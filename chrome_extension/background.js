// background.js
const DEFAULT_API_BASE = 'http://120.26.173.133/api';
const STORAGE_KEYS = {
  apiBase: 'paperreaderApiBase',
  token: 'paperreaderSessionToken',
  user: 'paperreaderUser',
};

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  const handlers = {
    getStatus,
    getTasks: fetchTasks,
    addPaper,
    login,
    register,
    logout,
    saveServer,
  };

  const handler = handlers[request.action];
  if (!handler) {
    return false;
  }

  handler(request.payload || {}).then(sendResponse);
  return true;
});

function storageGet(keys) {
  return chrome.storage.local.get(keys);
}

function storageSet(values) {
  return chrome.storage.local.set(values);
}

function storageRemove(keys) {
  return chrome.storage.local.remove(keys);
}

function normalizeApiBase(value) {
  const trimmed = String(value || '').trim().replace(/\/+$/, '');
  if (!trimmed) {
    return DEFAULT_API_BASE;
  }
  return trimmed.endsWith('/api') ? trimmed : `${trimmed}/api`;
}

async function getConfig() {
  const data = await storageGet([STORAGE_KEYS.apiBase, STORAGE_KEYS.token, STORAGE_KEYS.user]);
  return {
    apiBase: normalizeApiBase(data[STORAGE_KEYS.apiBase] || DEFAULT_API_BASE),
    token: data[STORAGE_KEYS.token] || '',
    user: data[STORAGE_KEYS.user] || null,
  };
}

async function apiFetch(path, options = {}) {
  const { apiBase, token } = await getConfig();
  const headers = {
    ...(options.body ? { 'Content-Type': 'application/json' } : {}),
    ...(options.headers || {}),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    headers,
  });

  let payload = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch (error) {
      payload = { detail: text };
    }
  }

  if (response.status === 401) {
    await clearSession();
    throw new Error('Please login to PaperReader first.');
  }
  if (!response.ok) {
    throw new Error(payload?.detail || `Request failed with status ${response.status}`);
  }
  return payload;
}

async function getStatus() {
  const config = await getConfig();
  if (!config.token) {
    return {
      success: true,
      apiBase: config.apiBase,
      user: null,
      authenticated: false,
    };
  }

  try {
    const auth = await apiFetch('/auth/me');
    await storageSet({ [STORAGE_KEYS.user]: auth.user });
    return {
      success: true,
      apiBase: config.apiBase,
      user: auth.user,
      authenticated: true,
    };
  } catch (error) {
    return {
      success: false,
      apiBase: config.apiBase,
      user: null,
      authenticated: false,
      error: error.message,
    };
  }
}

async function saveServer({ apiBase }) {
  const normalized = normalizeApiBase(apiBase);
  await storageSet({ [STORAGE_KEYS.apiBase]: normalized });
  return { success: true, apiBase: normalized };
}

async function authenticate(path, { email, password, name }) {
  const { apiBase } = await getConfig();
  const response = await fetch(`${apiBase}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || 'Authentication failed');
  }
  if (!payload.token || !payload.user) {
    throw new Error('Server did not return a session token');
  }
  await storageSet({
    [STORAGE_KEYS.token]: payload.token,
    [STORAGE_KEYS.user]: payload.user,
  });
  return { success: true, user: payload.user };
}

async function login(payload) {
  try {
    return await authenticate('/auth/login', payload);
  } catch (error) {
    return { success: false, error: error.message };
  }
}

async function register(payload) {
  try {
    return await authenticate('/auth/register', payload);
  } catch (error) {
    return { success: false, error: error.message };
  }
}

async function clearSession() {
  await storageRemove([STORAGE_KEYS.token, STORAGE_KEYS.user]);
}

async function logout() {
  try {
    await apiFetch('/auth/logout', { method: 'POST' });
  } catch (error) {
    // A stale session should still be removed locally.
  }
  await clearSession();
  return { success: true };
}

async function fetchTasks() {
  try {
    const tasks = await apiFetch('/tasks/');
    return { success: true, tasks: tasks.filter((task) => task.status !== 'completed') };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

async function addPaper({ title, taskId }) {
  try {
    const data = await apiFetch(`/tasks/${taskId}/papers`, {
      method: 'POST',
      body: JSON.stringify({
        titles: [title],
      }),
    });
    return { success: true, paper: Array.isArray(data) ? data[0] : data };
  } catch (error) {
    return { success: false, error: error.message };
  }
}
