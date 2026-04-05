"""
main.py — FastAPI Backend for Zoho Projects Assistant
------------------------------------------------------
This file is the backend server. It:
  1. Handles OAuth2 authentication with Zoho
  2. Exposes REST API endpoints that the Streamlit UI calls
  3. Proxies requests to the Zoho Projects REST API using stored tokens

Run with: uvicorn main:app --reload --port 8000
"""

import os
import json
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

# ── Load environment variables from .env file ─────────────────────────────────
load_dotenv()

# ── FastAPI app instance ───────────────────────────────────────────────────────
app = FastAPI(title="Zoho Projects Assistant API")

# ── Allow all origins (needed so Streamlit on :8501 can call this on :8000) ───
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Configuration — read from .env ────────────────────────────────────────────
ZOHO_DOMAIN       = os.getenv("ZOHO_DOMAIN", "projectsapi.zoho.in")
ZOHO_ACCOUNTS_URL = os.getenv("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.in")
PORTAL_ID         = os.getenv("PORTAL_ID", "60068773891")
CLIENT_ID         = os.getenv("ZOHO_CLIENT_ID", "")
CLIENT_SECRET     = os.getenv("ZOHO_CLIENT_SECRET", "")
REDIRECT_URI      = os.getenv("ZOHO_REDIRECT_URI", "http://localhost:8000/callback")

# ── Token file — persists OAuth tokens between server restarts ────────────────
TOKEN_FILE = "zoho_tokens.json"


# ── Token helpers ──────────────────────────────────────────────────────────────

def load_tokens() -> dict:
    """Load OAuth tokens from the local JSON file. Creates a blank file if missing."""
    if not os.path.exists(TOKEN_FILE):
        blank = {
            "access_token": "",
            "refresh_token": "",
            "scope": "ZohoProjects.tasks.ALL ZohoProjects.projects.ALL",
            "api_domain": "https://www.zohoapis.in",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        with open(TOKEN_FILE, "w") as f:
            json.dump(blank, f, indent=4)
        return blank

    with open(TOKEN_FILE, "r") as f:
        return json.load(f)


def save_tokens(tokens: dict):
    """Save OAuth tokens back to the local JSON file."""
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=4)


def get_access_token() -> str:
    """Return the current access token from the stored tokens."""
    return load_tokens().get("access_token", "")


def get_headers() -> dict:
    """Build the Authorization header required by the Zoho API."""
    token = get_access_token()
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Access token missing. Visit /auth/login to authenticate."
        )
    return {"Authorization": f"Zoho-oauthtoken {token}"}


def refresh_access_token() -> bool:
    """
    Use the stored refresh token to get a new access token from Zoho.
    Returns True if successful, False otherwise.
    """
    tokens = load_tokens()
    refresh_token = tokens.get("refresh_token", "")
    if not refresh_token:
        return False

    response = requests.post(
        f"{ZOHO_ACCOUNTS_URL}/oauth/v2/token",
        data={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
        },
        timeout=15,
    )
    data = response.json()
    if "access_token" in data:
        tokens["access_token"] = data["access_token"]
        save_tokens(tokens)
        return True
    return False


def zoho_request(method: str, url: str, **kwargs) -> requests.Response:
    """
    Central HTTP helper for all Zoho API calls.
    - Adds the Authorization header automatically.
    - If Zoho returns 401 (expired token), it refreshes and retries once.
    """
    kwargs.setdefault("headers", {}).update(get_headers())
    response = requests.request(method, url, timeout=15, **kwargs)

    # Auto-retry once if token expired
    if response.status_code == 401 and refresh_access_token():
        kwargs["headers"].update(get_headers())
        response = requests.request(method, url, timeout=15, **kwargs)

    if response.status_code >= 400:
        print(f"[Zoho API] {response.status_code} — {response.text[:200]}")

    return response


# ── Pydantic models — define the shape of request bodies ─────────────────────

class TaskCreate(BaseModel):
    """Body for creating a new task."""
    name: str
    description: Optional[str] = None
    priority: Optional[str] = "None"


class TaskUpdate(BaseModel):
    """Body for updating an existing task (all fields optional)."""
    name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    percent_complete: Optional[int] = None


class AddUserBody(BaseModel):
    """Body for adding a user to a project."""
    email: str


# ── Auth endpoints ─────────────────────────────────────────────────────────────

@app.get("/", tags=["Info"])
def root():
    """Health check — confirms the server is running."""
    return {
        "status": "running",
        "auth": "Visit /auth/login to authenticate with Zoho",
        "docs": "Visit /docs for the full API reference",
    }


@app.get("/auth/login", tags=["Auth"])
def login():
    """
    Step 1 of OAuth2: redirect the browser to Zoho's login/consent page.
    Zoho will redirect back to /callback with an authorization code.
    """
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(500, "ZOHO_CLIENT_ID or ZOHO_CLIENT_SECRET not set in .env")

    scope = "ZohoProjects.portals.ALL,ZohoProjects.projects.ALL,ZohoProjects.tasks.ALL"
    auth_url = (
        f"{ZOHO_ACCOUNTS_URL}/oauth/v2/auth"
        f"?scope={scope}"
        f"&client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&access_type=offline"
        f"&prompt=consent"
        f"&redirect_uri={REDIRECT_URI}"
    )
    return RedirectResponse(auth_url)


