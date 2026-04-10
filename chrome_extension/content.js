// content.js
let bubble = null;
let taskList = null;
let selectedText = '';

// Create bubble element
function createBubble() {
  const b = document.createElement('div');
  b.className = 'paperreader-bubble';
  b.innerHTML = `
    <img src="${chrome.runtime.getURL('icon.svg')}" width="20" height="20" style="display:block">
  `;
  b.style.display = 'none';
  document.body.appendChild(b);
  
  // Show task list on hover
  b.addEventListener('mouseenter', () => {
    showTaskList();
  });
  
  // Hide task list when mouse leaves bubble (unless entering task list)
  b.addEventListener('mouseleave', (e) => {
    // Check if moving to task list
    if (e.relatedTarget && taskList && taskList.contains(e.relatedTarget)) {
      return;
    }
    // Otherwise hide task list but keep bubble
    if (taskList) taskList.style.display = 'none';
  });
  
  return b;
}

// Create task list dropdown
function createTaskList() {
  const l = document.createElement('div');
  l.className = 'paperreader-task-list';
  document.body.appendChild(l);
  
  // Handle mouse leave from task list
  l.addEventListener('mouseleave', (e) => {
    // Check if moving back to bubble
    if (e.relatedTarget && bubble && bubble.contains(e.relatedTarget)) {
      return;
    }
    // Otherwise hide task list
    l.style.display = 'none';
  });
  
  return l;
}

// Handle text selection
document.addEventListener('mouseup', (e) => {
  const selection = window.getSelection();
  const text = selection.toString().trim();
  
  if (text.length > 0 && text.length < 300) { // Limit length to avoid huge selections
    selectedText = text;
    
    if (!bubble) bubble = createBubble();
    if (!taskList) taskList = createTaskList();
    
    // Position bubble to the right of the selection
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    
    // Position: Right of the end of selection, vertically centered
    // We use client rects which are viewport relative, so add scroll offsets
    bubble.style.top = `${window.scrollY + rect.top + (rect.height / 2) - 15}px`; // Center vertically (assuming 30px height)
    bubble.style.left = `${window.scrollX + rect.right + 10}px`; // 10px padding to the right
    bubble.style.display = 'flex';
    
    // Hide task list if showing
    taskList.style.display = 'none';
  } else {
    // DO NOT hide immediately on deselection if we are interacting with the bubble
    // We rely on the mousedown listener on document to hide it
  }
});

// Hide on click elsewhere
document.addEventListener('mousedown', (e) => {
  // If clicking inside bubble or task list, do nothing
  if ((bubble && bubble.contains(e.target)) || (taskList && taskList.contains(e.target))) {
    return;
  }
  
  // If clicking outside, hide everything
  if (bubble) bubble.style.display = 'none';
  if (taskList) taskList.style.display = 'none';
});

async function showTaskList() {
  if (!taskList) return;
  
  // Position task list
  const bubbleRect = bubble.getBoundingClientRect();
  // Remove gap: align top of list with bottom of bubble, maybe even overlap slightly or 0 gap
  taskList.style.top = `${window.scrollY + bubbleRect.bottom}px`; // Removed +5px gap
  taskList.style.left = `${window.scrollX + bubbleRect.left}px`;
  taskList.style.display = 'block';
  taskList.innerHTML = '<div class="paperreader-loading">Loading tasks...</div>';
  
  try {
    const response = await chrome.runtime.sendMessage({ action: 'getTasks' });
    
    if (response.success) {
      if (response.tasks.length === 0) {
        taskList.innerHTML = '<div class="paperreader-loading">No active tasks found.</div>';
        return;
      }
      
      taskList.innerHTML = '';
      response.tasks.forEach(task => {
        const item = document.createElement('div');
        item.className = 'paperreader-task-item';
        item.textContent = task.name;
        item.onclick = () => addToTask(task.id);
        taskList.appendChild(item);
      });
    } else {
      taskList.innerHTML = `<div class="paperreader-loading" style="color:red">Error: ${response.error}</div>`;
    }
  } catch (e) {
    taskList.innerHTML = `<div class="paperreader-loading" style="color:red">Connection failed. Is PaperReader running?</div>`;
  }
}

async function addToTask(taskId) {
  taskList.innerHTML = '<div class="paperreader-loading">Adding paper...</div>';
  
  try {
    const response = await chrome.runtime.sendMessage({
      action: 'addPaper',
      payload: {
        title: selectedText,
        taskId: taskId
      }
    });
    
    if (response.success) {
      taskList.innerHTML = '<div class="paperreader-loading" style="color:green">Paper added!</div>';
      setTimeout(() => {
        bubble.style.display = 'none';
        taskList.style.display = 'none';
      }, 1000);
    } else {
      taskList.innerHTML = `<div class="paperreader-loading" style="color:red">Error: ${response.error}</div>`;
    }
  } catch (e) {
    taskList.innerHTML = `<div class="paperreader-loading" style="color:red">Failed to add paper.</div>`;
  }
}
