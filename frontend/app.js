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

// Wait for the entire HTML document to load before running our JS
document.addEventListener('DOMContentLoaded', () => {

    // ── DOM references ──────────────────────────────────────────────────────
    // Get references to main table areas and structural elements
    const tasksContainer  = document.getElementById('tasks-container');
    const tasksTbody      = document.getElementById('tasks-tbody');
    const loader          = document.getElementById('loader');
    const refreshBtn      = document.getElementById('refresh-btn');
    const projectSelect   = document.getElementById('project-select');

    // Get references for the 'Create Task' modal
    const createTaskBtn   = document.getElementById('create-task-btn');
    const taskModal       = document.getElementById('task-modal');
    const modalCloseBtn   = document.getElementById('modal-close-btn');
    const cancelTaskBtn   = document.getElementById('cancel-task-btn');
    const submitTaskBtn   = document.getElementById('submit-task-btn');
    const newTaskName     = document.getElementById('new-task-name');
    const newTaskPriority = document.getElementById('new-task-priority');

    // Get references for the Floating Chat Widget
    const chatFab         = document.getElementById('chat-fab');
    const chatPanel       = document.getElementById('chat-panel');
    const closeChatBtn    = document.getElementById('close-chat');
    const chatInput       = document.getElementById('chat-input');
    const sendBtn         = document.getElementById('send-btn');
    const chatBody        = document.getElementById('chat-body');


    // ── SECTION B: Load Projects ────────────────────────────────────────────
    // Fetches all projects from GET /projects and populates the dropdown.
    // After loading, automatically loads tasks for the first project.

    async function loadProjects() {
        try {
            // Call our backend API to list all projects the user can access
            const res = await fetch('/projects');

            // If the token expired, redirect user to the OAuth login flow
            if (res.status === 401) {
                window.location.href = '/auth/login';
                return;
            }
            // If any other error occurs, throw an exception
            if (!res.ok) throw new Error(await res.text());

            // Extract the list of projects from the API response
            const data     = await res.json();
            const projects = data.projects || [];

            // Clear the existing dropdown values
            projectSelect.innerHTML = '';

            // If no projects exist, tell the user
            if (projects.length === 0) {
                projectSelect.innerHTML = '<option value="">No projects found</option>';
                return;
            }

            // Loop over every project and create an <option> to add to the HTML Select menu
            projects.forEach(proj => {
                const opt       = document.createElement('option');
                opt.value       = proj.id_string;
                opt.textContent = proj.name;
                projectSelect.appendChild(opt);
            });

            // Load tasks for whichever project was selected by default the first time
            loadTasks();

        } catch (err) {
            console.error('loadProjects error:', err);
            projectSelect.innerHTML = '<option value="">Error loading projects</option>';
        }
    }

    // Add an event listener to reload tasks if the user picks a different project
    projectSelect.addEventListener('change', loadTasks);


    // ── SECTION C: Load Tasks ───────────────────────────────────────────────
    // Fetches tasks for the selected project from GET /tasks?project_id=...
    // Shows a spinner while loading, then calls renderTasks().

    async function loadTasks() {
        // Find out which project the user currently has selected
        const projectId = projectSelect.value;
        if (!projectId) return;

        // Show a loading spinner and hide the table so the user knows it's loading
        loader.innerHTML = '<div class="loader-spinner"></div><p>Loading tasks...</p>';
        loader.classList.remove('hidden');
        tasksContainer.classList.add('hidden');

        try {
            // Ask the backend for all tasks matching the selected project
            const res = await fetch(`/tasks?project_id=${projectId}`);
            if (!res.ok) throw new Error(await res.text());

            // Get the list of tasks from the response payload
            const data        = await res.json();
            const tasks       = data.tasks || [];
            // Retrieve the project name for display purposes in the UI
            const projectName = projectSelect.options[projectSelect.selectedIndex]?.text || '';

            // Send the raw data to `renderTasks` to actually build the HTML table rows
            renderTasks(tasks, projectName);

        } catch (err) {
            // Handle errors by updating the UI loader box to show a red error icon and message
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

    // Let the user force a reload by clicking the refresh button
    refreshBtn.addEventListener('click', loadTasks);


    // ── SECTION D: Render Tasks ─────────────────────────────────────────────
    // Takes an array of task objects from the Zoho API and builds the HTML
    // table rows. Also attaches delete button listeners on each row.

    function renderTasks(tasks, projectName) {
        // Clear any previous items in the HTML table body
        tasksTbody.innerHTML = '';

        // If the project doesn't have any tasks, inform the user with a nice placeholder state
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

        // Loop over every single task loaded from the backend
        tasks.forEach(task => {
            // Apply priority css classifications (None, Low, Medium, High)
            const priorityClass = `priority-${(task.priority || 'none').toLowerCase()}`;
            // Determine the progress bar completion state
            const percent       = task.percent_complete || 0;
            // Get the color Zoho assigns to the status, default to grey
            const colorCode     = task.status?.color_code || '#c8c6c4';
            // Determine progress bar color based on 100% vs partial
            const progressColor = percent === 100 ? '#107c10' : '#6264a7';

            // Owner logic — Zoho provides owners in an array format inside task.details
            let ownerName = '—';
            if (task.details?.owners?.length > 0) {
                // Try grabbing the 'name' or 'full_name' properties safely
                ownerName = task.details.owners[0].name
                         || task.details.owners[0].full_name
                         || '—';
            }

            // Prepare inline tags / labels if any exist
            let tagsHtml = '—';
            if (Array.isArray(task.tags) && task.tags.length > 0) {
                tagsHtml = task.tags
                    .map(t => `<span class="task-badge" style="background:#f3f2f1;color:#605e5c;font-size:10px">${t.name}</span>`)
                    .join(' ');
            }

            // Create 1-2 letter initial representation for the user's avatar icon based on their name
            const initials = ownerName !== '—'
                ? ownerName.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
                : '?';

            // Build the row (<tr>) element and inject column data (<td>)
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
                <td class="action-col">
                    <button class="danger-btn delete-task-btn" data-id="${task.id_string}">Delete</button>
                </td>`;

            // Append the row to the table body
            tasksTbody.appendChild(tr);
        });

        // Hide the loader, reveal the tasks table container now that data is populated
        loader.classList.add('hidden');
        tasksContainer.classList.remove('hidden');

        // ── SECTION D1: Delete Task ─────────────────────────────────────────
        // Attaches a click listener to every "Delete" button in the newly generated table.
        // Calls DELETE /projects/{id}/tasks/{task_id} on confirmation.
        document.querySelectorAll('.delete-task-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                // Get the task ID encoded in HTML data-id attribute
                const taskId    = e.target.getAttribute('data-id');
                // Target the currently selected project
                const projectId = projectSelect.value;

                // Stop the operation if user cancels the native pop-up dialogue
                if (!confirm('Delete this task? This action cannot be undone.')) return;

                try {
                    // Start an HTTP DELETE request linking back to backend FastAPI
                    const res = await fetch(`/projects/${projectId}/tasks/${taskId}`, { method: 'DELETE' });
                    if (!res.ok) throw new Error(await res.text());
                    // If successful, reload tasks from scratch to accurately reflect removal
                    loadTasks();
                } catch (err) {
                    // Show a Javascript alert with the error message
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
        // Reset the form fields right as the Modal is about to be displayed
        newTaskName.value = '';        // clear previous input
        newTaskPriority.value = 'None';
        // Make modal visible by removing 'hidden' CSS class
        taskModal.classList.remove('hidden');
        newTaskName.focus();
    });

    // Both the X Button and the "Cancel" Button share this logic to hide the Modal
    [cancelTaskBtn, modalCloseBtn].forEach(btn => {
        btn.addEventListener('click', () => taskModal.classList.add('hidden'));
    });

    // When clicking "Create Task" inside the modal, proceed with the API call
    submitTaskBtn.addEventListener('click', async () => {
        const name = newTaskName.value.trim();
        // Validation check to enforce that task names aren't empty
        if (!name) {
            alert('Task name is required.');
            return;
        }

        const priority  = newTaskPriority.value;
        const projectId = projectSelect.value;

        // Briefly change button text to simulate a loading state
        submitTaskBtn.textContent = 'Creating...';
        submitTaskBtn.disabled    = true; // prevent the user from clicking the submit twice accidentally

        try {
            // POST /projects/{project_id}/tasks - Creating the actual REST API Payload
            const res = await fetch(`/projects/${projectId}/tasks`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ name, priority }),
            });
            if (!res.ok) throw new Error(await res.text());

            // If it succeeds, hide the modal and force refresh the list
            taskModal.classList.add('hidden');
            loadTasks();    
        } catch (err) {
            // Issue alert pointing out failure mechanism (like token expiration, invalid param)
            alert('Failed to create task: ' + err.message);
        } finally {
            // Revert the button to its normal operational state
            submitTaskBtn.textContent = 'Create Task';
            submitTaskBtn.disabled    = false;
        }
    });


    // ── SECTION F: Chat Widget ──────────────────────────────────────────────
    // A floating chat button opens a panel allowing interaction with Groq/LLM engine.

    // Store dialogue locally as JSON object array so the LLM retains context locally.
    let chatHistory = [];

    // Tapping the bottom right FAB circle reveals the floating message window.
    chatFab.addEventListener('click', () => {
        chatPanel.classList.toggle('hidden');
        // Auto focus the input automatically if the window just appeared
        if (!chatPanel.classList.contains('hidden')) chatInput.focus();
    });

    // Allow user to manually collapse chat window using top right X
    closeChatBtn.addEventListener('click', () => chatPanel.classList.add('hidden'));

    // This utility function generates HTML dynamically for any bubble type block (User or AI)
    function createMsgElement(text, isUser, options) {
        const msgDiv     = document.createElement('div');
        msgDiv.className = `message ${isUser ? 'user-message' : 'ai-message'}`;

        const avatarDiv     = document.createElement('div');
        avatarDiv.className = 'msg-avatar';
        avatarDiv.textContent = isUser ? 'ME' : 'AI';

        const contentDiv     = document.createElement('div');
        contentDiv.className = 'msg-content';

        const senderSpan     = document.createElement('span');
        senderSpan.className = 'msg-sender';
        senderSpan.textContent = isUser ? 'You' : 'Zoho AI Assistant';

        const textP     = document.createElement('p');
        // Replace typical \n return commands with linebreaks for HTML output
        textP.innerHTML = text.replace(/\n/g, '<br>');

        contentDiv.appendChild(senderSpan);
        contentDiv.appendChild(textP);
        
        // When AI decides asking for user validation via JSON payload...
        if (options && options.length > 0) {
            const optionsContainer = document.createElement('div');
            optionsContainer.className = 'chat-options-container';
            // Render interactive user JSON buttons representing API options available
            options.forEach(opt => {
                const btn = document.createElement('button');
                btn.className = 'chat-option-btn';
                btn.textContent = opt.label;
                btn.addEventListener('click', () => {
                    handleSend(opt.value || opt.label);
                });
                optionsContainer.appendChild(btn);
            });
            contentDiv.appendChild(optionsContainer);
        }

        // Attach elements up the tree and push back to render stack
        msgDiv.appendChild(avatarDiv);
        msgDiv.appendChild(contentDiv);
        return msgDiv;
    }

    // Handles injecting messages onto the UI properly and forcing the camera constraint downwards
    function addMessage(text, isUser = false, options = null) {
        const msgDiv = createMsgElement(text, isUser, options);
        chatBody.appendChild(msgDiv);
        // Ensure scroll forces to latest sent element automatically in chat frame
        chatBody.scrollTop = chatBody.scrollHeight;
    }

    // Processing event responsible for pushing traffic to LLM service via backend endpoint structure
    async function handleSend(forcedText = null) {
        const text = typeof forcedText === 'string' ? forcedText : chatInput.value.trim();
        // If chat payload was totally empty don't route out dummy API queries
        if (!text) return;

        // Inject the sent user command onto the UI explicitly
        addMessage(text, true);
        if (typeof forcedText !== 'string') chatInput.value = '';

        // Push input text structurally to backend for contextual reasoning 
        chatHistory.push({ role: 'user', content: text });

        // Show a brief '...' status window allowing User to see visual loading indication
        const loadingId = 'loading-' + Date.now();
        const msgDiv = createMsgElement('...', false);
        msgDiv.id = loadingId;
        chatBody.appendChild(msgDiv);
        chatBody.scrollTop = chatBody.scrollHeight;

        try {
            // Forward payload string array up into /chat FastAPI pipeline
            const res = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ messages: chatHistory })
            });
            if (!res.ok) throw new Error('API Error');
            const data = await res.json();

            // Destroy interim wait indication completely.
            document.getElementById(loadingId)?.remove();

            // Maintain history record
            chatHistory.push({ role: 'assistant', content: data.content });

            let responseContent = data.content;
            let options = null;
            // The AI acts conversational, but pushes JSON blocks via regex markdown syntax to trigger UI selections
            const jsonMatch = responseContent.match(/```json\s*([\s\S]*?)\s*```/);
            // Safely parse JSON structure to generate buttons natively if provided by the assistant model
            if (jsonMatch) {
                try {
                    const parsed = JSON.parse(jsonMatch[1]);
                    if (parsed.options) {
                        options = parsed.options;
                        responseContent = responseContent.replace(jsonMatch[0], '').trim();
                    }
                } catch(e) {}
            }

            // Put formatted message completely on DOM window 
            addMessage(responseContent || "Done.", false, options);
            
            // Auto refresh task table silently just assuming user generated/deleted items 
            loadTasks();
            
        } catch (err) {
            // Failsafe condition in case Model pipeline or groq interface completely falls off sync
            document.getElementById(loadingId)?.remove();
            addMessage('Error: Cannot reach assistant.', false);
        }
    }

    // Register basic input bindings such as pressing standard enter resolving user payload submission
    sendBtn.addEventListener('click', handleSend);
    chatInput.addEventListener('keypress', e => {
        if (e.key === 'Enter') handleSend();
    });


    // ── Initialise the page ─────────────────────────────────────────────────
    loadProjects();      // Fetch projects from API and then auto-load tasks
});