@app.get("/callback", tags=["Auth"])
def callback(code: str = None, error: str = None):
    """
    Step 2 of OAuth2: Zoho redirects here after the user grants permission.
    We exchange the code for access + refresh tokens and save them locally.
    """
    if error:
        raise HTTPException(400, f"OAuth error from Zoho: {error}")
    if not code:
        raise HTTPException(400, "Missing authorization code in callback")

    response = requests.post(
        f"{ZOHO_ACCOUNTS_URL}/oauth/v2/token",
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "code": code,
        },
        timeout=15,
    )
    data = response.json()

    if "access_token" not in data:
        raise HTTPException(400, f"Token exchange failed: {data}")

    save_tokens(data)
    # Redirect to API docs so user can confirm everything worked
    return RedirectResponse("/docs")


# ── Portal & Project endpoints ─────────────────────────────────────────────────

@app.get("/portals", tags=["Portals"])
def list_portals():
    """List all Zoho portals the authenticated user has access to."""
    response = zoho_request("GET", f"https://{ZOHO_DOMAIN}/restapi/portals/")
    if response.status_code == 200:
        return response.json()
    raise HTTPException(response.status_code, response.text)


@app.get("/projects", tags=["Projects"])
def list_projects():
    """List all projects in the configured portal."""
    response = zoho_request("GET", f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/")
    if response.status_code == 200:
        return response.json()
    raise HTTPException(response.status_code, response.text)


# ── Task CRUD endpoints ────────────────────────────────────────────────────────

@app.get("/tasks", tags=["Tasks"])
def list_tasks(project_id: str):
    """
    READ — List all tasks for a given project.
    The project_id is passed as a query parameter: /tasks?project_id=...
    """
    url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/{project_id}/tasks/"
    response = zoho_request("GET", url)
    if response.status_code == 200:
        return response.json()
    raise HTTPException(response.status_code, response.text)


@app.get("/projects/{project_id}/tasks/{task_id}", tags=["Tasks"])
def get_task(project_id: str, task_id: str):
    """READ — Fetch details for a single task by its ID."""
    url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/{project_id}/tasks/{task_id}/"
    response = zoho_request("GET", url)
    if response.status_code == 200:
        return response.json()
    raise HTTPException(response.status_code, response.text)


@app.post("/projects/{project_id}/tasks", tags=["Tasks"])
def create_task(project_id: str, task: TaskCreate):
    """
    CREATE — Add a new task to a project.
    Accepts a JSON body with at least a 'name' field.
    """
    url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/{project_id}/tasks/"
    # model_dump() excludes None fields so we only send what is provided
    payload = task.model_dump(exclude_none=True)
    response = zoho_request("POST", url, data=payload)
    if response.status_code in (200, 201):
        return response.json()
    raise HTTPException(response.status_code, response.text)


@app.post("/projects/{project_id}/tasks/{task_id}/update", tags=["Tasks"])
def update_task(project_id: str, task_id: str, task: TaskUpdate):
    """
    UPDATE — Modify an existing task.
    Zoho uses POST (not PATCH) for task updates.
    Only the fields provided in the body will be updated.
    """
    url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/{project_id}/tasks/{task_id}/"
    payload = task.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(400, "No update fields provided.")
    response = zoho_request("POST", url, data=payload)
    if response.status_code in (200, 201):
        return response.json()
    raise HTTPException(response.status_code, response.text)


@app.delete("/projects/{project_id}/tasks/{task_id}", tags=["Tasks"])
def delete_task(project_id: str, task_id: str):
    """
    DELETE — Permanently remove a task from a project.
    Returns a confirmation message on success.
    """
    url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/{project_id}/tasks/{task_id}/"
    response = zoho_request("DELETE", url)
    if response.status_code in (200, 204):
        return {"message": f"Task {task_id} deleted successfully."}
    raise HTTPException(response.status_code, response.text)


# ── User endpoints ─────────────────────────────────────────────────────────────

@app.get("/users", tags=["Users"])
def list_users():
    """List all users in the portal."""
    url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/users/"
    response = zoho_request("GET", url)
    if response.status_code == 200:
        return response.json()
    raise HTTPException(response.status_code, response.text)


@app.post("/projects/{project_id}/users", tags=["Users"])
def add_user_to_project(project_id: str, body: AddUserBody):
    """
    Add a user to a project by their email address.
    Accepts a JSON body: { "email": "user@example.com" }
    """
    url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/{project_id}/users/"
    response = zoho_request("POST", url, data={"email": body.email})
    if response.status_code in (200, 201):
        return response.json()
    raise HTTPException(response.status_code, response.text)


# ── Serve the static Vanilla JS frontend at /app ──────────────────────────────
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="frontend")
