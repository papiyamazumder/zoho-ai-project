/**
 * app.js — Vanilla JS Frontend for Zoho Projects Task Hub
 * --------------------------------------------------------
 * This file powers the interactive task table at http://localhost:8000/app
 *
 * Responsibilities:
 *   1. Load projects from the FastAPI backend and populate the dropdown
 *   2. Load tasks for the selected project and render them in a table
 *   3. Handle task creation via a modal form (Admin role only)
 *   4. Handle task deletion with a confirm dialog (Admin role only)
 *   5. Persona toggle (Developer vs Admin) to show/hide admin controls
 *   6. AI chat widget — sends messages to the Streamlit assistant
 *
 * All API calls go to http://localhost:8000 (same origin when served via /app)
 */

document.addEventListener('DOMContentLoaded', () => {

    // ── DOM references ──────────────────────────────────────────────────────
    const tasksContainer  = document.getElementById('tasks-container');
    const tasksTbody      = document.getElementById('tasks-tbody');
    const loader          = document.getElementById('loader');
    const refreshBtn      = document.getElementById('refresh-btn');
    const projectSelect   = document.getElementById('project-select');
    const personaSelect   = document.getElementById('persona-select');

    // Create-task modal elements
    const createTaskBtn   = document.getElementById('create-task-btn');
    const taskModal       = document.getElementById('task-modal');
    const modalCloseBtn   = document.getElementById('modal-close-btn');
    const cancelTaskBtn   = document.getElementById('cancel-task-btn');
    const submitTaskBtn   = document.getElementById('submit-task-btn');
    const newTaskName     = document.getElementById('new-task-name');
    const newTaskPriority = document.getElementById('new-task-priority');

    // Chat widget elements
    const chatFab         = document.getElementById('chat-fab');
    const chatPanel       = document.getElementById('chat-panel');
    const closeChatBtn    = document.getElementById('close-chat');
    const chatInput       = document.getElementById('chat-input');
    const sendBtn         = document.getElementById('send-btn');
    const chatBody        = document.getElementById('chat-body');


    // ── SECTION A: Persona toggle ───────────────────────────────────────────
    // The persona selector switches between "Developer" (read-only) and
    // "Admin" (can create/delete tasks). Admin-only elements are toggled.

    function updatePersonaUI() {
        const isAdmin = personaSelect.value === 'admin';
        document.querySelectorAll('.admin-only').forEach(el => {
            el.classList.toggle('hidden', !isAdmin);
        });
    }

    personaSelect.addEventListener('change', updatePersonaUI);


    // ── SECTION B: Load Projects ────────────────────────────────────────────
    // Fetches all projects from GET /projects and populates the dropdown.
    // After loading, automatically loads tasks for the first project.

    async function loadProjects() {
        try {
            const res = await fetch('/projects');

            // If the token expired, redirect to OAuth login
            if (res.status === 401) {
                window.location.href = '/auth/login';
                return;
            }
            if (!res.ok) throw new Error(await res.text());

            const data     = await res.json();
            const projects = data.projects || [];

            projectSelect.innerHTML = '';

            if (projects.length === 0) {
                projectSelect.innerHTML = '<option value="">No projects found</option>';
                return;
            }

            // Build one <option> per project
            projects.forEach(proj => {
                const opt       = document.createElement('option');
                opt.value       = proj.id_string;
                opt.textContent = proj.name;
                projectSelect.appendChild(opt);
            });

            // Load tasks for whichever project is selected by default
            loadTasks();

        } catch (err) {
            console.error('loadProjects error:', err);
            projectSelect.innerHTML = '<option value="">Error loading projects</option>';
        }
    }

    // Reload tasks whenever the user changes the project dropdown
    projectSelect.addEventListener('change', loadTasks);


    // ── SECTION C: Load Tasks ───────────────────────────────────────────────
    // Fetches tasks for the selected project from GET /tasks?project_id=...
    // Shows a spinner while loading, then calls renderTasks().

    async function loadTasks() {
        const projectId = projectSelect.value;
        if (!projectId) return;

        // Show loading spinner, hide table
        loader.innerHTML = '<div class="loader-spinner"></div><p>Loading tasks...</p>';
        loader.classList.remove('hidden');
        tasksContainer.classList.add('hidden');

        try {
            const res = await fetch(`/tasks?project_id=${projectId}`);
            if (!res.ok) throw new Error(await res.text());

            const data        = await res.json();
            const tasks       = data.tasks || [];
            const projectName = projectSelect.options[projectSelect.selectedIndex]?.text || '';

            renderTasks(tasks, projectName);

        } catch (err) {
            console.error('loadTasks error:', err);
            loader.innerHTML = `
                <div style="color:#c50f1f;text-align:center;padding:40px">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                         width="32" height="32" style="margin-bottom:12px;opacity:0.6">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M12 8v4M12 16h.01"/>
                    </svg>
                    <p style="font-weight:600;margin-bottom:4px">Failed to load tasks</p>
                    <small style="color:#616161">${err.message}</small>
                </div>`;
        }
    }

    refreshBtn.addEventListener('click', loadTasks);


    // ── SECTION D: Render Tasks ─────────────────────────────────────────────
    // Takes an array of task objects from the Zoho API and builds the HTML
    // table rows. Also attaches delete button listeners on each row.

    function renderTasks(tasks, projectName) {
        tasksTbody.innerHTML = '';

        // Handle empty state
        if (tasks.length === 0) {
            loader.innerHTML = `
                <div style="text-align:center;color:#616161;padding:60px 0">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"
                         width="40" height="40" style="margin-bottom:12px;opacity:0.4">
                        <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2
                                 M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
                    </svg>
                    <p style="font-weight:600">No tasks found in this project</p>
                </div>`;
            loader.classList.remove('hidden');
            return;
        }

        tasks.forEach(task => {
            // Extract values safely (Zoho API may omit fields)
            const priorityClass = `priority-${(task.priority || 'none').toLowerCase()}`;
            const percent       = task.percent_complete || 0;
            const colorCode     = task.status?.color_code || '#c8c6c4';
            const progressColor = percent === 100 ? '#107c10' : '#6264a7';

            // Owner — Zoho nests owner info inside task.details.owners
            let ownerName = '—';
            if (task.details?.owners?.length > 0) {
                ownerName = task.details.owners[0].name
                         || task.details.owners[0].full_name
                         || '—';
            }

            // Tags / labels
            let tagsHtml = '—';
            if (Array.isArray(task.tags) && task.tags.length > 0) {
                tagsHtml = task.tags
                    .map(t => `<span class="task-badge" style="background:#f3f2f1;color:#605e5c;font-size:10px">${t.name}</span>`)
                    .join(' ');
            }

            // Avatar initials (first letter of each word, max 2 chars)
            const initials = ownerName !== '—'
                ? ownerName.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
                : '?';

            // Build the table row
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><span class="task-id">${task.key || task.id_string}</span></td>
                <td class="task-name-cell">${task.name}</td>
                <td>
                    <span class="task-badge" style="background:#ede9f8;color:#6264a7;font-size:11px">
                        ${projectName}
                    </span>
                </td>
                <td>
                    <div style="display:flex;align-items:center;gap:6px">
                        <div style="width:22px;height:22px;border-radius:50%;background:#0078d4;
                                    color:white;font-size:9px;font-weight:700;display:flex;
                                    align-items:center;justify-content:center;flex-shrink:0">
                            ${initials}
                        </div>
                        <span style="color:#242424;font-weight:500">${ownerName}</span>
                    </div>
                </td>
                <td>
                    <div class="task-status">
                        <span class="status-dot" style="background-color:${colorCode}"></span>
                        <span>${task.status?.name || 'Open'}</span>
                    </div>
                </td>
                <td>${tagsHtml}</td>
                <td style="white-space:nowrap;font-size:12px">${task.start_date_format || '—'}</td>
                <td style="white-space:nowrap;font-size:12px">${task.end_date_format   || '—'}</td>
                <td style="font-size:12px">${task.duration ? task.duration + ' days' : '—'}</td>
                <td><span class="task-badge ${priorityClass}">${task.priority || 'None'}</span></td>
                <td>
                    <div style="min-width:90px">
                        <span class="progress-label">${percent}%</span>
                        <div class="progress-container">
                            <div class="progress-bar" style="width:${percent}%;background-color:${progressColor}"></div>
                        </div>
                    </div>
                </td>
                <td style="font-size:12px;color:#616161">${task.work || '0:00'}</td>
                <td class="action-col admin-only ${personaSelect.value === 'admin' ? '' : 'hidden'}">
                    <button class="danger-btn delete-task-btn" data-id="${task.id_string}">Delete</button>
                </td>`;

            tasksTbody.appendChild(tr);
        });

        loader.classList.add('hidden');
        tasksContainer.classList.remove('hidden');

        // ── SECTION D1: Delete Task ─────────────────────────────────────────
        // Attaches a click listener to every "Delete" button in the table.
        // Calls DELETE /projects/{id}/tasks/{task_id} on confirmation.
        document.querySelectorAll('.delete-task-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const taskId    = e.target.getAttribute('data-id');
                const projectId = projectSelect.value;

                if (!confirm('Delete this task? This action cannot be undone.')) return;

                try {
                    const res = await fetch(`/projects/${projectId}/tasks/${taskId}`, { method: 'DELETE' });
                    if (!res.ok) throw new Error(await res.text());
                    // Reload the task list to reflect the deletion
                    loadTasks();
                } catch (err) {
                    alert('Failed to delete task: ' + err.message);
                }
            });
        });
    }


    // ── SECTION E: Create Task Modal ────────────────────────────────────────
    // Opens a modal form when the Admin clicks "New Task".
    // Submits POST /projects/{id}/tasks with { name, priority }.

    createTaskBtn.addEventListener('click', () => {
        if (!projectSelect.value) {
            alert('Select a project before creating a task.');
            return;
        }
        newTaskName.value = '';        // clear previous input
        newTaskPriority.value = 'None';
        taskModal.classList.remove('hidden');
        newTaskName.focus();
    });

    // Close modal on Cancel or X button
    [cancelTaskBtn, modalCloseBtn].forEach(btn => {
        btn.addEventListener('click', () => taskModal.classList.add('hidden'));
    });

    submitTaskBtn.addEventListener('click', async () => {
        const name = newTaskName.value.trim();
        if (!name) {
            alert('Task name is required.');
            return;
        }

        const priority  = newTaskPriority.value;
        const projectId = projectSelect.value;

        // Show loading state on the button to prevent double-submit
        submitTaskBtn.textContent = 'Creating...';
        submitTaskBtn.disabled    = true;

        try {
            // POST /projects/{project_id}/tasks
            const res = await fetch(`/projects/${projectId}/tasks`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ name, priority }),
            });
            if (!res.ok) throw new Error(await res.text());

            taskModal.classList.add('hidden');
            loadTasks();    // Refresh the table to show the new task
        } catch (err) {
            alert('Failed to create task: ' + err.message);
        } finally {
            submitTaskBtn.textContent = 'Create Task';
            submitTaskBtn.disabled    = false;
        }
    });


    // ── SECTION F: Chat Widget ──────────────────────────────────────────────
    // A floating chat button opens a panel.
    // Messages are forwarded to the Streamlit AI assistant running on port 8501.
    // This is a simple redirect — the full LLM-powered chat lives in Streamlit.

    chatFab.addEventListener('click', () => {
        chatPanel.classList.toggle('hidden');
        if (!chatPanel.classList.contains('hidden')) chatInput.focus();
    });

    closeChatBtn.addEventListener('click', () => chatPanel.classList.add('hidden'));

    /**
     * Adds a message bubble to the chat panel.
     * @param {string}  text   - The message text to display
     * @param {boolean} isUser - true = right-aligned user bubble, false = AI bubble
     */
    function addMessage(text, isUser = false) {
        const msgDiv     = document.createElement('div');
        msgDiv.className = `message ${isUser ? 'user-message' : 'ai-message'}`;

        const avatarDiv     = document.createElement('div');
        avatarDiv.className = 'msg-avatar';
        avatarDiv.textContent = isUser ? 'ME' : 'AI';

        const contentDiv     = document.createElement('div');
        contentDiv.className = 'msg-content';

        const senderSpan     = document.createElement('span');
        senderSpan.className = 'msg-sender';
        senderSpan.textContent = isUser ? 'You' : 'Zoho Assistant';

        const textP     = document.createElement('p');
        textP.textContent = text;

        contentDiv.appendChild(senderSpan);
        contentDiv.appendChild(textP);
        msgDiv.appendChild(avatarDiv);
        msgDiv.appendChild(contentDiv);
        chatBody.appendChild(msgDiv);
        chatBody.scrollTop = chatBody.scrollHeight;
    }

    function handleSend() {
        const text = chatInput.value.trim();
        if (!text) return;

        addMessage(text, true);
        chatInput.value = '';

        // Inform user that the full AI assistant is in Streamlit
        // (The LLM chat is powered by Groq in streamlit_app.py on port 8501)
        setTimeout(() => {
            addMessage(
                'For full AI-powered responses, open the Streamlit Assistant at ' +
                'http://localhost:8501 — it uses Groq + LLaMA 3 for natural language task management.'
            );
        }, 500);
    }

    sendBtn.addEventListener('click', handleSend);
    chatInput.addEventListener('keypress', e => {
        if (e.key === 'Enter') handleSend();
    });


    // ── Initialise the page ─────────────────────────────────────────────────
    updatePersonaUI();   // Apply correct visibility based on default persona
    loadProjects();      // Fetch projects from API and then auto-load tasks

});