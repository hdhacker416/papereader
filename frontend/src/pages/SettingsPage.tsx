import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Star,
  Check,
  Terminal,
  Trash2,
  Wrench,
} from 'lucide-react';
import clsx from 'clsx';
import Layout from '../components/Layout';
import { deepResearchApi, settingsApi, templatesApi } from '../api/services';
import {
  ApiKeyCheckResponse,
  ApiKeyInfo,
  ApiKeyProvider,
  SelfCheckResponse,
  Template,
} from '../types';

const statusStyles = {
  ok: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  warning: 'bg-amber-50 text-amber-700 border-amber-200',
  error: 'bg-red-50 text-red-700 border-red-200',
};

const keySourceLabels: Record<ApiKeyInfo['source'], string> = {
  user: 'User key',
  server: 'Server default',
  missing: 'Missing',
};

type SectionKey = 'selfCheck' | 'templates' | 'api';

interface SettingsSectionProps {
  id: SectionKey;
  title: string;
  description: string;
  icon: React.ReactNode;
  open: boolean;
  onToggle: (id: SectionKey) => void;
  children: React.ReactNode;
}

const SettingsSection: React.FC<SettingsSectionProps> = ({
  id,
  title,
  description,
  icon,
  open,
  onToggle,
  children,
}) => (
  <section className="bg-white border border-gray-200 rounded-lg overflow-hidden">
    <button
      type="button"
      onClick={() => onToggle(id)}
      className="w-full flex items-center justify-between gap-4 px-5 py-4 text-left hover:bg-gray-50 transition-colors"
    >
      <div className="flex items-start gap-3 min-w-0">
        <div className="w-9 h-9 rounded-lg bg-blue-50 text-blue-700 flex items-center justify-center shrink-0">
          {icon}
        </div>
        <div className="min-w-0">
          <h2 className="font-semibold text-gray-900">{title}</h2>
          <p className="text-sm text-gray-500 mt-1">{description}</p>
        </div>
      </div>
      {open ? <ChevronDown size={20} className="text-gray-500 shrink-0" /> : <ChevronRight size={20} className="text-gray-500 shrink-0" />}
    </button>
    {open && <div className="border-t border-gray-100 p-5">{children}</div>}
  </section>
);

