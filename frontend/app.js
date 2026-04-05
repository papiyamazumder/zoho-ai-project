document.addEventListener('DOMContentLoaded', () => {
    const tasksContainer = document.getElementById('tasks-container');
    const tasksTbody = document.getElementById('tasks-tbody');
    const loader = document.getElementById('loader');
    const refreshBtn = document.getElementById('refresh-btn');
    const projectSelect = document.getElementById('project-select');
    const personaSelect = document.getElementById('persona-select');

    // Create Task Modal Elements
    const createTaskBtn = document.getElementById('create-task-btn');
    const taskModal = document.getElementById('task-modal');
    const cancelTaskBtn = document.getElementById('cancel-task-btn');
    const submitTaskBtn = document.getElementById('submit-task-btn');
    const newTaskName = document.getElementById('new-task-name');
    const newTaskPriority = document.getElementById('new-task-priority');

    // Persona Change Logic
    function updatePersonaUI() {
        const isAdmin = personaSelect.value === 'admin';
        document.querySelectorAll('.admin-only').forEach(el => {
            if (isAdmin) el.classList.remove('hidden');
            else el.classList.add('hidden');
        });
    }
    personaSelect.addEventListener('change', updatePersonaUI);

    // Chatbot Elements
    const chatFab = document.getElementById('chat-fab');
    const chatPanel = document.getElementById('chat-panel');
    const closeChatBtn = document.getElementById('close-chat');
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const chatBody = document.getElementById('chat-body');

    // Fetch Projects
    async function loadProjects() {
        try {
            const response = await fetch('/projects');
            if (response.status === 401) {
                // Instantly redirect them to login if token is missing
                window.location.href = '/auth/login';
                return;
            }
            if (!response.ok) throw new Error(await response.text());
            
            const data = await response.json();
            const projects = data.projects || [];
            
            projectSelect.innerHTML = '';
            if (projects.length === 0) {
                projectSelect.innerHTML = '<option value="">No projects found.</option>';
                return;
            }

            projects.forEach(proj => {
                const opt = document.createElement('option');
                opt.value = proj.id_string;
                opt.textContent = proj.name;
                projectSelect.appendChild(opt);
            });

            // Automatically load tasks for the first project
            loadTasks();
        } catch (error) {
            console.error('Error fetching projects:', error);
            projectSelect.innerHTML = '<option value="">Error loading</option>';
        }
    }

    projectSelect.addEventListener('change', loadTasks);

    // Fetch Tasks
    async function loadTasks() {
        const projectId = projectSelect.value;
        if (!projectId) return;

        loader.classList.remove('hidden');
        tasksContainer.classList.add('hidden');
        
        try {
            const response = await fetch(`/tasks?project_id=${projectId}`);
            
            if (!response.ok) throw new Error(await response.text());

            const data = await response.json();
            const tasks = data.tasks || [];
            
            const projectName = projectSelect.options[projectSelect.selectedIndex]?.text || '-';
            renderTasks(tasks, projectName);
        } catch (error) {
            console.error('Error fetching tasks:', error);
            loader.innerHTML = `
                <div style="color: var(--danger)">
                    Failed to load tasks. Check if backend is running or token is valid.<br>
                    <small>${error.message}</small>
                </div>`;
        }
    }

    function renderTasks(tasks, projectName) {
        tasksTbody.innerHTML = '';
        
        if (tasks.length === 0) {
            loader.innerHTML = 'No tasks found in this project.';
            return;
        }

        tasks.forEach(task => {
            const priorityClass = `priority-${(task.priority || 'none').toLowerCase()}`;
            const percent = task.percent_complete || 0;
            const colorCode = task.status?.color_code || '#cbd5e1';
            
            let ownerName = '-';
            if (task.details && task.details.owners && task.details.owners.length > 0) {
                ownerName = task.details.owners[0].name || task.details.owners[0].full_name || '-';
            }
            
            let tagsHtml = '-';
            if (task.tags && Array.isArray(task.tags) && task.tags.length > 0) {
                tagsHtml = task.tags.map(t => `<span class="task-badge" style="background:#334155;color:#cbd5e1;padding:2px 6px;">${t.name}</span>`).join(' ');
            }

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="task-id">${task.key || task.id_string}</td>
                <td class="task-name-cell">${task.name}</td>
                <td><span class="task-badge" style="background:rgba(255,255,255,0.1); color:var(--text-primary); text-transform:none;">${projectName}</span></td>
                <td>${ownerName}</td>
                <td>
                    <div class="task-status">
                        <span class="status-dot" style="background-color: ${colorCode}"></span>
                        <span>${task.status?.name || 'Open'}</span>
                    </div>
                </td>
                <td>${tagsHtml}</td>
                <td>${task.start_date_format || '-'}</td>
                <td>${task.end_date_format || '-'}</td>
                <td>${task.duration ? task.duration + ' days' : '-'}</td>
                <td><span class="task-badge ${priorityClass}">${task.priority || 'None'}</span></td>
                <td>
                    <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 0.2rem">
                        ${percent}%
                    </div>
                    <div class="progress-container">
                        <div class="progress-bar" style="width: ${percent}%; background-color: ${percent == 100 ? 'var(--success)' : 'var(--accent-color)'}"></div>
                    </div>
                </td>
                <td>${task.work || '0:00'}</td>
                <td class="action-col admin-only ${personaSelect.value === 'admin' ? '' : 'hidden'}">
                    <button class="btn danger-btn delete-task-btn" data-id="${task.id_string}">Delete</button>
                </td>
            `;
            tasksTbody.appendChild(tr);
        });

        loader.classList.add('hidden');
        tasksContainer.classList.remove('hidden');

        // Attach Delete Listeners
        document.querySelectorAll('.delete-task-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const taskId = e.target.getAttribute('data-id');
                const projectId = projectSelect.value;
                if(confirm("Are you sure you want to delete this task? This action cannot be undone.")) {
                    try {
                        const res = await fetch(`/projects/${projectId}/tasks/${taskId}`, { method: 'DELETE' });
                        if(!res.ok) throw new Error(await res.text());
                        loadTasks();
                    } catch(err) {
                        alert('Error deleting task: ' + err.message);
                    }
                }
            });
        });
    }

    refreshBtn.addEventListener('click', loadTasks);

    // Modal Interaction Logic
    createTaskBtn.addEventListener('click', () => {
        if(!projectSelect.value) return alert("Please select a project first!");
        newTaskName.value = '';
        taskModal.classList.remove('hidden');
        newTaskName.focus();
    });

    cancelTaskBtn.addEventListener('click', () => {
        taskModal.classList.add('hidden');
    });

    submitTaskBtn.addEventListener('click', async () => {
        const name = newTaskName.value.trim();
        if(!name) return alert("Task name is required");
        const priority = newTaskPriority.value;
        const projectId = projectSelect.value;
        
        submitTaskBtn.textContent = 'Creating...';
        submitTaskBtn.disabled = true;
        
        try {
            const res = await fetch(`/projects/${projectId}/tasks`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, priority })
            });
            if(!res.ok) throw new Error(await res.text());
            
            taskModal.classList.add('hidden');
            loadTasks();
        } catch(err) {
            alert('Error creating task: ' + err.message);
        } finally {
            submitTaskBtn.textContent = 'Create Task';
            submitTaskBtn.disabled = false;
        }
    });

    // Initial Load
    updatePersonaUI();
    loadProjects();


    // --- Chatbot Logic ---
    chatFab.addEventListener('click', () => {
        chatPanel.classList.toggle('hidden');
        if (!chatPanel.classList.contains('hidden')) {
            chatInput.focus();
        }
    });

    closeChatBtn.addEventListener('click', () => {
        chatPanel.classList.add('hidden');
    });

    function addMessage(text, isUser = false) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${isUser ? 'user-message' : 'ai-message'}`;
        msgDiv.textContent = text;
        chatBody.appendChild(msgDiv);
        chatBody.scrollTop = chatBody.scrollHeight;
    }

    function handleSend() {
        const text = chatInput.value.trim();
        if (!text) return;

        // User message
        addMessage(text, true);
        chatInput.value = '';

        // Mock AI Response (Later connect to LLM backend)
        setTimeout(() => {
            addMessage("I am currently a mock UI response. Once you integrate an LLM on the Python backend, I'll be able to answer questions and trigger Zoho task actions!");
        }, 600);
    }

    sendBtn.addEventListener('click', handleSend);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSend();
    });
});
