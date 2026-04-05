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
from groq import Groq
import traceback

# Optional imports for local LLM fallback
try:
    from huggingface_hub import hf_hub_download
    from llama_cpp import Llama
except ImportError:
    hf_hub_download = None
    Llama = None

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

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
# ── Token helpers ──────────────────────────────────────────────────────────────

def load_tokens() -> dict:
    """Load OAuth tokens from the local JSON file. Creates a blank file if missing."""
    if not os.path.exists(TOKEN_FILE):
        blank = {
            "access_token": "",
            "refresh_token": "",
            "scope": "ZohoProjects.tasks.ALL ZohoProjects.projects.ALL ZohoProjects.users.ALL",
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
    person_responsible: Optional[str] = None


class TaskUpdate(BaseModel):
    """Body for updating an existing task (all fields optional)."""
    name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    custom_status: Optional[str] = None
    percent_complete: Optional[int] = None
    person_responsible: Optional[str] = None


class AddUserBody(BaseModel):
    """Body for adding a user to a project."""
    email: str

class ChatMessage(BaseModel):
    role: str
    content: str
    
class ChatRequest(BaseModel):
    messages: list[ChatMessage]


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

    scope = "ZohoProjects.portals.ALL,ZohoProjects.projects.ALL,ZohoProjects.tasks.ALL,ZohoProjects.users.ALL"
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


# ── LLM Chat Endpoint ─────────────────────────────────────────────────────────

zoho_tools = [
    {
        "type": "function",
        "function": {
            "name": "list_projects",
            "description": "Fetch all projects available in the user's Zoho portal. Returns project IDs and names.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "Fetch tasks for a specific project. Needed to get task utilization, deadlines, or listing tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The unique ID of the project."}
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Creates a task in a specific project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The unique ID of the project."},
                    "name": {"type": "string", "description": "Name of the task."},
                    "priority": {"type": "string", "description": "Priority (None, Low, Medium, High)."},
                    "person_responsible": {"type": "string", "description": "Unique user ID to assign this task to."}
                },
                "required": ["project_id", "name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": "Updates a task. Use this to assign/change users (person_responsible) or update the status (custom_status / status).",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The unique ID of the project."},
                    "task_id": {"type": "string", "description": "The unique ID of the task."},
                    "person_responsible": {"type": "string", "description": "The unique user ID to assign."},
                    "status": {"type": "string", "description": "The new status label or ID."}
                },
                "required": ["project_id", "task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": "Deletes a task from a specific project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The unique ID of the project."},
                    "task_id": {"type": "string", "description": "The unique ID of the task."}
                },
                "required": ["project_id", "task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_users",
            "description": "List all users/team members to assess utilization or task assignments.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_user_to_project",
            "description": "Adds a user to a project (Assigning a project to an employee).",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The unique ID of the project."},
                    "email": {"type": "string", "description": "The email of the user to add."}
                },
                "required": ["project_id", "email"]
            }
        }
    }
]

SYSTEM_PROMPT = """
You are the Zoho AI Assistant, deeply integrated with Zoho Projects to manage tasks, projects, and analyze team utilization.
Core rules:
1. Interactive & Guided UI: For CRUD operations or selecting items (e.g., choosing a project or an assignee), DO NOT ask the user to type structured inputs manually. Instead, instruct them with normal text, BUT format your FINAL response to include a strict JSON block wrapped in ` ```json ` ... ` ``` ` that defines options the UI will render as buttons.
Example format for options:
```json
{
  "options": [
    {"label": "Actual Name from DB", "value": "ID from DB"},
    {"label": "Another Name from DB", "value": "ID from DB"}
  ]
}
```
Include your conversational normal text BEFORE the JSON block. If a tool returns an error, DO NOT make up fake users, simply tell the user the API failed!
2. Smart Clarifications: If you need a project_id but only have the name, try to list_projects first. If you need a user ID, list_users first! For task statuses, you can use the update_task tool.
3. Reviewing Utilization & Status Updates: When asked about utilization of each team/member, use list_projects and list_tasks to calculate assignments. Use list_users to ensure mapping. You can update task statuses using the update_task tool.
4. "Due this month": Look at the current date dynamically (evaluate it) and use list_projects to see `end_date_format` or `end_date` to determine what projects are due this month.
"""

local_llm_instance = None

