// static/tasks.js
// Asynchronously manages task creations, transitions, and deletions on the task board

document.addEventListener("DOMContentLoaded", function() {
    const taskForm = document.getElementById("task-form");
    const listPending = document.getElementById("list-pending");
    const listProgress = document.getElementById("list-progress");
    const listCompleted = document.getElementById("list-completed");
    
    // Load existing tasks on startup
    fetchTasks();

    taskForm.addEventListener("submit", function(e) {
        e.preventDefault();
        const title = document.getElementById("task-title").value.trim();
        const description = document.getElementById("task-desc").value.trim();
        const priority = document.getElementById("task-prio").value;
        const dueDate = document.getElementById("task-due").value;

        if (!title) return;

        const payload = {
            title: title,
            description: description,
            priority: priority,
            due_date: dueDate || null
        };

        fetch('/api/v1/tasks', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        })
        .then(res => {
            if (!res.ok) throw new Error("Failed to create task");
            return res.json();
        })
        .then(() => {
            taskForm.reset();
            fetchTasks();
        })
        .catch(err => alert(err.message));
    });

    function fetchTasks() {
        fetch('/api/v1/tasks')
            .then(res => res.json())
            .then(tasks => {
                // Clear previous contents
                listPending.innerHTML = "";
                listProgress.innerHTML = "";
                listCompleted.innerHTML = "";

                if (tasks.length === 0) {
                    const empty = `<p style="text-align: center; color: #95a5a6; font-size: 0.85rem; padding-top: 20px;">No tasks</p>`;
                    listPending.innerHTML = empty;
                    listProgress.innerHTML = empty;
                    listCompleted.innerHTML = empty;
                    return;
                }

                tasks.forEach(task => {
                    const card = createTaskCard(task);
                    if (task.status === "Pending") {
                        listPending.appendChild(card);
                    } else if (task.status === "In Progress") {
                        listProgress.appendChild(card);
                    } else if (task.status === "Completed") {
                        listCompleted.appendChild(card);
                    }
                });

                // Add empty notices to empty columns
                checkEmpty(listPending);
                checkEmpty(listProgress);
                checkEmpty(listCompleted);
            });
    }

    function checkEmpty(listElement) {
        if (listElement.children.length === 0) {
            listElement.innerHTML = `<p style="text-align: center; color: #95a5a6; font-size: 0.85rem; padding-top: 20px;">No tasks in this category</p>`;
        }
    }

    function createTaskCard(task) {
        const card = document.createElement("div");
        card.className = "task-card";
        
        // Format due date label
        const dueLabel = task.due_date ? `🗓️ Due: ${task.due_date}` : "🗓️ No due date";
        const descHtml = task.description ? `<p class="task-desc">${task.description}</p>` : "";

        let moveButtons = "";
        if (task.status === "Pending") {
            moveButtons = `<button class="btn-action btn-move" onclick="updateStatus(${task.id}, 'In Progress')">🚀 Start</button>`;
        } else if (task.status === "In Progress") {
            moveButtons = `
                <button class="btn-action btn-move" onclick="updateStatus(${task.id}, 'Pending')">↩️ Postpone</button>
                <button class="btn-action btn-move" style="background: #d4efdf; color: #27ae60;" onclick="updateStatus(${task.id}, 'Completed')">✅ Done</button>
            `;
        } else if (task.status === "Completed") {
            moveButtons = `<button class="btn-action btn-move" onclick="updateStatus(${task.id}, 'In Progress')">↩️ Reopen</button>`;
        }

        card.innerHTML = `
            <div class="task-header">
                <h4 class="task-title">${task.title}</h4>
                <span class="priority-badge prio-${task.priority}">${task.priority}</span>
            </div>
            ${descHtml}
            <div class="task-footer">
                <span>${dueLabel}</span>
                <div class="task-actions">
                    ${moveButtons}
                    <button class="btn-action btn-delete" onclick="deleteTask(${task.id})">🗑️ Delete</button>
                </div>
            </div>
        `;
        return card;
    }

    // Bind functions to window context for inline event handlers
    window.updateStatus = function(taskId, nextStatus) {
        fetch(`/api/v1/tasks/${taskId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ status: nextStatus })
        })
        .then(res => {
            if (!res.ok) throw new Error("Failed to update status");
            fetchTasks();
        })
        .catch(err => alert(err.message));
    };

    window.deleteTask = function(taskId) {
        if (!confirm("Are you sure you want to delete this task?")) return;
        
        fetch(`/api/v1/tasks/${taskId}`, {
            method: 'DELETE'
        })
        .then(res => {
            if (!res.ok) throw new Error("Failed to delete task");
            fetchTasks();
        })
        .catch(err => alert(err.message));
    };
});
