"""
main.py — FastAPI Backend for Zoho Projects Assistant
------------------------------------------------------
This file is the backend server. It:
  1. Handles OAuth2 authentication with Zoho
  2. Exposes REST API endpoints that the Streamlit UI calls
  3. Proxies requests to the Zoho Projects REST API using stored tokens

Run with: uvicorn main:app --reload --port 8000
"""

# Import standard os and json modules for file operations and environment var handling
import os
import json
# Import requests for making HTTP calls to the Zoho API and Groq models
import requests
# load_dotenv reads variables from .env into os.environ
from dotenv import load_dotenv
# FastAPI framework imports to create our backend API server, routes, and error handling
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
# CORS is required so frontend requests from different ports don't get blocked
from fastapi.middleware.cors import CORSMiddleware
# StaticFiles is used to serve our vanilla JS app
from fastapi.staticfiles import StaticFiles
# Pydantic is used to validate incoming JSON structures on API endpoints
from pydantic import BaseModel
from typing import Optional
# Groq library for ultra-fast, cloud-based LLM inference
from groq import Groq
import traceback
# Ollama library used as our primary fallback LLM
import ollama

# Attempt to load local LLM components for offline fallback (Llama CP)
try:
    from huggingface_hub import hf_hub_download
    from llama_cpp import Llama
except ImportError:
    # If not installed, disable the local model fallback route safely
    hf_hub_download = None
    Llama = None

# ── Load environment variables from .env file ─────────────────────────────────
# Physically load the .env key values into memory
load_dotenv()

# ── FastAPI app instance ───────────────────────────────────────────────────────
# Instantiate the web server application giving it a unified title in docs
app = FastAPI(title="Zoho Projects Assistant API")

# ── Allow all origins (needed so Streamlit on :8501 can call this on :8000) ───
# Adds headers that tell browsers it's OK to interact with this API locally
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Configuration — read from .env ────────────────────────────────────────────
# Default Zoho endpoint configurations handling varying domains securely
ZOHO_DOMAIN       = os.getenv("ZOHO_DOMAIN", "projectsapi.zoho.in")
ZOHO_ACCOUNTS_URL = os.getenv("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.in")
PORTAL_ID         = os.getenv("PORTAL_ID", "60068773891")
CLIENT_ID         = os.getenv("ZOHO_CLIENT_ID", "")
CLIENT_SECRET     = os.getenv("ZOHO_CLIENT_SECRET", "")
# URL where Zoho will send the user back after they authorize our App securely
REDIRECT_URI      = os.getenv("ZOHO_REDIRECT_URI", "http://localhost:8000/callback")

# ── Token file — persists OAuth tokens between server restarts ────────────────
# Text file storing the generated JSON token block 
TOKEN_FILE = "zoho_tokens.json"

# Grab our Groq Key and initialize the cloud agent instance
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ── Ollama Local LLM Configuration ───────────────────────────────────────────
# Set up default parameters for Ollama API, fallback to default local docker configuration
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:11434")
# The ollama library uses OLLAMA_HOST. If we have a URL, extract the host part cleanly.
if "api/chat" in LOCAL_LLM_URL:
    os.environ["OLLAMA_HOST"] = LOCAL_LLM_URL.split("/api/chat")[0]
else:
    os.environ["OLLAMA_HOST"] = LOCAL_LLM_URL

LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "llama3")

# ── Token helpers ──────────────────────────────────────────────────────────────

# Method to safely retrieve Zoho credentials from disk
def load_tokens() -> dict:
    """Load OAuth tokens from the local JSON file. Creates a blank file if missing."""
    # If file doesn't exist, generate template data and save
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

    # If valid file exists, open and decode into dictionary
    with open(TOKEN_FILE, "r") as f:
        return json.load(f)

# Helper function to save incoming updated credentials to disk permanently
def save_tokens(tokens: dict):
    """Save OAuth tokens back to the local JSON file."""
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=4)

# Dedicated fast retrieval method for standard operations
def get_access_token() -> str:
    """Return the current access token from the stored tokens."""
    return load_tokens().get("access_token", "")

# Extracts formatted bearer strings formatted exactly for Zoho Servers
def get_headers() -> dict:
    """Build the Authorization header required by the Zoho API."""
    token = get_access_token()
    if not token:
        # Halt execution entirely and notify frontend of state
        raise HTTPException(
            status_code=401,
            detail="Access token missing. Visit /auth/login to authenticate."
        )
    return {"Authorization": f"Zoho-oauthtoken {token}"}

