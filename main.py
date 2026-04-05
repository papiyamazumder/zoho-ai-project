import os
import json
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

load_dotenv()

app = FastAPI(title="Zoho Projects FastAPI integration")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
ZOHO_DOMAIN = os.getenv("ZOHO_DOMAIN", "projectsapi.zoho.in") 
ZOHO_ACCOUNTS_URL = os.getenv("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.in")
PORTAL_ID = os.getenv("PORTAL_ID", "43903000000069138")

CLIENT_ID = os.getenv("ZOHO_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("ZOHO_REDIRECT_URI", "http://localhost:8000/callback")

TOKEN_FILE = "zoho_tokens.json"

def load_tokens():
    if not os.path.exists(TOKEN_FILE):
        default_tokens = {
            "access_token": "",
            "refresh_token": "",
            "scope": "ZohoProjects.tasks.ALL ZohoProjects.projects.ALL",
            "api_domain": "https://www.zohoapis.in",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        with open(TOKEN_FILE, "w") as f:
            json.dump(default_tokens, f, indent=4)
        return default_tokens

    with open(TOKEN_FILE, "r") as f:
        return json.load(f)

def save_tokens(tokens):
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=4)

def get_access_token():
    tokens = load_tokens()
    access_token = tokens.get("access_token")
    return access_token

def get_headers():
    token = get_access_token()
    if not token:
        raise HTTPException(status_code=401, detail="Access token missing. Please visit /auth/login first.")
    return {
        "Authorization": f"Zoho-oauthtoken {token}"
    }

def refresh_access_token():
    tokens = load_tokens()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return False
        
    url = f"{ZOHO_ACCOUNTS_URL}/oauth/v2/token"
    payload = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token
    }
    response = requests.post(url, data=payload)
    data = response.json()
    if "access_token" in data:
        tokens["access_token"] = data["access_token"]
        save_tokens(tokens)
        return True
    return False

def make_zoho_request(method, url, **kwargs):
    headers = get_headers()
    if 'headers' in kwargs:
        kwargs['headers'].update(headers)
    else:
        kwargs['headers'] = headers
        
    response = requests.request(method, url, **kwargs)
    if response.status_code == 401:
        # Token might have expired, attempt to refresh
        if refresh_access_token():
            kwargs['headers'] = get_headers()
            response = requests.request(method, url, **kwargs)
    return response

class TaskCreate(BaseModel):
    name: str
    description: Optional[str] = None
    priority: Optional[str] = "None" 

class TaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    percent_complete: Optional[int] = None

@app.get("/")
def read_root():
    return {
        "message": "Welcome to Zoho Projects Fast API Server.",
        "authorization": "Visit /auth/login to authenticate with Zoho.",
        "docs": "Visit /docs to see the endpoints."
    }

@app.get("/auth/login")
def login():
    """Redirects to Zoho for OAuth2 Authorization"""
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Client ID or Secret is not set in .env")
        
    scope = "ZohoProjects.tasks.ALL,ZohoProjects.projects.ALL"
    url = f"{ZOHO_ACCOUNTS_URL}/oauth/v2/auth?scope={scope}&client_id={CLIENT_ID}&response_type=code&access_type=offline&prompt=consent&redirect_uri={REDIRECT_URI}"
    return RedirectResponse(url)

@app.get("/callback")
def callback(code: str = None, error: str = None):
    """Callback endpoint for Zoho OAuth2. Zoho will redirect here with a 'code' parameter."""
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    url = f"{ZOHO_ACCOUNTS_URL}/oauth/v2/token"
    payload = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "code": code
    }
    
    response = requests.post(url, data=payload)
    data = response.json()
    
    if "access_token" in data:
        save_tokens(data)
        return RedirectResponse(url="/app/index.html")
    else:
        raise HTTPException(status_code=400, detail=f"Failed to get token: {data}")

@app.get("/projects")
def list_projects():
    """Retrieve all projects for the portal"""
    url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/"
    response = make_zoho_request('GET', url)
    if response.status_code == 200:
        return response.json()
    raise HTTPException(status_code=response.status_code, detail=response.text)

@app.get("/tasks")
def list_tasks(project_id: str):
    """Retrieve all tasks from a project"""
    url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/{project_id}/tasks/"
    response = make_zoho_request('GET', url)
    if response.status_code == 200:
        return response.json()
    raise HTTPException(status_code=response.status_code, detail=response.text)

@app.get("/projects/{project_id}/tasks/{task_id}")
def get_task(project_id: str, task_id: str):
    """Retrieve details of a specific task"""
    url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/{project_id}/tasks/{task_id}/"
    response = make_zoho_request('GET', url)
    if response.status_code == 200:
        return response.json()
    raise HTTPException(status_code=response.status_code, detail=response.text)

@app.post("/projects/{project_id}/tasks")
def create_task(project_id: str, task: TaskCreate):
    """Create a new task in the project"""
    url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/{project_id}/tasks/"
    payload = task.dict(exclude_none=True)
    response = make_zoho_request('POST', url, data=payload)
    if response.status_code in (200, 201):
        return response.json()
    raise HTTPException(status_code=response.status_code, detail=response.text)

@app.post("/projects/{project_id}/tasks/{task_id}/update")
def update_task(project_id: str, task_id: str, task: TaskUpdate):
    """Update an existing task in the project."""
    url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/{project_id}/tasks/{task_id}/"
    payload = task.dict(exclude_none=True)
    response = make_zoho_request('POST', url, data=payload)
    if response.status_code in (200, 201):
        return response.json()
    raise HTTPException(status_code=response.status_code, detail=response.text)

@app.delete("/projects/{project_id}/tasks/{task_id}")
def delete_task(project_id: str, task_id: str):
    """Delete a task"""
    url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/{project_id}/tasks/{task_id}/"
    response = make_zoho_request('DELETE', url)
    if response.status_code in (200, 204):
        return {"message": f"Task {task_id} successfully deleted."}
    raise HTTPException(status_code=response.status_code, detail=response.text)

frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="frontend")
