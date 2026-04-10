// background.js
const API_BASE = 'http://localhost:8000/api';

// Listen for messages from content script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getTasks') {
    fetchTasks().then(sendResponse);
    return true; // Will respond asynchronously
  } else if (request.action === 'addPaper') {
    addPaper(request.payload).then(sendResponse);
    return true;
  }
});

async function fetchTasks() {
  try {
    // Remove trailing slash to match backend redirect behavior if needed, 
    // but FastAPI usually handles trailing slashes by redirecting. 
    // The issue might be that FastAPI redirects POST /papers/ to /papers, but fetch doesn't follow POST redirects well with body.
    // Let's use strict paths without trailing slashes.
    // Update: FastAPI redirects non-slash to slash for some routes or vice-versa depending on definition.
    // If the previous attempt failed with 307->404, it means we need the slash.
    // Let's try adding the slash back.
    const response = await fetch(`${API_BASE}/tasks/`);
    if (!response.ok) throw new Error('Failed to fetch tasks');
    const tasks = await response.json();
    // Filter out completed tasks if you want, or show all
    return { success: true, tasks: tasks.filter(t => t.status !== 'completed') };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

async function addPaper({ title, taskId }) {
  try {
    const response = await fetch(`${API_BASE}/tasks/${taskId}/papers`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        titles: [title]
      }),
    });
    
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Failed to add paper');
    }
    
    const data = await response.json();
    return { success: true, paper: Array.isArray(data) ? data[0] : data };
  } catch (error) {
    return { success: false, error: error.message };
  }
}