# Core session handling, automatically requests new token when previous expires natively
def refresh_access_token() -> bool:
    """
    Use the stored refresh token to get a new access token from Zoho.
    Returns True if successful, False otherwise.
    """
    tokens = load_tokens()
    refresh_token = tokens.get("refresh_token", "")
    if not refresh_token:
        return False

    # Dispatch request manually using specific grant type
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
    # Parse network output and securely overwrite JSON parameters locally
    data = response.json()
    if "access_token" in data:
        tokens["access_token"] = data["access_token"]
        save_tokens(tokens)
        return True
    return False


# Standardized method for interfacing directly with actual Zoho systems 
def zoho_request(method: str, url: str, **kwargs) -> requests.Response:
    """
    Central HTTP helper for all Zoho API calls.
    - Adds the Authorization header automatically.
    - If Zoho returns 401 (expired token), it refreshes and retries once.
    """
    kwargs.setdefault("headers", {}).update(get_headers())
    response = requests.request(method, url, timeout=15, **kwargs)

    # Auto-retry logic implemented in-line if token unexpectedly expired during invocation
    if response.status_code == 401 and refresh_access_token():
        kwargs["headers"].update(get_headers())
        response = requests.request(method, url, timeout=15, **kwargs)

    # General fallback logging locally
    if response.status_code >= 400:
        print(f"[Zoho API] {response.status_code} — {response.text[:200]}")

    return response


# ── Pydantic models — define the shape of request bodies ─────────────────────

# Ensure the POST payloads exactly map these variables to create correctly 
class TaskCreate(BaseModel):
    """Body for creating a new task."""
    name: str # Only the name is strictly required
    description: Optional[str] = None
    priority: Optional[str] = "None"
    person_responsible: Optional[str] = None


# Used specifically on Update events as Zoho treats Update/Creates differently
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
    # Differentiates user inputs from AI inferences
    role: str
    content: str
    
class ChatRequest(BaseModel):
    # Maintains conversation timeline history natively inside request
    messages: list[ChatMessage]


# ── Auth endpoints ─────────────────────────────────────────────────────────────

# Server base URL - confirms that Uvicorn container is active 
@app.get("/", tags=["Info"])
def root():
    """Health check — confirms the server is running."""
    return {
        "status": "running",
        "auth": "Visit /auth/login to authenticate with Zoho",
        "docs": "Visit /docs for the full API reference",
    }


# Initial setup stage triggered manually via web browser 
@app.get("/auth/login", tags=["Auth"])
def login():
    """
    Step 1 of OAuth2: redirect the browser to Zoho's login/consent page.
    Zoho will redirect back to /callback with an authorization code.
    """
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(500, "ZOHO_CLIENT_ID or ZOHO_CLIENT_SECRET not set in .env")

    # The level of permissions we request from Zoho explicitly
    scope = "ZohoProjects.portals.ALL,ZohoProjects.projects.ALL,ZohoProjects.tasks.ALL,ZohoProjects.users.ALL"
    
    # Fully qualified URL that User gets pushed to to grant access
    auth_url = (
        f"{ZOHO_ACCOUNTS_URL}/oauth/v2/auth"
        f"?scope={scope}"
        f"&client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&access_type=offline" # Offline mode asserts we want a persistent Refresh Token
        f"&prompt=consent"
        f"&redirect_uri={REDIRECT_URI}"
    )
    return RedirectResponse(auth_url)


# Target URL mapping to Zoho returning user payload
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

    # Send Zoho specific one-time code generated explicitly for this server session
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

    # Failout cleanly based on error messages
    if "access_token" not in data:
        raise HTTPException(400, f"Token exchange failed: {data}")

    # Write permanent file to system utilizing our helper function securely 
    save_tokens(data)
    # Redirect to API docs so user can confirm everything worked visually
    return RedirectResponse("/docs")


# ── Portal & Project endpoints ─────────────────────────────────────────────────

# Retrieve all high level portal clusters for instance tracking
@app.get("/portals", tags=["Portals"])
def list_portals():
    """List all Zoho portals the authenticated user has access to."""
    response = zoho_request("GET", f"https://{ZOHO_DOMAIN}/restapi/portals/")
    if response.status_code == 200:
        return response.json()
    raise HTTPException(response.status_code, response.text)

