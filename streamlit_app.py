"""
streamlit_app.py — Streamlit Chat UI for Zoho Projects Assistant
-----------------------------------------------------------------
This file is the AI-powered front-end. It:
  1. Provides a chat interface where users can type natural language requests
  2. Uses Groq (LLaMA 3) to parse the user's intent from the text
  3. Calls the FastAPI backend (main.py) to perform the actual CRUD operations
  4. Also exposes sidebar quick-action panels for direct CRUD without typing

Run with: streamlit run streamlit_app.py
"""

import streamlit as st
import requests
import os
import json
from dotenv import load_dotenv
from groq import Groq

# ── Load environment variables ────────────────────────────────────────────────
load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
API_BASE_URL = "http://localhost:8000"          # FastAPI backend address
GROQ_API_KEY = os.getenv("GROQ_API_KEY")       # Groq key for LLM intent parsing

# ── Initialise Groq client (fail fast if key is missing) ─────────────────────
if not GROQ_API_KEY:
    st.error("GROQ_API_KEY not found. Add it to your .env file and restart.")
    st.stop()

groq_client = Groq(api_key=GROQ_API_KEY)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — THEME / STYLING
# We inject custom CSS to make Streamlit look like a professional enterprise app
# ─────────────────────────────────────────────────────────────────────────────

