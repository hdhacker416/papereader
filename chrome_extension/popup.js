document.addEventListener('DOMContentLoaded', async () => {
  const statusDiv = document.getElementById('status');
  
  try {
    const response = await chrome.runtime.sendMessage({ action: 'getTasks' });
    if (response.success) {
      statusDiv.textContent = `Connected! ${response.tasks.length} active tasks available.`;
      statusDiv.classList.add('online');
    } else {
      statusDiv.textContent = `Error: ${response.error}`;
      statusDiv.classList.add('offline');
    }
  } catch (e) {
    statusDiv.textContent = 'Cannot connect to PaperReader. Is it running at http://localhost:8000?';
    statusDiv.classList.add('offline');
  }
});