def get_local_llm():
    global local_llm_instance
    if local_llm_instance is None:
        if hf_hub_download is None or Llama is None:
            raise Exception("llama-cpp-python or huggingface-hub is not installed.")
        print("[Fallback] Downloading/Loading local Llama-3.2 model from Hugging Face...")
        model_path = hf_hub_download(repo_id="bartowski/Llama-3.2-3B-Instruct-GGUF", filename="Llama-3.2-3B-Instruct-Q4_K_M.gguf")
        local_llm_instance = Llama(model_path=model_path, n_ctx=4096, chat_format="llama-3", verbose=False)
    return local_llm_instance

def execute_tool(tool_call):
    name = tool_call.function.name
    args = {}
    if tool_call.function.arguments:
        args = json.loads(tool_call.function.arguments)
    print(f"[Tool Call] {name}({args})")
    
    try:
        if name == "list_projects":
            data = list_projects()
            return [{"id_string": p.get("id_string"), "name": p.get("name"), "end_date_format": p.get("end_date_format", ""), "end_date": p.get("end_date", "")} for p in data.get("projects", [])]
        elif name == "list_tasks":
            data = list_tasks(args["project_id"])
            return [{"id_string": t.get("id_string"), "name": t.get("name"), "status": t.get("status",{}).get("name"), "priority": t.get("priority"), "owner": (t.get("details",{}).get("owners") or [{}])[0].get("name")} for t in data.get("tasks", [])]
        elif name == "create_task":
            return create_task(args["project_id"], TaskCreate(
                name=args["name"], 
                priority=args.get("priority", "None"),
                person_responsible=args.get("person_responsible")
            ))
        elif name == "update_task":
            return update_task(args["project_id"], args["task_id"], TaskUpdate(
                status=args.get("status"),
                person_responsible=args.get("person_responsible")
            ))
        elif name == "delete_task":
            return delete_task(args["project_id"], args["task_id"])
        elif name == "list_users":
            data = list_users()
            return [{"id": u.get("id"), "name": u.get("name"), "email": u.get("email")} for u in data.get("users", [])]
        elif name == "add_user_to_project":
            return add_user_to_project(args["project_id"], AddUserBody(email=args["email"]))
        else:
            return {"error": "Unknown tool"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/chat", tags=["Chat"])
def chat(request: ChatRequest):
    if not groq_client:
        raise HTTPException(500, "Groq API client is not configured.")
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in request.messages:
        messages.append({"role": m.role, "content": m.content})
        
    try:
        while True:
            content_text = None
            tool_calls_data = []

            try:
                # Primary Groq API Route
                response = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    tools=zoho_tools,
                    tool_choice="auto",
                    max_tokens=2048
                )
                m = response.choices[0].message
                content_text = m.content
                tool_calls_data = m.tool_calls or []
            except Exception as groq_err:
                print(f"[Fallback] Groq API Failed: {groq_err}")
                print(f"[Fallback] Swapping to Local LLM (llama-cpp-python)...")
                llm = get_local_llm()
                
                # Filter out messages with type expected by groq into pure dicts
                clean_msgs = []
                for msg in messages:
                    if isinstance(msg, dict):
                        clean_msgs.append(msg)
                    else:
                        clean_msgs.append(msg.model_dump(exclude_none=True))
                
                res = llm.create_chat_completion(
                    messages=clean_msgs,
                    tools=zoho_tools,
                    tool_choice="auto",
                    max_tokens=2048
                )
                m_data = res["choices"][0]["message"]
                content_text = m_data.get("content")
                
                # Map llama-cpp dict output to object-like structure so the remaining code works
                class MockFunc:
                    def __init__(self, name, args):
                        self.name = name
                        self.arguments = args
                class MockTC:
                    def __init__(self, t_id, name, args):
                        self.id = t_id
                        self.function = MockFunc(name, args)
                for tc in m_data.get("tool_calls", []):
                    tool_calls_data.append(MockTC(tc["id"], tc["function"]["name"], tc["function"]["arguments"]))

            if tool_calls_data:
                tool_calls_dict = []
                for tc in tool_calls_data:
                    tool_calls_dict.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })
                messages.append({
                    "role": "assistant",
                    "content": content_text,
                    "tool_calls": tool_calls_dict
                })
                
                for tc in tool_calls_data:
                    result = execute_tool(tc)
                    messages.append({
                        "tool_call_id": tc.id,
                        "role": "tool",
                        "name": tc.function.name,
                        "content": json.dumps(result, default=str)
                    })
            else:
                return {"role": "assistant", "content": content_text}
                
    except Exception as e:
        print(f"Chat error: {e}")
        traceback.print_exc()
        raise HTTPException(500, str(e))

# ── Serve the static Vanilla JS frontend at /app ──────────────────────────────
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="frontend")