def apply_theme():
    """Inject custom CSS for the Microsoft Teams-inspired professional theme."""
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

        /* Apply Inter font everywhere */
        html, body, [class*="css"] {
            font-family: 'Inter', 'Segoe UI', system-ui, sans-serif !important;
        }

        /* Light grey page background */
        .stApp { background-color: #F5F5F5 !important; }

        /* Dark sidebar (Teams-style) */
        [data-testid="stSidebar"] {
            background-color: #201F1E !important;
            border-right: none !important;
        }
        [data-testid="stSidebar"] * { color: #C8C6C4 !important; }
        [data-testid="stSidebar"] hr {
            border-color: rgba(255,255,255,0.08) !important;
            margin: 10px 0 !important;
        }

        /* Sidebar brand block at the top */
        .sidebar-brand {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 16px 0 12px;
            border-bottom: 1px solid rgba(255,255,255,0.08);
            margin-bottom: 12px;
        }
        .sidebar-icon {
            width: 32px; height: 32px;
            background: #6264A7; border-radius: 6px;
            display: flex; align-items: center; justify-content: center;
        }
        .sidebar-title  { font-size: 14px; font-weight: 700; color: #FFF !important; }
        .sidebar-sub    { font-size: 11px; color: #A19F9D !important; }
        .sidebar-section {
            font-size: 10px !important; font-weight: 700 !important;
            letter-spacing: 0.1em !important; text-transform: uppercase !important;
            color: #A19F9D !important; padding: 10px 0 4px !important;
        }

        /* Purple action buttons */
        .stButton > button {
            background-color: #6264A7 !important; color: #FFF !important;
            border: none !important; border-radius: 4px !important;
            font-weight: 600 !important; font-size: 13px !important;
            transition: background 0.15s !important;
        }
        .stButton > button:hover {
            background-color: #464775 !important;
            box-shadow: 0 1px 4px rgba(0,0,0,0.2) !important;
        }

        /* Form inputs */
        .stTextInput > div > div > input {
            border-radius: 4px !important; border: 1px solid #D1D1D1 !important;
            font-size: 13px !important;
        }
        .stTextInput > div > div > input:focus {
            border-color: #6264A7 !important;
            box-shadow: 0 0 0 2px rgba(98,100,167,0.15) !important;
        }

        /* Chat message cards */
        [data-testid="stChatMessage"] {
            background: #FFF !important; border: 1px solid #E1DFDD !important;
            border-radius: 8px !important; padding: 12px 16px !important;
            margin-bottom: 8px !important; box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
        }

        /* Chat input bar */
        [data-testid="stChatInputTextArea"] {
            background: #FFF !important; border: 1px solid #D1D1D1 !important;
            border-radius: 6px !important; font-size: 13px !important;
        }

        /* Page header area */
        .page-header {
            background: #FFF; border-bottom: 1px solid #E1DFDD;
            padding: 16px 0 14px; margin-bottom: 20px;
        }
        .page-title   { font-size: 20px; font-weight: 700; color: #242424; margin: 0; }
        .page-subtitle{ font-size: 13px; color: #616161; margin: 2px 0 0; }

        /* Content width */
        .main .block-container { padding-top: 0 !important; max-width: 960px !important; }

        /* Hide Streamlit branding */
        #MainMenu { visibility: hidden; }
        footer     { visibility: hidden; }
        header     { visibility: hidden; }
        </style>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — API HELPERS
# These functions call the FastAPI backend (main.py) using the requests library.
# They are simple GET / POST / DELETE wrappers used throughout the app.
# ─────────────────────────────────────────────────────────────────────────────

def api_get(endpoint: str):
    """
    HTTP GET to the FastAPI backend.
    Returns the parsed JSON on success, or None on error.
    """
    try:
        r = requests.get(f"{API_BASE_URL}{endpoint}", timeout=10)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 401:
            st.warning("Session expired. Visit http://localhost:8000/auth/login to re-authenticate.")
        else:
            st.error(f"API error {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        st.error(f"Cannot reach backend: {e}")
        return None


def api_post(endpoint: str, payload: dict):
    """
    HTTP POST to the FastAPI backend with a JSON body.
    Returns the parsed JSON on success, or None on error.
    """
    try:
        r = requests.post(f"{API_BASE_URL}{endpoint}", json=payload, timeout=10)
        if r.status_code in (200, 201):
            return r.json()
        st.error(f"API error {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        st.error(f"Cannot reach backend: {e}")
        return None


def api_delete(endpoint: str) -> bool:
    """
    HTTP DELETE to the FastAPI backend.
    Returns True on success, False on error.
    """
    try:
        r = requests.delete(f"{API_BASE_URL}{endpoint}", timeout=10)
        if r.status_code in (200, 204):
            return True
        st.error(f"API error {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        st.error(f"Cannot reach backend: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — INTENT PARSING (AI Layer)
# We send the user's chat message to Groq (LLaMA 3) with a system prompt.
# The model returns structured JSON telling us what operation the user wants.
# ─────────────────────────────────────────────────────────────────────────────

def parse_intent(query: str) -> dict:
    """
    Call the Groq LLM to extract the user's intent and entities from free text.

    The system prompt instructs the model to return a strict JSON object with:
      - intent: one of the supported action names
      - entities: any named values extracted (project name, task name, etc.)
    """
    system_prompt = """
You are an AI assistant for Zoho Projects.
Parse the user's query into a structured intent.

Supported intents:
  LIST_PROJECTS   — user wants to see all projects
  LIST_TASKS      — user wants tasks for a project
  ADD_TASK        — user wants to create a new task
  UPDATE_TASK     — user wants to update task status or priority
  DELETE_TASK     — user wants to delete a task
  LIST_USERS      — user wants to see portal users
  ADD_USER        — user wants to add someone to a project
  GET_UTILIZATION — user wants to see who on the team is least busy

Return ONLY valid JSON in this exact shape:
{
    "intent": "INTENT_NAME",
    "entities": {
        "project_name": "",
        "task_name": "",
        "task_id": "",
        "priority": "",
        "status": "",
        "user_email": ""
    }
}
"""
    completion = groq_client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": query},
        ],
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"},
    )
    return json.loads(completion.choices[0].message.content)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — UTILITY HELPERS
# Small reusable functions used by both the sidebar and the chat processor.
# ─────────────────────────────────────────────────────────────────────────────

def get_projects() -> list:
    """Fetch the list of projects from the API. Returns [] if unavailable."""
    data = api_get("/projects")
    return data.get("projects", []) if data else []


def add_chat_message(role: str, content: str):
    """Append a message dict to the session state message list."""
    st.session_state.messages.append({"role": role, "content": content})


def quick_action(prompt: str):
    """
    Simulate the user typing a prompt, then immediately process it.
    Used by the sidebar quick-action buttons.
    """
    add_chat_message("user", prompt)
    process_chat_query(prompt)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — SIDEBAR
# The sidebar provides quick-action buttons and direct CRUD forms so users
# can perform operations without typing natural language.
# ─────────────────────────────────────────────────────────────────────────────

def render_sidebar():
    """Render the left sidebar with project selector and CRUD panels."""
    with st.sidebar:

        # ── Brand header ──────────────────────────────────────────────────
        st.markdown("""
            <div class="sidebar-brand">
                <div class="sidebar-icon">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2">
                        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                    </svg>
                </div>
                <div>
                    <div class="sidebar-title">Zoho Assistant</div>
                    <div class="sidebar-sub">Powered by Groq + LLaMA 3</div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        # ── Project selector (shared across all task panels) ──────────────
        # We load projects once here so all task actions know which project to use
        st.markdown('<div class="sidebar-section">Projects</div>', unsafe_allow_html=True)

        if st.button("List All Projects", use_container_width=True, key="btn_list_projects"):
            quick_action("List all my projects")

        st.markdown('<hr style="border-color:rgba(255,255,255,0.08);margin:10px 0"/>', unsafe_allow_html=True)

        # ── Task section ──────────────────────────────────────────────────
        st.markdown('<div class="sidebar-section">Tasks</div>', unsafe_allow_html=True)

        projects = get_projects()
        project_map = {p["name"]: p["id_string"] for p in projects}

        # Dropdown to pick which project the task actions apply to
        selected_name = st.selectbox(
            "Select Project",
            list(project_map.keys()),
            key="sidebar_project",
            label_visibility="collapsed",
        ) if project_map else None
        selected_id = project_map.get(selected_name) if selected_name else None

        # LIST TASKS button
        if st.button("List Tasks", use_container_width=True, key="btn_list_tasks"):
            if selected_id:
                quick_action(f"List tasks for project {selected_name}")
            else:
                st.warning("Select a project first.")

        # CREATE TASK form
        with st.expander("Create Task"):
            task_name = st.text_input("Task Name", key="new_task_name", placeholder="Enter task name...")
            task_priority = st.selectbox("Priority", ["None", "Low", "Medium", "High"], key="new_task_priority")
            if st.button("Create Task", key="create_task_btn", use_container_width=True):
                if task_name and selected_id:
                    # Call POST /projects/{id}/tasks
                    result = api_post(f"/projects/{selected_id}/tasks", {"name": task_name, "priority": task_priority})
                    if result:
                        add_chat_message("user", f"Create task '{task_name}' in {selected_name}")
                        add_chat_message("assistant", f"Task **'{task_name}'** created in **{selected_name}** with priority **{task_priority}**.")
                        st.rerun()
                else:
                    st.warning("Enter a task name and select a project.")

        # UPDATE TASK form
        with st.expander("Update Task"):
            update_id = st.text_input("Task ID", key="update_task_id", placeholder="e.g. 12345678")
            new_status = st.text_input("New Status", key="update_status", placeholder="e.g. In Progress")
            new_priority = st.selectbox("New Priority", ["None", "Low", "Medium", "High"], key="update_priority")
            if st.button("Update Task", key="update_task_btn", use_container_width=True):
                if update_id and selected_id:
                    # Build payload with only the fields that were filled in
                    payload = {}
                    if new_status:
                        payload["status"] = new_status
                    if new_priority and new_priority != "None":
                        payload["priority"] = new_priority
                    if payload:
                        result = api_post(f"/projects/{selected_id}/tasks/{update_id}/update", payload)
                        if result:
                            add_chat_message("user", f"Update task {update_id}")
                            add_chat_message("assistant", f"Task **{update_id}** updated successfully.")
                            st.rerun()
                    else:
                        st.warning("Provide at least one field to update.")
                else:
                    st.warning("Enter a Task ID and select a project.")

        # DELETE TASK form
        with st.expander("Delete Task"):
            delete_id = st.text_input("Task ID", key="delete_task_id", placeholder="e.g. 12345678")
            if st.button("Delete Task", key="delete_task_btn", use_container_width=True):
                if delete_id and selected_id:
                    # Call DELETE /projects/{id}/tasks/{task_id}
                    if api_delete(f"/projects/{selected_id}/tasks/{delete_id}"):
                        add_chat_message("user", f"Delete task {delete_id}")
                        add_chat_message("assistant", f"Task **{delete_id}** has been deleted from **{selected_name}**.")
                        st.rerun()
                else:
                    st.warning("Enter a Task ID and select a project.")

        st.markdown('<hr style="border-color:rgba(255,255,255,0.08);margin:10px 0"/>', unsafe_allow_html=True)

        # ── Users section ─────────────────────────────────────────────────
        st.markdown('<div class="sidebar-section">Users</div>', unsafe_allow_html=True)

        if st.button("List All Users", use_container_width=True, key="btn_list_users"):
            quick_action("List all users in the portal")

        with st.expander("Add User to Project"):
            user_email = st.text_input("Email Address", key="add_user_email", placeholder="user@example.com")
            if st.button("Add User", key="add_user_btn", use_container_width=True):
                if user_email and selected_id:
                    # Call POST /projects/{id}/users with JSON body
                    result = api_post(f"/projects/{selected_id}/users", {"email": user_email})
                    if result:
                        add_chat_message("user", f"Add user {user_email} to {selected_name}")
                        add_chat_message("assistant", f"User **{user_email}** added to **{selected_name}**.")
                        st.rerun()
                else:
                    st.warning("Enter an email and select a project.")

        st.markdown('<hr style="border-color:rgba(255,255,255,0.08);margin:10px 0"/>', unsafe_allow_html=True)

        # ── Utilization section ───────────────────────────────────────────
        st.markdown('<div class="sidebar-section">Team Utilization</div>', unsafe_allow_html=True)
        if st.button("Check Utilization", use_container_width=True, key="btn_utilization"):
            quick_action("Show me team utilization and who is least busy")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — INTENT PROCESSOR (Chat Handler)
# This is where the AI intent is mapped to real API actions.
# Each intent branch fetches/creates/updates/deletes data and formats a reply.
# ─────────────────────────────────────────────────────────────────────────────

def process_chat_query(prompt: str):
    """
    Core logic: parse the user's intent with Groq, then execute the matching
    API operation and display the result as an assistant chat message.
    """
    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("Processing your request...")

        # Step 1: Ask the LLM what the user wants
        parsed   = parse_intent(prompt)
        intent   = parsed.get("intent", "")
        entities = parsed.get("entities", {})
        reply    = ""

        # ── LIST_PROJECTS ─────────────────────────────────────────────────
        if intent == "LIST_PROJECTS":
            data = api_get("/projects")
            if data and "projects" in data:
                reply = "**Projects**\n\n"
                for p in data["projects"]:
                    reply += f"- **{p['name']}** — ID: `{p['id_string']}`\n"
            else:
                reply = "Could not retrieve projects. Make sure you are authenticated."

        # ── LIST_TASKS ────────────────────────────────────────────────────
        elif intent == "LIST_TASKS":
            proj_name = entities.get("project_name", "")
            projects  = get_projects()
            # Match the project name the user mentioned (or fall back to first)
            target = next(
                (p for p in projects if proj_name.lower() in p["name"].lower()),
                projects[0] if projects else None
            )
            if target:
                data = api_get(f"/tasks?project_id={target['id_string']}")
                if data and "tasks" in data:
                    reply = f"**Tasks — {target['name']}**\n\n"
                    for t in data["tasks"]:
                        status   = t.get("status", {}).get("name", "Open")
                        priority = t.get("priority", "None")
                        reply   += f"- **{t['name']}** `{t['id_string']}` · {status} · Priority: {priority}\n"
                else:
                    reply = f"No tasks found in **{target['name']}**."
            else:
                reply = "No projects found. Please authenticate first."

        # ── ADD_TASK (CREATE) ─────────────────────────────────────────────
        elif intent == "ADD_TASK":
            task_name = entities.get("task_name", "New Task")
            proj_name = entities.get("project_name", "")
            projects  = get_projects()
            target    = next(
                (p for p in projects if proj_name.lower() in p["name"].lower()),
                projects[0] if projects else None
            )
            if target:
                result = api_post(
                    f"/projects/{target['id_string']}/tasks",
                    {"name": task_name, "priority": entities.get("priority", "None")}
                )
                if result:
                    reply = f"Task **'{task_name}'** created in **{target['name']}**."
                else:
                    reply = "Failed to create the task. Check backend logs."
            else:
                reply = "No project found to create the task in."

        # ── UPDATE_TASK ───────────────────────────────────────────────────
        elif intent == "UPDATE_TASK":
            task_id  = entities.get("task_id", "")
            projects = get_projects()
            proj_name = entities.get("project_name", "")
            target   = next(
                (p for p in projects if proj_name.lower() in p["name"].lower()),
                projects[0] if projects else None
            )
            if task_id and target:
                payload = {}
                if entities.get("status"):
                    payload["status"]   = entities["status"]
                if entities.get("priority"):
                    payload["priority"] = entities["priority"]
                if payload:
                    result = api_post(f"/projects/{target['id_string']}/tasks/{task_id}/update", payload)
                    reply  = f"Task **{task_id}** updated." if result else "Update failed. Check the Task ID."
                else:
                    reply = "Provide the Task ID, and the new status or priority. Or use the **Update Task** panel in the sidebar."
            else:
                reply = "To update a task, please use the **Update Task** panel in the sidebar (fill in Task ID and select a project)."

        # ── DELETE_TASK ───────────────────────────────────────────────────
        elif intent == "DELETE_TASK":
            task_id  = entities.get("task_id", "")
            projects = get_projects()
            proj_name = entities.get("project_name", "")
            target   = next(
                (p for p in projects if proj_name.lower() in p["name"].lower()),
                projects[0] if projects else None
            )
            if task_id and target:
                success = api_delete(f"/projects/{target['id_string']}/tasks/{task_id}")
                reply   = f"Task **{task_id}** deleted." if success else "Deletion failed. Check the Task ID."
            else:
                reply = "To delete a task, please use the **Delete Task** panel in the sidebar (fill in Task ID and select a project)."

        # ── LIST_USERS ────────────────────────────────────────────────────
        elif intent == "LIST_USERS":
            data = api_get("/users")
            if data and "users" in data:
                reply = "**Portal Users**\n\n"
                for u in data["users"]:
                    name  = u.get("name") or u.get("full_name", "Unknown")
                    email = u.get("email", "")
                    reply += f"- **{name}** — {email}\n"
            else:
                reply = "Could not retrieve users."

        # ── ADD_USER ──────────────────────────────────────────────────────
        elif intent == "ADD_USER":
            reply = "To add a user, use the **Add User to Project** panel in the sidebar."

        # ── GET_UTILIZATION ───────────────────────────────────────────────
        elif intent == "GET_UTILIZATION":
            # Count open tasks per person across all projects
            projects = get_projects()
            if not projects:
                reply = "No projects found."
            else:
                utilization = {}  # { person_name: task_count }
                for proj in projects:
                    data = api_get(f"/tasks?project_id={proj['id_string']}")
                    if data and "tasks" in data:
                        for task in data["tasks"]:
                            for owner in task.get("details", {}).get("owners", []):
                                name = owner.get("name") or owner.get("full_name", "Unknown")
                                utilization[name] = utilization.get(name, 0) + 1

                if utilization:
                    sorted_util = sorted(utilization.items(), key=lambda x: x[1])
                    reply = "**Team Utilization — Open Task Count**\n\n"
                    for name, count in sorted_util:
                        # Simple ASCII bar chart
                        bar    = "█" * count + "░" * max(0, 10 - count)
                        reply += f"- **{name}**: {bar} {count} task(s)\n"
                    least_busy = sorted_util[0][0]
                    reply += f"\n**Recommendation:** {least_busy} has the lowest workload and is the best candidate for new tasks."
                else:
                    reply = "No task ownership data found. Tasks may not have assignees."

        # ── UNKNOWN INTENT ────────────────────────────────────────────────
        else:
            reply = (
                "I didn't understand that request. Try asking:\n"
                "- **List all projects**\n"
                "- **List tasks for [project name]**\n"
                "- **Create a task called [name]**\n"
                "- **Show team utilization**"
            )

        # Display the response and save it to message history
        placeholder.markdown(reply)
        add_chat_message("assistant", reply)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — MAIN APP ENTRY POINT
# This is where Streamlit renders the page, message history, and chat input.
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Main Streamlit app — sets up the page, sidebar, and chat interface."""

    # Page config must be the first Streamlit call
    st.set_page_config(
        page_title="Zoho Projects Assistant",
        page_icon="🗂️",
        layout="wide",
    )

    apply_theme()
    render_sidebar()

    # ── Page header ───────────────────────────────────────────────────────
    st.markdown("""
        <div class="page-header">
            <div class="page-title">Zoho Projects Assistant</div>
            <div class="page-subtitle">AI-powered project management &nbsp;·&nbsp; Groq + LLaMA 3</div>
        </div>
    """, unsafe_allow_html=True)

    # ── Initialise chat history in session state ───────────────────────────
    # st.session_state persists across reruns within the same browser session
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "Hello! I'm your Zoho Projects Assistant.\n\n"
                    "You can ask me things like:\n"
                    "- *List all projects*\n"
                    "- *Show tasks for [project name]*\n"
                    "- *Create a task called [name]*\n"
                    "- *Who is least busy on the team?*\n\n"
                    "Or use the quick-action panels in the sidebar for direct CRUD operations."
                ),
            }
        ]

    # ── Render existing chat messages ──────────────────────────────────────
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── Chat input — triggers on Enter or click ────────────────────────────
    if prompt := st.chat_input("Type your question — e.g. 'List all projects' or 'Who is least busy?'"):
        # Show the user's message immediately
        add_chat_message("user", prompt)
        with st.chat_message("user"):
            st.markdown(prompt)
        # Then process it and show the assistant's reply
        process_chat_query(prompt)


# Entry point
if __name__ == "__main__":
    main()