const SettingsPage: React.FC = () => {
  const [openSections, setOpenSections] = useState<Record<SectionKey, boolean>>({
    selfCheck: true,
    templates: false,
    api: true,
  });

  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [checks, setChecks] = useState<Record<string, ApiKeyCheckResponse>>({});
  const [loadingKeys, setLoadingKeys] = useState(true);
  const [busyProvider, setBusyProvider] = useState<string | null>(null);

  const [selfChecking, setSelfChecking] = useState(false);
  const [selfCheckResult, setSelfCheckResult] = useState<SelfCheckResponse | null>(null);

  const [templates, setTemplates] = useState<Template[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [showTemplateForm, setShowTemplateForm] = useState(false);
  const [newTemplateName, setNewTemplateName] = useState('');
  const [newTemplateContent, setNewTemplateContent] = useState<string[]>(['']);

  const [error, setError] = useState('');

  const toggleSection = (id: SectionKey) => {
    setOpenSections((current) => ({ ...current, [id]: !current[id] }));
  };

  const loadKeys = async () => {
    setLoadingKeys(true);
    setError('');
    try {
      const data = await settingsApi.listApiKeys();
      setKeys(data.keys);
    } catch (err) {
      console.error('Failed to load API keys:', err);
      setError('Failed to load API key settings.');
    } finally {
      setLoadingKeys(false);
    }
  };

  useEffect(() => {
    loadKeys();
  }, []);

  const loadTemplates = async () => {
    setLoadingTemplates(true);
    setError('');
    try {
      const data = await templatesApi.list();
      setTemplates(data);
    } catch (err) {
      console.error('Failed to load templates:', err);
      setError('Failed to load templates.');
    } finally {
      setLoadingTemplates(false);
    }
  };

  useEffect(() => {
    if (openSections.templates && templates.length === 0) {
      loadTemplates();
    }
  }, [openSections.templates, templates.length]);

  const addTemplateStep = () => {
    setNewTemplateContent(prev => [...prev, '']);
  };

  const updateTemplateStep = (index: number, value: string) => {
    setNewTemplateContent(prev => prev.map((item, itemIndex) => itemIndex === index ? value : item));
  };

  const removeTemplateStep = (index: number) => {
    setNewTemplateContent(prev => prev.length <= 1 ? prev : prev.filter((_, itemIndex) => itemIndex !== index));
  };

  const createTemplate = async () => {
    const content = newTemplateContent.map(item => item.trim()).filter(Boolean);
    if (!newTemplateName.trim() || content.length === 0) {
      setError('Template name and at least one prompt are required.');
      return;
    }
    setError('');
    try {
      await templatesApi.create({ name: newTemplateName.trim(), content });
      setNewTemplateName('');
      setNewTemplateContent(['']);
      setShowTemplateForm(false);
      await loadTemplates();
    } catch (err) {
      console.error('Failed to create template:', err);
      setError('Failed to create template.');
    }
  };

  const deleteTemplate = async (id: string) => {
    setError('');
    try {
      await templatesApi.delete(id);
      await loadTemplates();
    } catch (err) {
      console.error('Failed to delete template:', err);
      setError('Failed to delete template.');
    }
  };

  const setDefaultTemplate = async (id: string) => {
    setError('');
    try {
      await templatesApi.setDefault(id);
      await loadTemplates();
    } catch (err) {
      console.error('Failed to set default template:', err);
      setError('Failed to set default template.');
    }
  };

  const updateKeyInState = (updated: ApiKeyInfo) => {
    setKeys(prev => prev.map(item => item.provider === updated.provider ? updated : item));
  };

  const handleSave = async (provider: ApiKeyProvider) => {
    const value = (values[provider] || '').trim();
    if (!value) {
      setError('API key value cannot be empty.');
      return;
    }
    setBusyProvider(provider);
    setError('');
    try {
      const result = await settingsApi.updateApiKey(provider, value);
      updateKeyInState(result.key);
      setValues(prev => ({ ...prev, [provider]: '' }));
      const check = await settingsApi.checkApiKey(provider);
      setChecks(prev => ({ ...prev, [provider]: check }));
    } catch (err) {
      console.error('Failed to save API key:', err);
      setError('Failed to save API key.');
    } finally {
      setBusyProvider(null);
    }
  };

  const handleDelete = async (provider: ApiKeyProvider) => {
    setBusyProvider(provider);
    setError('');
    try {
      const result = await settingsApi.deleteApiKey(provider);
      updateKeyInState(result.key);
      setValues(prev => ({ ...prev, [provider]: '' }));
      setChecks(prev => {
        const next = { ...prev };
        delete next[provider];
        return next;
      });
    } catch (err) {
      console.error('Failed to clear API key:', err);
      setError('Failed to clear API key.');
    } finally {
      setBusyProvider(null);
    }
  };

  const handleCheck = async (provider: ApiKeyProvider) => {
    setBusyProvider(provider);
    setError('');
    try {
      const check = await settingsApi.checkApiKey(provider);
      setChecks(prev => ({ ...prev, [provider]: check }));
    } catch (err) {
      console.error('Failed to check API key:', err);
      setError('Failed to check API key.');
    } finally {
      setBusyProvider(null);
    }
  };

  const runSelfCheck = async () => {
    if (selfChecking) {
      return;
    }
    setSelfChecking(true);
    setError('');
    try {
      const result = await deepResearchApi.runSelfCheck();
      setSelfCheckResult(result);
    } catch (err) {
      console.error('Failed to run self-check:', err);
      setSelfCheckResult({
        overall_status: 'error',
        summary: 'Self-check request failed.',
        checked_at: new Date().toISOString(),
        items: [],
      });
    } finally {
      setSelfChecking(false);
    }
  };

  const renderStatusBadge = (status: 'ok' | 'warning' | 'error', label?: string) => (
    <span className={clsx('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium', statusStyles[status])}>
      {status === 'ok' ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
      {label || status}
    </span>
  );

  return (
    <Layout>
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
            <p className="text-gray-500 mt-1">Manage environment checks and the Qwen API key.</p>
          </div>
          <button
            type="button"
            onClick={() => {
              loadKeys();
            }}
            disabled={loadingKeys}
            className="flex items-center gap-2 px-4 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            <RefreshCw size={18} className={clsx(loadingKeys && 'animate-spin')} />
            Refresh
          </button>
        </div>

        {error && (
          <div className="mb-5 flex items-center gap-2 border border-red-200 bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm">
            <AlertTriangle size={18} />
            {error}
          </div>
        )}

        <div className="space-y-4">
          <SettingsSection
            id="selfCheck"
            title="Self-check"
            description="Run the environment check for keys, shared search data, and provider readiness."
            icon={<Wrench size={18} />}
            open={openSections.selfCheck}
            onToggle={toggleSection}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="font-semibold text-gray-900">Environment self-check</h3>
                <p className="text-sm text-gray-500 mt-1">This runs the same backend checks used by Deep Research.</p>
              </div>
              <button
                type="button"
                onClick={runSelfCheck}
                disabled={selfChecking}
                className="shrink-0 flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              >
                {selfChecking ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
                Run
              </button>
            </div>
            {selfCheckResult && (
              <div className="mt-4 space-y-3">
                <div className={clsx('rounded-lg px-4 py-3 text-sm border', statusStyles[selfCheckResult.overall_status])}>
                  <div className="font-medium">{selfCheckResult.summary}</div>
                  <div className="mt-1 text-xs opacity-80">Checked at {new Date(selfCheckResult.checked_at).toLocaleString()}</div>
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  {selfCheckResult.items.map((item) => (
                    <div key={item.key} className="border border-gray-200 rounded-lg px-4 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="font-medium text-gray-900">{item.label}</div>
                          <div className="text-sm text-gray-700 mt-1">{item.message}</div>
                        </div>
                        {renderStatusBadge(item.status, item.status)}
                      </div>
                      {item.hint && <div className="mt-2 text-xs text-gray-500">{item.hint}</div>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </SettingsSection>

          <SettingsSection
            id="templates"
            title="Templates"
            description="Manage paper reading prompt templates from Settings instead of the main sidebar."
            icon={<Terminal size={18} />}
            open={openSections.templates}
            onToggle={toggleSection}
          >
            <div className="flex items-center justify-between gap-4 mb-4">
              <div>
                <h3 className="font-semibold text-gray-900">Reading templates</h3>
                <p className="text-sm text-gray-500 mt-1">Templates define multi-step prompts for paper reading tasks.</p>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={loadTemplates}
                  disabled={loadingTemplates}
                  className="flex items-center gap-2 px-3 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                >
                  <RefreshCw size={16} className={clsx(loadingTemplates && 'animate-spin')} />
                  Refresh
                </button>
                <button
                  type="button"
                  onClick={() => setShowTemplateForm(prev => !prev)}
                  className="flex items-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700"
                >
                  <Plus size={16} />
                  New
                </button>
              </div>
            </div>

            {showTemplateForm && (
              <div className="mb-5 rounded-lg border border-gray-200 bg-gray-50 p-4">
                <div className="grid grid-cols-1 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                    <input
                      value={newTemplateName}
                      onChange={(event) => setNewTemplateName(event.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                      placeholder="Template name"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Prompts</label>
                    <div className="space-y-3">
                      {newTemplateContent.map((step, index) => (
                        <div key={index}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs font-medium text-gray-500">Step {index + 1}</span>
                            {newTemplateContent.length > 1 && (
                              <button
                                type="button"
                                onClick={() => removeTemplateStep(index)}
                                className="text-xs text-red-600 hover:text-red-700"
                              >
                                Remove
                              </button>
                            )}
                          </div>
                          <textarea
                            value={step}
                            onChange={(event) => updateTemplateStep(index, event.target.value)}
                            className="w-full h-24 px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm resize-none"
                            placeholder={`Prompt for step ${index + 1}`}
                          />
                        </div>
                      ))}
                    </div>
                    <button
                      type="button"
                      onClick={addTemplateStep}
                      className="mt-2 flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700"
                    >
                      <Plus size={16} />
                      Add step
                    </button>
                  </div>
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => setShowTemplateForm(false)}
                      className="px-4 py-2 rounded-lg bg-white border border-gray-200 text-sm font-medium text-gray-700 hover:bg-gray-50"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={createTemplate}
                      disabled={!newTemplateName.trim() || newTemplateContent.every(item => !item.trim())}
                      className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                    >
                      Create
                    </button>
                  </div>
                </div>
              </div>
            )}

            {loadingTemplates ? (
              <div className="text-sm text-gray-500">Loading templates...</div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {templates.map((template) => (
                  <div
                    key={template.id}
                    className={clsx(
                      'border rounded-lg p-4 bg-white',
                      template.is_default ? 'border-blue-300 ring-1 ring-blue-200' : 'border-gray-200',
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h4 className="font-semibold text-gray-900">{template.name}</h4>
                        {template.is_default && (
                          <span className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full">
                            <Check size={12} />
                            Default
                          </span>
                        )}
                      </div>
                      <div className="flex gap-2 shrink-0">
                        {!template.is_default && (
                          <button
                            type="button"
                            onClick={() => setDefaultTemplate(template.id)}
                            className="w-8 h-8 rounded-md text-gray-400 hover:bg-yellow-50 hover:text-yellow-600 flex items-center justify-center"
                            title="Set as default"
                          >
                            <Star size={16} />
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => deleteTemplate(template.id)}
                          className="w-8 h-8 rounded-md text-gray-400 hover:bg-red-50 hover:text-red-600 flex items-center justify-center"
                          title="Delete template"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                    <div className="mt-3 space-y-2">
                      {template.content.map((step, index) => (
                        <div key={index} className="rounded-md border border-gray-100 bg-gray-50 p-2">
                          <div className="text-[11px] font-semibold text-gray-400 mb-1">Step {index + 1}</div>
                          <p className="text-xs text-gray-600 font-mono whitespace-pre-wrap line-clamp-3">{step}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
                {templates.length === 0 && (
                  <div className="text-sm text-gray-500">No templates found.</div>
                )}
              </div>
            )}
          </SettingsSection>

          <SettingsSection
            id="api"
            title="API Management"
            description="Configure the Qwen / Alibaba Cloud Model Studio API key for this account."
            icon={<KeyRound size={18} />}
            open={openSections.api}
            onToggle={toggleSection}
          >
            <div className="space-y-4">
              {loadingKeys ? (
                <div className="text-sm text-gray-500">Loading API key settings...</div>
              ) : keys.map((item) => {
                const check = checks[item.provider];
                const isBusy = busyProvider === item.provider;
                const inputType = visible[item.provider] ? 'text' : 'password';
                const canClearUserKey = item.source === 'user';
                return (
                  <div key={item.provider} className="border border-gray-200 rounded-lg p-4">
                    <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                      <div className="min-w-0">
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-lg bg-blue-50 text-blue-700 flex items-center justify-center shrink-0">
                            <KeyRound size={18} />
                          </div>
                          <div>
                            <h3 className="font-semibold text-gray-900">{item.label}</h3>
                            <div className="text-xs text-gray-500">{item.env_var}</div>
                          </div>
                        </div>
                        <p className="text-sm text-gray-500 mt-3 max-w-2xl">{item.hint}</p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {renderStatusBadge(item.configured ? 'ok' : 'warning', item.configured ? 'Configured' : 'Missing')}
                        <span className="inline-flex items-center px-2.5 py-1 rounded-full border border-gray-200 bg-gray-50 text-xs font-medium text-gray-600">
                          {keySourceLabels[item.source]}
                        </span>
                        {item.masked_value && <span className="text-xs text-gray-500 font-mono">{item.masked_value}</span>}
                      </div>
                    </div>

                    <div className="mt-4 grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_auto] gap-3">
                      <div className="relative">
                        <input
                          type={inputType}
                          value={values[item.provider] || ''}
                          onChange={(event) => setValues(prev => ({ ...prev, [item.provider]: event.target.value }))}
                          placeholder={`Enter ${item.label} API key`}
                          className="w-full h-11 px-3 pr-11 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        />
                        <button
                          type="button"
                          onClick={() => setVisible(prev => ({ ...prev, [item.provider]: !prev[item.provider] }))}
                          className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-md text-gray-400 hover:bg-gray-100 hover:text-gray-700 flex items-center justify-center"
                          title={visible[item.provider] ? 'Hide key' : 'Show key'}
                        >
                          {visible[item.provider] ? <EyeOff size={16} /> : <Eye size={16} />}
                        </button>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => handleSave(item.provider)}
                          disabled={isBusy || !(values[item.provider] || '').trim()}
                          className="h-11 flex items-center gap-2 px-4 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                        >
                          {isBusy ? <RefreshCw size={16} className="animate-spin" /> : <Save size={16} />}
                          Save
                        </button>
                        <button
                          type="button"
                          onClick={() => handleCheck(item.provider)}
                          disabled={isBusy || !item.configured}
                          className="h-11 flex items-center gap-2 px-4 rounded-lg border border-gray-200 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                        >
                          {isBusy ? <RefreshCw size={16} className="animate-spin" /> : <Terminal size={16} />}
                          Check
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(item.provider)}
                          disabled={isBusy || !canClearUserKey}
                          className="h-11 flex items-center gap-2 px-4 rounded-lg border border-red-200 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                          title={canClearUserKey ? 'Clear your saved key' : 'No user key is saved for your account'}
                        >
                          <Trash2 size={16} />
                          Clear user key
                        </button>
                      </div>
                    </div>

                    {check && (
                      <div className={clsx('mt-4 border rounded-lg px-3 py-2 text-sm', statusStyles[check.status])}>
                        {check.message}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </SettingsSection>
        </div>
      </div>
    </Layout>
  );
};

export default SettingsPage;
