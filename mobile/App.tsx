import { StatusBar } from 'expo-status-bar';
import * as DocumentPicker from 'expo-document-picker';
import * as SecureStore from 'expo-secure-store';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  RefreshControl,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

const API_BASE_URL = 'http://120.26.173.133/api';
const TOKEN_KEY = 'paperreader_mobile_token';

type TabKey = 'tasks' | 'settings' | 'account';
type Provider = 'gemini' | 'deepseek' | 'dashscope' | 'github';

interface AuthUser {
  id: string;
  email: string;
  name: string;
}

interface AuthResponse {
  user: AuthUser;
  token?: string;
  expires_at?: string;
}

interface TaskStats {
  total: number;
  done: number;
  failed: number;
  skipped: number;
  queued: number;
  processing: number;
}

interface Task {
  id: string;
  name: string;
  description?: string;
  status: string;
  model_name: string;
  created_at: string;
  updated_at: string;
  statistics?: TaskStats;
}

interface Template {
  id: string;
  name: string;
  is_default: boolean;
}

interface Paper {
  id: string;
  task_id: string;
  title: string;
  status: string;
  failure_reason?: string;
  source?: string;
  source_url?: string;
  pdf_path?: string;
  created_at: string;
  interpretation?: {
    content: string;
    template_used: string;
    created_at: string;
  };
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  cost?: number;
  time_cost?: number;
  created_at?: string;
}

interface ApiKeyInfo {
  provider: Provider;
  label: string;
  env_var: string;
  configured: boolean;
  masked_value?: string;
  source: 'user' | 'server' | 'missing';
  hint?: string;
}

interface ApiKeyCheckResponse {
  provider: Provider;
  status: 'ok' | 'warning' | 'error';
  message: string;
}

interface SelfCheckItem {
  key: string;
  label: string;
  status: 'ok' | 'warning' | 'error';
  severity: 'required' | 'optional';
  message: string;
  hint?: string;
}

interface SelfCheckResponse {
  overall_status: 'ok' | 'warning' | 'error';
  summary: string;
  checked_at: string;
  items: SelfCheckItem[];
}

const models = [
  'gemini-3-flash-preview',
  'gemini-3-pro-preview',
  'deepseek-v4-flash',
  'deepseek-v4-pro',
  'qwen-plus',
  'qwen-long',
];

const providerOrder: Provider[] = ['gemini', 'deepseek', 'dashscope', 'github'];

function statusColor(status: string) {
  if (status === 'done' || status === 'ok') return '#047857';
  if (status === 'failed' || status === 'error') return '#b91c1c';
  if (status === 'warning' || status === 'processing' || status === 'queued') return '#b45309';
  return '#334155';
}