# Returns specific isolated sub-environments natively
@app.get("/projects", tags=["Projects"])
def list_projects():
    """List all projects in the configured portal."""
    response = zoho_request("GET", f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/")
    if response.status_code == 200:
        return response.json()
    raise HTTPException(response.status_code, response.text)


# ── Task CRUD endpoints ────────────────────────────────────────────────────────

# Return a list of completely managed tasks assigned inside standard environment
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

# Query details on a specific unified object manually by appending Task ID
@app.get("/projects/{project_id}/tasks/{task_id}", tags=["Tasks"])
def get_task(project_id: str, task_id: str):
    """READ — Fetch details for a single task by its ID."""
    url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/{project_id}/tasks/{task_id}/"
    response = zoho_request("GET", url)
    if response.status_code == 200:
        return response.json()
    raise HTTPException(response.status_code, response.text)

# Post completely new generated item blocks inside a specific group container
@app.post("/projects/{project_id}/tasks", tags=["Tasks"])
def create_task(project_id: str, task: TaskCreate):
    """
    CREATE — Add a new task to a project.
    Accepts a JSON body with at least a 'name' field.
    """
    url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/{project_id}/tasks/"
    # model_dump() excludes None fields so we only send what is explicitly provided natively 
    payload = task.model_dump(exclude_none=True)
    response = zoho_request("POST", url, data=payload)
    if response.status_code in (200, 201):
        return response.json()
    raise HTTPException(response.status_code, response.text)

# Change properties on previously generated systems natively 
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

# Erase entry block natively completely destroying it
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

# Query high-level members structure for portal operations tracking assignments correctly
@app.get("/users", tags=["Users"])
def list_users():
    """List all users in the portal."""
    url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/users/"
    response = zoho_request("GET", url)
    if response.status_code == 200:
        return response.json()
    raise HTTPException(response.status_code, response.text)

# Specifically track subsets assigned natively by project constraint explicitly
@app.get("/projects/{project_id}/users", tags=["Users"])
def list_project_users_api(project_id: str):
    """List users belonging to a specific project."""
    url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/{project_id}/users/"
    response = zoho_request("GET", url)
    if response.status_code == 200:
        return response.json()
    raise HTTPException(response.status_code, response.text)

# System logic injecting members into specified workflows directly
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

# Native structured data map formatting the functions AI interface has access to cleanly for OpenAI spec natively
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
            "name": "list_project_users",
            "description": "List users actively assigned to a specific project. Needed before assigning tasks.",
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

# Primary logic constraints dictating core behavior for natural language generation accurately for the specific product suite exclusively!
SYSTEM_PROMPT = """
You are the Zoho AI Assistant, deeply integrated with Zoho Projects to manage tasks, projects, and analyze team utilization.

Core rules:
1. Natural Language & Guided UI: ALWAYS respond in natural, plain, conversational human English. Do not use highly-structured robotic jargon. For CRUD operations or selecting items (e.g., choosing a project or an assignee), instruct the user conversationally, BUT format your FINAL response to include a strict JSON block wrapped in ` ```json ` ... ` ``` ` that defines options the UI will render as buttons.
Example format for options:
```json
{
  "options": [
    {"label": "Actual Name from DB", "value": "ID from DB"},
    {"label": "Another Name from DB", "value": "ID from DB"}
  ]
}
```
CRITICAL RULE: NEVER output a JSON block for simple text inputs (like asking for a task name or description). ONLY use JSON blocks strictly for providing `options` buttons when a user needs to pick from a list. Ask for all other inputs in plain natural English (e.g., "What would you like the task name to be?").
Include your conversational normal text BEFORE the JSON block. If a tool returns an error, DO NOT make up fake users, simply tell the user the API failed!
2. Strict Task Creation Workflow Constraint:
   - When creating a task, you MUST confirm the `project_id` FIRST (using `list_projects` if needed).
   - Once you have the `project_id`, you MUST run `list_project_users(project_id)` to get valid project members.
   - Format the valid project users as JSON options buttons, and ask the user for both the assignee selection and the task name simultaneously.
3. Reviewing Utilization & Status Updates: When asked about utilization of each team/member, use list_projects and list_tasks to calculate assignments. Use list_users to ensure mapping. You can update task statuses using the update_task tool.
4. "Due this month": Look at the current date dynamically (evaluate it) and use list_projects to see `end_date_format` or `end_date` to determine what projects are due this month.
5. Task Assignment Choice: When a user asks you to create and assign a task (or assign an existing task), without explicitly specifying an assignee, you MUST first offer them a choice. Give them two JSON button options: "Assign manually myself" and "Auto-assign (balance load)".
If they select "Auto-assign (balance load)", you MUST dynamically calculate the utilization of the project team members. To do this: first call `list_project_users` to get the team member IDs. Then call `list_tasks` to get the current tasks in the project. Count the number of active tasks assigned to each team member (by matching `owner_id` or `name`). Automatically call `create_task` or `update_task`, providing the user ID (`person_responsible`) of the team member with the LOWEST number of assigned tasks. Finally, explain in natural human language who you assigned the task to and why.
If they select "Assign manually myself", call `list_project_users` and present the users as JSON button options for them to pick from.
"""

local_llm_instance = None

# Handles physically initializing local Llama system effectively and securely keeping instance permanently bound to backend runtime constraints
def get_local_llm():
    global local_llm_instance
    if local_llm_instance is None:
        if hf_hub_download is None or Llama is None:
            raise Exception("llama-cpp-python or huggingface-hub is not installed.")
        print("[Fallback] Downloading/Loading local Llama-3.2 model from Hugging Face...")
        # Pull specified hardware model file and cache on physical environment naturally gracefully without blocking indefinitely effectively
        model_path = hf_hub_download(repo_id="bartowski/Llama-3.2-3B-Instruct-GGUF", filename="Llama-3.2-3B-Instruct-Q4_K_M.gguf")
        # Generate instance utilizing system limitations securely dynamically directly manually securely 
        local_llm_instance = Llama(model_path=model_path, n_ctx=4096, chat_format="llama-3", verbose=False)
    return local_llm_instance

# Primary bridging mechanism interpreting generic LLM payloads translating to hard-coded Python implementations gracefully 
def execute_tool(tool_call):
    name = tool_call.function.name
    args = {}
    # Decrypt JSON generated natively by LLM inference 
    if tool_call.function.arguments:
        args = json.loads(tool_call.function.arguments)
    print(f"[Tool Call] {name}({args})")
    
    # Simple explicit routing mapping LLM functions exactly to specific Python implementations 
    try:
        if name == "list_projects":
            data = list_projects()
            # Trim massive response payload avoiding context length failure gracefully safely 
            return [{"id_string": p.get("id_string"), "name": p.get("name"), "end_date_format": p.get("end_date_format", ""), "end_date": p.get("end_date", "")} for p in data.get("projects", [])]
        elif name == "list_tasks":
            data = list_tasks(args["project_id"])
            return [{"id_string": t.get("id_string"), "name": t.get("name"), "status": t.get("status",{}).get("name"), "priority": t.get("priority"), "owner": (t.get("details",{}).get("owners") or [{}])[0].get("name"), "owner_id": (t.get("details",{}).get("owners") or [{}])[0].get("id")} for t in data.get("tasks", [])]
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
        elif name == "list_project_users":
            url = f"https://{ZOHO_DOMAIN}/restapi/portal/{PORTAL_ID}/projects/{args['project_id']}/users/"
            r = zoho_request("GET", url)
            if r.status_code == 200:
                return [{"id": u.get("id"), "name": u.get("name"), "email": u.get("email")} for u in r.json().get("users", [])]
            return {"error": r.text}
        elif name == "add_user_to_project":
            return add_user_to_project(args["project_id"], AddUserBody(email=args["email"]))
        else:
            return {"error": "Unknown tool"}
    except Exception as e:
        # Stop crashing entire system if API rejects formatted arguments securely preventing total crashes 
        return {"error": str(e)}

# Central Hub handling complex orchestration across Cloud, Containers, and Hardware Fallbacks exclusively directly securely 
@app.post("/chat", tags=["Chat"])
def chat(request: ChatRequest):
    # Verify primary provider operates clearly securely inherently fundamentally  
    if not groq_client:
        raise HTTPException(500, "Groq API client is not configured.")
    
    # Check if a fallback notification has already been shown in this conversation securely natively effectively naturally 
    has_fallback_note = any("*(Note: Acting via" in m.content for m in request.messages if m.content)

    # Reconstruct system context natively directly 
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in request.messages:
        messages.append({"role": m.role, "content": m.content})
        
    try:
        # Generate persistent loop evaluating recursive tools reliably organically 
        while True:
            content_text = None
            tool_calls_data = []
            fallback_used = None

            try:
                # Primary Groq API Route explicitly natively automatically securely
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
                # Graceful degradation logic executed automatically without explicit manual intervention securely
                print(f"[Fallback] Groq API Failed: {groq_err}")
                
                try:
                    # First Fallback Tier: Local containerized Ollama instance 
                    fallback_used = "Ollama"
                    print(f"[Fallback] Swapping to Ollama ({LOCAL_LLM_MODEL})...")
                    # Clean messages for Ollama payload requirements
                    clean_msgs = []
                    for msg in messages:
                        if isinstance(msg, dict):
                            clean_msgs.append(msg)
                        else:
                            clean_msgs.append(msg.model_dump(exclude_none=True))

                    # Fire off standard network payload securely dynamically 
                    res = ollama.chat(
                        model=LOCAL_LLM_MODEL,
                        messages=clean_msgs,
                        tools=zoho_tools,
                    )
                    m_data = res["message"]
                    content_text = m_data.get("content")
                    
                    # Map Ollama output back to identical object format used by primary logic cleanly!
                    class MockFunc:
                        def __init__(self, name, args):
                            self.name = name
                            self.arguments = json.dumps(args) if isinstance(args, dict) else args
                    class MockTC:
                        def __init__(self, t_id, name, args):
                            self.id = t_id
                            self.function = MockFunc(name, args)
                    
                    for tc in m_data.get("tool_calls", []):
                        fn_data = tc["function"]
                        tool_calls_data.append(MockTC(f"ollama_{fn_data['name']}", fn_data['name'], fn_data['arguments']))

                except Exception as ollama_err:
                    # Final Fail-safe tier: completely local CPU hardware execution independently securely
                    print(f"[Fallback] Ollama Failed: {ollama_err}")
                    fallback_used = "Offline Llama-cpp"
                    print(f"[Fallback] Swapping to Local LLM (llama-cpp-python)...")
                    llm = get_local_llm()
                    
                    clean_msgs = []
                    for msg in messages:
                        if isinstance(msg, dict):
                            clean_msgs.append(msg)
                        else:
                            clean_msgs.append(msg.model_dump(exclude_none=True))
                    
                    # Execute localized CPU bound inference natively without network completely organically naturally 
                    res = llm.create_chat_completion(
                        messages=clean_msgs,
                        tools=zoho_tools,
                        tool_choice="auto",
                        max_tokens=2048
                    )
                    m_data = res["choices"][0]["message"]
                    content_text = m_data.get("content")
                    
                    # Generate Mock tool execution definitions securely functionally independently
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

            # Handle executed tool payloads cleanly natively natively appropriately 
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
                # Commit tool selection logically back to execution history dynamically securely
                messages.append({
                    "role": "assistant",
                    "content": content_text,
                    "tool_calls": tool_calls_dict
                })
                
                # Execute tools against the defined implementation explicitly dynamically organically gracefully  
                for tc in tool_calls_data:
                    result = execute_tool(tc)
                    # Push result payload directly securely intelligently onto sequence naturally
                    messages.append({
                        "tool_call_id": tc.id,
                        "role": "tool",
                        "name": tc.function.name,
                        "content": json.dumps(result, default=str)
                    })
            else:
                # Execution finished cleanly! Inform user visually if degraded naturally securely reliably
                if fallback_used and not has_fallback_note:
                    suffix = f"\n\n*(Note: Acting via {fallback_used} backup)*"
                    content_text = (content_text or "") + suffix
                return {"role": "assistant", "content": content_text}
                
    except HTTPException:
        # Re-raise FastAPIs HTTPException to preserve Zoho's 401/403/404 errors etc.
        raise
    except Exception as e:
        # Trace errors out explicitly natively inherently naturally manually securely
        print(f"Chat error: {e}")
        traceback.print_exc()
        raise HTTPException(500, detail=f"AI Assistant Error: {str(e)}")

# ── Serve the static Vanilla JS frontend at /app ──────────────────────────────
# Instruct FastAPI system locally securely natively inherently organically where to find UI files for Dashboard functionality properly natively
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="frontend")
