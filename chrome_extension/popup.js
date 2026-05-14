let mode = 'login';

const elements = {};

document.addEventListener('DOMContentLoaded', async () => {
  for (const id of [
    'status',
    'serverInput',
    'saveServerButton',
    'signedInView',
    'signedOutView',
    'userName',
    'userEmail',
    'refreshButton',
    'logoutButton',
    'loginTab',
    'registerTab',
    'authForm',
    'nameLabel',
    'nameInput',
    'emailInput',
    'passwordInput',
    'submitButton',
  ]) {
    elements[id] = document.getElementById(id);
  }

  elements.loginTab.addEventListener('click', () => setMode('login'));
  elements.registerTab.addEventListener('click', () => setMode('register'));
  elements.saveServerButton.addEventListener('click', saveServer);
  elements.refreshButton.addEventListener('click', refreshStatus);
  elements.logoutButton.addEventListener('click', logout);
  elements.authForm.addEventListener('submit', submitAuth);

  await refreshStatus();
});

function setMode(nextMode) {
  mode = nextMode;
  elements.loginTab.classList.toggle('active', mode === 'login');
  elements.registerTab.classList.toggle('active', mode === 'register');
  elements.nameLabel.classList.toggle('hidden', mode !== 'register');
  elements.submitButton.textContent = mode === 'register' ? 'Create account' : 'Login';
  elements.passwordInput.autocomplete = mode === 'register' ? 'new-password' : 'current-password';
  setStatus('', '');
}

function setStatus(message, tone) {
  elements.status.textContent = message || 'Ready.';
  elements.status.className = 'status';
  if (tone) {
    elements.status.classList.add(tone);
  }
}

function setBusy(isBusy) {
  elements.saveServerButton.disabled = isBusy;
  elements.refreshButton.disabled = isBusy;
  elements.logoutButton.disabled = isBusy;
  elements.submitButton.disabled = isBusy;
}

async function sendMessage(action, payload) {
  return chrome.runtime.sendMessage({ action, payload });
}

function renderSignedIn(user) {
  elements.signedInView.classList.remove('hidden');
  elements.signedOutView.classList.add('hidden');
  elements.userName.textContent = user.name || user.email;
  elements.userEmail.textContent = user.email;
}

function renderSignedOut() {
  elements.signedInView.classList.add('hidden');
  elements.signedOutView.classList.remove('hidden');
}

async function refreshStatus() {
  setBusy(true);
  setStatus('Checking connection...', '');
  try {
    const response = await sendMessage('getStatus');
    elements.serverInput.value = response.apiBase || '';
    if (response.authenticated && response.user) {
      renderSignedIn(response.user);
      const tasksResponse = await sendMessage('getTasks');
      if (tasksResponse.success) {
        setStatus(`Connected. ${tasksResponse.tasks.length} active tasks available.`, 'online');
      } else {
        setStatus(tasksResponse.error, 'offline');
      }
      return;
    }
    renderSignedOut();
    setStatus(response.error || 'Login to connect this extension to your PaperReader account.', response.error ? 'offline' : '');
  } catch (error) {
    renderSignedOut();
    setStatus(error.message || 'Cannot connect to PaperReader.', 'offline');
  } finally {
    setBusy(false);
  }
}

async function saveServer() {
  setBusy(true);
  try {
    const response = await sendMessage('saveServer', { apiBase: elements.serverInput.value });
    elements.serverInput.value = response.apiBase;
    setStatus('Server saved.', 'online');
    await refreshStatus();
  } catch (error) {
    setStatus(error.message || 'Failed to save server.', 'offline');
  } finally {
    setBusy(false);
  }
}

async function submitAuth(event) {
  event.preventDefault();
  setBusy(true);
  setStatus(mode === 'register' ? 'Creating account...' : 'Logging in...', '');
  try {
    const response = await sendMessage(mode, {
      email: elements.emailInput.value,
      password: elements.passwordInput.value,
      name: elements.nameInput.value,
    });
    if (!response.success) {
      setStatus(response.error || 'Authentication failed.', 'offline');
      return;
    }
    elements.passwordInput.value = '';
    await refreshStatus();
  } catch (error) {
    setStatus(error.message || 'Authentication failed.', 'offline');
  } finally {
    setBusy(false);
  }
}

async function logout() {
  setBusy(true);
  try {
    await sendMessage('logout');
    renderSignedOut();
    setStatus('Logged out.', '');
  } catch (error) {
    setStatus(error.message || 'Failed to logout.', 'offline');
  } finally {
    setBusy(false);
  }
}