function formatDate(value?: string) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function shortId(value: string) {
  return value.slice(0, 8);
}

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [booting, setBooting] = useState(true);
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authName, setAuthName] = useState('');
  const [authBusy, setAuthBusy] = useState(false);
  const [tab, setTab] = useState<TabKey>('tasks');
  const [message, setMessage] = useState('');

  const [tasks, setTasks] = useState<Task[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [taskName, setTaskName] = useState('');
  const [taskDescription, setTaskDescription] = useState('');
  const [taskModel, setTaskModel] = useState(models[0]);
  const [paperTitles, setPaperTitles] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [chatBusy, setChatBusy] = useState(false);

  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({});
  const [checks, setChecks] = useState<Record<string, ApiKeyCheckResponse>>({});
  const [selfCheck, setSelfCheck] = useState<SelfCheckResponse | null>(null);
  const [settingsBusy, setSettingsBusy] = useState(false);

  const authHeaders = useMemo<Record<string, string>>(() => {
    if (!token) {
      const emptyHeaders: Record<string, string> = {};
      return emptyHeaders;
    }
    return { Authorization: `Bearer ${token}` };
  }, [token]);

  const request = useCallback(async <T,>(path: string, options: RequestInit = {}): Promise<T> => {
    const headers: Record<string, string> = {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...authHeaders,
      ...(options.headers as Record<string, string> | undefined),
    };
    const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
    const text = await response.text();
    const payload = text ? JSON.parse(text) : null;
    if (!response.ok) {
      throw new Error(payload?.detail || payload?.message || `HTTP ${response.status}`);
    }
    return payload as T;
  }, [authHeaders]);

  const saveToken = async (nextToken: string | null) => {
    setToken(nextToken);
    if (nextToken) {
      await SecureStore.setItemAsync(TOKEN_KEY, nextToken);
    } else {
      await SecureStore.deleteItemAsync(TOKEN_KEY);
    }
  };

  const loadMe = useCallback(async () => {
    const data = await request<AuthResponse>('/auth/me');
    setUser(data.user);
  }, [request]);

  useEffect(() => {
    (async () => {
      const saved = await SecureStore.getItemAsync(TOKEN_KEY);
      if (!saved) {
        setBooting(false);
        return;
      }
      setToken(saved);
    })();
  }, []);

  useEffect(() => {
    if (!token) {
      setBooting(false);
      return;
    }
    loadMe()
      .catch(async () => {
        await saveToken(null);
        setUser(null);
      })
      .finally(() => setBooting(false));
  }, [loadMe, token]);

  const showError = (err: unknown, fallback = 'Request failed') => {
    const text = err instanceof Error ? err.message : fallback;
    setMessage(text);
  };

  const loginOrRegister = async () => {
    if (!authEmail.trim() || !authPassword.trim()) {
      setMessage('Email and password are required.');
      return;
    }
    setAuthBusy(true);
    setMessage('');
    try {
      const data = await request<AuthResponse>(`/auth/${authMode}`, {
        method: 'POST',
        body: JSON.stringify({
          email: authEmail.trim(),
          password: authPassword,
          name: authMode === 'register' ? authName.trim() || undefined : undefined,
        }),
      });
      if (!data.token) {
        throw new Error('Server did not return a mobile token.');
      }
      setUser(data.user);
      await saveToken(data.token);
    } catch (err) {
      showError(err, 'Authentication failed');
    } finally {
      setAuthBusy(false);
    }
  };

  const logout = async () => {
    try {
      await request('/auth/logout', { method: 'POST' });
    } catch {
      // Local logout should still proceed if the token is already invalid.
    }
    await saveToken(null);
    setUser(null);
    setSelectedTask(null);
    setSelectedPaper(null);
  };

  const loadTasks = useCallback(async () => {
    setLoading(true);
    setMessage('');
    try {
      const [taskData, templateData] = await Promise.all([
        request<Task[]>('/tasks/'),
        request<Template[]>('/templates/'),
      ]);
      setTasks(taskData);
      setTemplates(templateData);
      if (selectedTask) {
        const updated = taskData.find((item) => item.id === selectedTask.id);
        if (updated) setSelectedTask(updated);
      }
    } catch (err) {
      showError(err, 'Failed to load tasks');
    } finally {
      setLoading(false);
    }
  }, [request, selectedTask]);

  const loadTaskPapers = useCallback(async (task: Task) => {
    setLoading(true);
    setMessage('');
    try {
      const [taskDetail, paperData] = await Promise.all([
        request<Task>(`/tasks/${task.id}`),
        request<Paper[]>(`/tasks/${task.id}/papers`),
      ]);
      setSelectedTask(taskDetail);
      setPapers(paperData);
    } catch (err) {
      showError(err, 'Failed to load task papers');
    } finally {
      setLoading(false);
    }
  }, [request]);

  const loadPaper = useCallback(async (paper: Paper) => {
    setLoading(true);
    setMessage('');
    try {
      const [paperDetail, chatData] = await Promise.all([
        request<Paper>(`/papers/${paper.id}`),
        request<ChatMessage[]>(`/papers/${paper.id}/chat`),
      ]);
      setSelectedPaper(paperDetail);
      setChat(chatData);
    } catch (err) {
      showError(err, 'Failed to load paper');
    } finally {
      setLoading(false);
    }
  }, [request]);

  useEffect(() => {
    if (user && tab === 'tasks' && !selectedTask && !selectedPaper) {
      loadTasks();
    }
  }, [loadTasks, selectedPaper, selectedTask, tab, user]);

  const createTask = async () => {
    const defaultTemplate = templates.find((item) => item.is_default) || templates[0];
    if (!defaultTemplate) {
      setMessage('No reading template is available. Create one on the web first.');
      return;
    }
    if (!taskName.trim()) {
      setMessage('Task name is required.');
      return;
    }
    setLoading(true);
    try {
      await request<Task>('/tasks/', {
        method: 'POST',
        body: JSON.stringify({
          name: taskName.trim(),
          description: taskDescription.trim() || undefined,
          template_id: defaultTemplate.id,
          model_name: taskModel,
        }),
      });
      setTaskName('');
      setTaskDescription('');
      setCreateOpen(false);
      await loadTasks();
    } catch (err) {
      showError(err, 'Failed to create task');
    } finally {
      setLoading(false);
    }
  };

  const addPaperTitles = async () => {
    if (!selectedTask) return;
    const titles = paperTitles.split('\n').map((item) => item.trim()).filter(Boolean);
    if (!titles.length) {
      setMessage('Enter at least one paper title.');
      return;
    }
    setLoading(true);
    try {
      await request<Paper[]>(`/tasks/${selectedTask.id}/papers`, {
        method: 'POST',
        body: JSON.stringify({ titles }),
      });
      setPaperTitles('');
      await loadTaskPapers(selectedTask);
    } catch (err) {
      showError(err, 'Failed to add papers');
    } finally {
      setLoading(false);
    }
  };

  const uploadPdf = async () => {
    if (!selectedTask) return;
    const picked = await DocumentPicker.getDocumentAsync({
      type: 'application/pdf',
      multiple: true,
      copyToCacheDirectory: true,
    });
    if (picked.canceled) return;
    const form = new FormData();
    picked.assets.forEach((asset) => {
      form.append('files', {
        uri: asset.uri,
        name: asset.name || 'paper.pdf',
        type: asset.mimeType || 'application/pdf',
      } as any);
    });
    setLoading(true);
    try {
      await request<Paper[]>(`/tasks/${selectedTask.id}/papers/upload`, {
        method: 'POST',
        body: form,
      });
      await loadTaskPapers(selectedTask);
    } catch (err) {
      showError(err, 'Upload failed');
    } finally {
      setLoading(false);
    }
  };

  const sendChat = async () => {
    if (!selectedPaper || !chatInput.trim()) return;
    const text = chatInput.trim();
    setChatInput('');
    setChatBusy(true);
    setChat((current) => [...current, { role: 'user', content: text }]);
    try {
      const reply = await request<ChatMessage>(`/papers/${selectedPaper.id}/chat`, {
        method: 'POST',
        body: JSON.stringify({ message: text }),
      });
      setChat((current) => [...current, reply]);
    } catch (err) {
      showError(err, 'Chat failed');
      await loadPaper(selectedPaper);
    } finally {
      setChatBusy(false);
    }
  };

  const loadSettings = useCallback(async () => {
    setSettingsBusy(true);
    try {
      const data = await request<{ keys: ApiKeyInfo[] }>('/settings/api-keys');
      setKeys(data.keys.sort((a, b) => providerOrder.indexOf(a.provider) - providerOrder.indexOf(b.provider)));
    } catch (err) {
      showError(err, 'Failed to load settings');
    } finally {
      setSettingsBusy(false);
    }
  }, [request]);

  useEffect(() => {
    if (user && tab === 'settings') {
      loadSettings();
    }
  }, [loadSettings, tab, user]);

  const saveKey = async (provider: Provider) => {
    const value = (keyInputs[provider] || '').trim();
    if (!value) {
      setMessage('API key value cannot be empty.');
      return;
    }
    setSettingsBusy(true);
    try {
      const data = await request<{ key: ApiKeyInfo }>(`/settings/api-keys/${provider}`, {
        method: 'PUT',
        body: JSON.stringify({ value }),
      });
      setKeys((current) => current.map((item) => item.provider === provider ? data.key : item));
      setKeyInputs((current) => ({ ...current, [provider]: '' }));
    } catch (err) {
      showError(err, 'Failed to save key');
    } finally {
      setSettingsBusy(false);
    }
  };

  const clearKey = async (provider: Provider) => {
    setSettingsBusy(true);
    try {
      const data = await request<{ key: ApiKeyInfo }>(`/settings/api-keys/${provider}`, { method: 'DELETE' });
      setKeys((current) => current.map((item) => item.provider === provider ? data.key : item));
    } catch (err) {
      showError(err, 'Failed to clear key');
    } finally {
      setSettingsBusy(false);
    }
  };

  const checkKey = async (provider: Provider) => {
    setSettingsBusy(true);
    try {
      const data = await request<ApiKeyCheckResponse>(`/settings/api-keys/${provider}/check`, { method: 'POST' });
      setChecks((current) => ({ ...current, [provider]: data }));
    } catch (err) {
      showError(err, 'Failed to check key');
    } finally {
      setSettingsBusy(false);
    }
  };

  const runSelfCheck = async () => {
    setSettingsBusy(true);
    try {
      const data = await request<SelfCheckResponse>('/deep-research/self-check');
      setSelfCheck(data);
    } catch (err) {
      showError(err, 'Self-check failed');
    } finally {
      setSettingsBusy(false);
    }
  };

  if (booting) {
    return (
      <SafeAreaView style={styles.center}>
        <ActivityIndicator />
        <Text style={styles.muted}>Loading PaperReader...</Text>
      </SafeAreaView>
    );
  }

  if (!user) {
    return (
      <SafeAreaView style={styles.screen}>
        <StatusBar style="dark" />
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.authWrap}>
          <Text style={styles.brand}>PaperReader</Text>
          <Text style={styles.subtitle}>Android client</Text>
          <View style={styles.segment}>
            <Pressable style={[styles.segmentButton, authMode === 'login' && styles.segmentActive]} onPress={() => setAuthMode('login')}>
              <Text style={[styles.segmentText, authMode === 'login' && styles.segmentTextActive]}>Login</Text>
            </Pressable>
            <Pressable style={[styles.segmentButton, authMode === 'register' && styles.segmentActive]} onPress={() => setAuthMode('register')}>
              <Text style={[styles.segmentText, authMode === 'register' && styles.segmentTextActive]}>Register</Text>
            </Pressable>
          </View>
          {authMode === 'register' && (
            <TextInput style={styles.input} placeholder="Name" value={authName} onChangeText={setAuthName} autoCapitalize="words" />
          )}
          <TextInput style={styles.input} placeholder="Email" value={authEmail} onChangeText={setAuthEmail} autoCapitalize="none" keyboardType="email-address" />
          <TextInput style={styles.input} placeholder="Password" value={authPassword} onChangeText={setAuthPassword} secureTextEntry />
          <Pressable style={styles.primaryButton} onPress={loginOrRegister} disabled={authBusy}>
            {authBusy ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryButtonText}>{authMode === 'login' ? 'Login' : 'Create Account'}</Text>}
          </Pressable>
          {!!message && <Text style={styles.errorText}>{message}</Text>}
          <Text style={styles.serverText}>{API_BASE_URL}</Text>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  const content = selectedPaper
    ? renderPaperScreen()
    : selectedTask
      ? renderTaskScreen()
      : tab === 'settings'
        ? renderSettingsScreen()
        : tab === 'account'
          ? renderAccountScreen()
          : renderTasksScreen();

  return (
    <SafeAreaView style={styles.screen}>
      <StatusBar style="dark" />
      <View style={styles.header}>
        {(selectedTask || selectedPaper) ? (
          <Pressable onPress={() => selectedPaper ? setSelectedPaper(null) : setSelectedTask(null)} style={styles.backButton}>
            <Text style={styles.backText}>Back</Text>
          </Pressable>
        ) : (
          <Text style={styles.headerTitle}>PaperReader</Text>
        )}
        <Text style={styles.headerMeta}>{user.email}</Text>
      </View>
      {!!message && (
        <Pressable style={styles.banner} onPress={() => setMessage('')}>
          <Text style={styles.bannerText}>{message}</Text>
        </Pressable>
      )}
      {content}
      {!selectedTask && !selectedPaper && (
        <View style={styles.tabBar}>
          {(['tasks', 'settings', 'account'] as TabKey[]).map((item) => (
            <Pressable key={item} style={[styles.tabItem, tab === item && styles.tabItemActive]} onPress={() => setTab(item)}>
              <Text style={[styles.tabText, tab === item && styles.tabTextActive]}>
                {item === 'tasks' ? 'Tasks' : item === 'settings' ? 'Settings' : 'Account'}
              </Text>
            </Pressable>
          ))}
        </View>
      )}
    </SafeAreaView>
  );

  function renderTasksScreen() {
    return (
      <View style={styles.content}>
        <View style={styles.rowBetween}>
          <View>
            <Text style={styles.title}>Tasks</Text>
            <Text style={styles.muted}>{tasks.length} task(s)</Text>
          </View>
          <Pressable style={styles.smallButton} onPress={() => setCreateOpen(!createOpen)}>
            <Text style={styles.smallButtonText}>{createOpen ? 'Close' : 'New'}</Text>
          </Pressable>
        </View>
        {createOpen && (
          <View style={styles.panel}>
            <TextInput style={styles.input} placeholder="Task name" value={taskName} onChangeText={setTaskName} />
            <TextInput style={[styles.input, styles.multiline]} placeholder="Description" value={taskDescription} onChangeText={setTaskDescription} multiline />
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.modelStrip}>
              {models.map((item) => (
                <Pressable key={item} style={[styles.pill, taskModel === item && styles.pillActive]} onPress={() => setTaskModel(item)}>
                  <Text style={[styles.pillText, taskModel === item && styles.pillTextActive]}>{item}</Text>
                </Pressable>
              ))}
            </ScrollView>
            <Pressable style={styles.primaryButton} onPress={createTask} disabled={loading}>
              <Text style={styles.primaryButtonText}>Create Task</Text>
            </Pressable>
          </View>
        )}
        <FlatList
          data={tasks}
          keyExtractor={(item) => item.id}
          refreshControl={<RefreshControl refreshing={loading} onRefresh={loadTasks} />}
          renderItem={({ item }) => (
            <Pressable style={styles.card} onPress={() => loadTaskPapers(item)}>
              <View style={styles.rowBetween}>
                <Text style={styles.cardTitle}>{item.name}</Text>
                <Text style={[styles.badge, { color: statusColor(item.status) }]}>{item.status}</Text>
              </View>
              <Text style={styles.muted}>{item.model_name}</Text>
              {item.description ? <Text style={styles.bodyText} numberOfLines={2}>{item.description}</Text> : null}
              {item.statistics && (
                <Text style={styles.meta}>
                  {item.statistics.done}/{item.statistics.total} done · {item.statistics.processing} processing · {item.statistics.failed} failed
                </Text>
              )}
            </Pressable>
          )}
          ListEmptyComponent={!loading ? <Text style={styles.emptyText}>No tasks yet.</Text> : null}
        />
      </View>
    );
  }

  function renderTaskScreen() {
    if (!selectedTask) return null;
    return (
      <ScrollView
        style={styles.content}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={() => loadTaskPapers(selectedTask)} />}
      >
        <Text style={styles.title}>{selectedTask.name}</Text>
        <Text style={styles.muted}>{selectedTask.model_name} · {selectedTask.status}</Text>
        <View style={styles.panel}>
          <Text style={styles.sectionTitle}>Upload PDFs</Text>
          <Pressable style={styles.primaryButton} onPress={uploadPdf} disabled={loading}>
            <Text style={styles.primaryButtonText}>Choose PDF Files</Text>
          </Pressable>
        </View>
        <View style={styles.panel}>
          <Text style={styles.sectionTitle}>Add by title</Text>
          <TextInput
            style={[styles.input, styles.multiline]}
            placeholder="One paper title per line"
            value={paperTitles}
            onChangeText={setPaperTitles}
            multiline
          />
          <Pressable style={styles.secondaryButton} onPress={addPaperTitles} disabled={loading}>
            <Text style={styles.secondaryButtonText}>Add Titles</Text>
          </Pressable>
        </View>
        <Text style={styles.sectionTitle}>Papers</Text>
        {papers.map((paper) => (
          <Pressable key={paper.id} style={styles.card} onPress={() => loadPaper(paper)}>
            <View style={styles.rowBetween}>
              <Text style={styles.cardTitle}>{paper.title}</Text>
              <Text style={[styles.badge, { color: statusColor(paper.status) }]}>{paper.status}</Text>
            </View>
            <Text style={styles.meta}>{shortId(paper.id)} · {paper.source || 'remote'} · {formatDate(paper.created_at)}</Text>
            {paper.failure_reason ? <Text style={styles.errorText}>{paper.failure_reason}</Text> : null}
          </Pressable>
        ))}
        {!papers.length && <Text style={styles.emptyText}>No papers in this task.</Text>}
      </ScrollView>
    );
  }

  function renderPaperScreen() {
    if (!selectedPaper) return null;
    return (
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.content}>
        <ScrollView refreshControl={<RefreshControl refreshing={loading} onRefresh={() => loadPaper(selectedPaper)} />}>
          <Text style={styles.title}>{selectedPaper.title}</Text>
          <Text style={[styles.badge, { color: statusColor(selectedPaper.status) }]}>{selectedPaper.status}</Text>
          {selectedPaper.failure_reason ? <Text style={styles.errorText}>{selectedPaper.failure_reason}</Text> : null}
          <View style={styles.panel}>
            <Text style={styles.sectionTitle}>Reading</Text>
            <Text style={styles.bodyText}>{selectedPaper.interpretation?.content || 'No interpretation yet. Pull to refresh after processing finishes.'}</Text>
          </View>
          <Text style={styles.sectionTitle}>Chat</Text>
          {chat.map((item, index) => (
            <View key={`${item.created_at || index}-${item.role}`} style={[styles.chatBubble, item.role === 'user' ? styles.chatUser : styles.chatAssistant]}>
              <Text style={styles.chatRole}>{item.role}</Text>
              <Text style={styles.bodyText}>{item.content}</Text>
            </View>
          ))}
          {chatBusy && <ActivityIndicator style={{ marginVertical: 12 }} />}
        </ScrollView>
        <View style={styles.chatInputRow}>
          <TextInput style={styles.chatInput} placeholder="Ask about this paper" value={chatInput} onChangeText={setChatInput} multiline />
          <Pressable style={styles.sendButton} onPress={sendChat} disabled={chatBusy || !chatInput.trim()}>
            <Text style={styles.sendButtonText}>Send</Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    );
  }

  function renderSettingsScreen() {
    return (
      <ScrollView style={styles.content} refreshControl={<RefreshControl refreshing={settingsBusy} onRefresh={loadSettings} />}>
        <View style={styles.rowBetween}>
          <View>
            <Text style={styles.title}>Settings</Text>
            <Text style={styles.muted}>API keys are stored per account.</Text>
          </View>
          <Pressable style={styles.smallButton} onPress={runSelfCheck} disabled={settingsBusy}>
            <Text style={styles.smallButtonText}>Self-check</Text>
          </Pressable>
        </View>
        {selfCheck && (
          <View style={styles.panel}>
            <Text style={[styles.sectionTitle, { color: statusColor(selfCheck.overall_status) }]}>{selfCheck.summary}</Text>
            {selfCheck.items.map((item) => (
              <View key={item.key} style={styles.checkRow}>
                <Text style={styles.cardTitle}>{item.label}</Text>
                <Text style={[styles.badge, { color: statusColor(item.status) }]}>{item.status}</Text>
                <Text style={styles.bodyText}>{item.message}</Text>
              </View>
            ))}
          </View>
        )}
        {keys.map((item) => (
          <View key={item.provider} style={styles.card}>
            <View style={styles.rowBetween}>
              <Text style={styles.cardTitle}>{item.label}</Text>
              <Text style={[styles.badge, { color: item.configured ? '#047857' : '#b45309' }]}>
                {item.source === 'user' ? 'User key' : item.source === 'server' ? 'Server default' : 'Missing'}
              </Text>
            </View>
            <Text style={styles.meta}>{item.env_var} {item.masked_value ? `· ${item.masked_value}` : ''}</Text>
            <TextInput
              style={styles.input}
              placeholder={`Enter ${item.label} key`}
              value={keyInputs[item.provider] || ''}
              onChangeText={(value) => setKeyInputs((current) => ({ ...current, [item.provider]: value }))}
              autoCapitalize="none"
              secureTextEntry
            />
            <View style={styles.buttonRow}>
              <Pressable style={styles.secondaryButton} onPress={() => saveKey(item.provider)} disabled={settingsBusy}>
                <Text style={styles.secondaryButtonText}>Save</Text>
              </Pressable>
              <Pressable style={styles.secondaryButton} onPress={() => checkKey(item.provider)} disabled={settingsBusy || !item.configured}>
                <Text style={styles.secondaryButtonText}>Check</Text>
              </Pressable>
              <Pressable style={styles.dangerButton} onPress={() => clearKey(item.provider)} disabled={settingsBusy || item.source !== 'user'}>
                <Text style={styles.dangerButtonText}>Clear</Text>
              </Pressable>
            </View>
            {checks[item.provider] && (
              <Text style={[styles.meta, { color: statusColor(checks[item.provider].status) }]}>{checks[item.provider].message}</Text>
            )}
          </View>
        ))}
      </ScrollView>
    );
  }

  function renderAccountScreen() {
    return (
      <ScrollView style={styles.content}>
        <Text style={styles.title}>Account</Text>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>{user?.name}</Text>
          <Text style={styles.bodyText}>{user?.email}</Text>
          <Text style={styles.meta}>Server: {API_BASE_URL}</Text>
        </View>
        <Pressable style={styles.dangerWideButton} onPress={() => Alert.alert('Logout', 'Log out of this device?', [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Logout', style: 'destructive', onPress: logout },
        ])}>
          <Text style={styles.dangerWideButtonText}>Logout</Text>
        </Pressable>
      </ScrollView>
    );
  }
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#f8fafc',
  },
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    backgroundColor: '#f8fafc',
  },
  authWrap: {
    flex: 1,
    justifyContent: 'center',
    padding: 24,
    gap: 12,
  },
  brand: {
    fontSize: 34,
    fontWeight: '800',
    color: '#0f172a',
  },
  subtitle: {
    fontSize: 15,
    color: '#64748b',
    marginBottom: 16,
  },
  serverText: {
    color: '#94a3b8',
    fontSize: 12,
    textAlign: 'center',
    marginTop: 12,
  },
  segment: {
    flexDirection: 'row',
    borderWidth: 1,
    borderColor: '#dbe3ef',
    borderRadius: 10,
    overflow: 'hidden',
    marginBottom: 4,
  },
  segmentButton: {
    flex: 1,
    paddingVertical: 11,
    alignItems: 'center',
    backgroundColor: '#fff',
  },
  segmentActive: {
    backgroundColor: '#2563eb',
  },
  segmentText: {
    color: '#475569',
    fontWeight: '700',
  },
  segmentTextActive: {
    color: '#fff',
  },
  header: {
    height: 56,
    paddingHorizontal: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
    backgroundColor: '#fff',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '800',
    color: '#0f172a',
  },
  headerMeta: {
    maxWidth: 210,
    color: '#64748b',
    fontSize: 12,
  },
  backButton: {
    paddingVertical: 8,
    paddingRight: 12,
  },
  backText: {
    color: '#2563eb',
    fontWeight: '800',
  },
  content: {
    flex: 1,
    padding: 16,
  },
  title: {
    fontSize: 24,
    fontWeight: '800',
    color: '#0f172a',
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: '#0f172a',
    marginBottom: 8,
  },
  muted: {
    color: '#64748b',
    fontSize: 13,
    marginTop: 3,
  },
  bodyText: {
    color: '#334155',
    fontSize: 14,
    lineHeight: 21,
  },
  meta: {
    color: '#64748b',
    fontSize: 12,
    marginTop: 6,
  },
  rowBetween: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
    marginBottom: 12,
  },
  card: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    padding: 14,
    marginBottom: 12,
  },
  panel: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    padding: 14,
    marginVertical: 12,
  },
  cardTitle: {
    flex: 1,
    fontSize: 16,
    fontWeight: '800',
    color: '#0f172a',
  },
  badge: {
    fontSize: 12,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  input: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 11,
    fontSize: 15,
    color: '#0f172a',
    marginBottom: 10,
  },
  multiline: {
    minHeight: 82,
    textAlignVertical: 'top',
  },
  primaryButton: {
    backgroundColor: '#2563eb',
    borderRadius: 10,
    paddingVertical: 13,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryButtonText: {
    color: '#fff',
    fontWeight: '800',
  },
  secondaryButton: {
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 10,
    paddingVertical: 11,
    paddingHorizontal: 14,
    alignItems: 'center',
    backgroundColor: '#fff',
  },
  secondaryButtonText: {
    color: '#1e293b',
    fontWeight: '800',
  },
  smallButton: {
    backgroundColor: '#0f172a',
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 14,
  },
  smallButtonText: {
    color: '#fff',
    fontWeight: '800',
  },
  dangerButton: {
    borderWidth: 1,
    borderColor: '#fecaca',
    borderRadius: 10,
    paddingVertical: 11,
    paddingHorizontal: 14,
    alignItems: 'center',
    backgroundColor: '#fff',
  },
  dangerButtonText: {
    color: '#b91c1c',
    fontWeight: '800',
  },
  dangerWideButton: {
    backgroundColor: '#fee2e2',
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 12,
  },
  dangerWideButtonText: {
    color: '#b91c1c',
    fontWeight: '800',
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
    marginTop: 4,
  },
  modelStrip: {
    marginBottom: 12,
  },
  pill: {
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 12,
    marginRight: 8,
    backgroundColor: '#fff',
  },
  pillActive: {
    backgroundColor: '#dbeafe',
    borderColor: '#2563eb',
  },
  pillText: {
    color: '#475569',
    fontWeight: '700',
    fontSize: 12,
  },
  pillTextActive: {
    color: '#1d4ed8',
  },
  emptyText: {
    color: '#64748b',
    textAlign: 'center',
    padding: 24,
  },
  errorText: {
    color: '#b91c1c',
    fontSize: 13,
    marginTop: 8,
  },
  banner: {
    backgroundColor: '#fff7ed',
    borderBottomWidth: 1,
    borderBottomColor: '#fed7aa',
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  bannerText: {
    color: '#9a3412',
    fontSize: 13,
  },
  tabBar: {
    flexDirection: 'row',
    borderTopWidth: 1,
    borderTopColor: '#e2e8f0',
    backgroundColor: '#fff',
    padding: 8,
    gap: 8,
  },
  tabItem: {
    flex: 1,
    alignItems: 'center',
    borderRadius: 10,
    paddingVertical: 10,
  },
  tabItemActive: {
    backgroundColor: '#dbeafe',
  },
  tabText: {
    color: '#64748b',
    fontWeight: '800',
  },
  tabTextActive: {
    color: '#1d4ed8',
  },
  chatBubble: {
    borderRadius: 10,
    padding: 12,
    marginBottom: 10,
    borderWidth: 1,
  },
  chatUser: {
    backgroundColor: '#dbeafe',
    borderColor: '#bfdbfe',
  },
  chatAssistant: {
    backgroundColor: '#fff',
    borderColor: '#e2e8f0',
  },
  chatRole: {
    textTransform: 'uppercase',
    fontSize: 11,
    color: '#64748b',
    fontWeight: '800',
    marginBottom: 4,
  },
  chatInputRow: {
    flexDirection: 'row',
    gap: 8,
    paddingVertical: 10,
  },
  chatInput: {
    flex: 1,
    maxHeight: 96,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    textAlignVertical: 'top',
  },
  sendButton: {
    alignSelf: 'flex-end',
    backgroundColor: '#2563eb',
    borderRadius: 10,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  sendButtonText: {
    color: '#fff',
    fontWeight: '800',
  },
  checkRow: {
    borderTopWidth: 1,
    borderTopColor: '#e2e8f0',
    paddingTop: 10,
    marginTop: 10,
  },
});
