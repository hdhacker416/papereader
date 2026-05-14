import React, { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Eye, EyeOff, KeyRound, RefreshCw, Save, Trash2 } from 'lucide-react';
import clsx from 'clsx';
import Layout from '../components/Layout';
import { settingsApi } from '../api/services';
import { ApiKeyCheckResponse, ApiKeyInfo, ApiKeyProvider } from '../types';

const statusStyles = {
  ok: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  warning: 'bg-amber-50 text-amber-700 border-amber-200',
  error: 'bg-red-50 text-red-700 border-red-200',
};

const SettingsPage: React.FC = () => {
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [checks, setChecks] = useState<Record<string, ApiKeyCheckResponse>>({});
  const [loading, setLoading] = useState(true);
  const [busyProvider, setBusyProvider] = useState<string | null>(null);
  const [error, setError] = useState('');

  const loadKeys = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await settingsApi.listApiKeys();
      setKeys(data.keys);
    } catch (err) {
      console.error('Failed to load API keys:', err);
      setError('Failed to load API key settings.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadKeys();
  }, []);

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

  return (
    <Layout>
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
            <p className="text-gray-500 mt-1">Manage local provider API keys for this PaperReader instance.</p>
          </div>
          <button
            type="button"
            onClick={loadKeys}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            <RefreshCw size={18} className={clsx(loading && 'animate-spin')} />
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
          {loading ? (
            <div className="bg-white border border-gray-200 rounded-lg p-6 text-sm text-gray-500">Loading settings...</div>
          ) : (
            keys.map((item) => {
              const check = checks[item.provider];
              const isBusy = busyProvider === item.provider;
              const inputType = visible[item.provider] ? 'text' : 'password';
              return (
                <div key={item.provider} className="bg-white border border-gray-200 rounded-lg p-5">
                  <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-lg bg-blue-50 text-blue-700 flex items-center justify-center shrink-0">
                          <KeyRound size={18} />
                        </div>
                        <div>
                          <h2 className="font-semibold text-gray-900">{item.label}</h2>
                          <div className="text-xs text-gray-500">{item.env_var}</div>
                        </div>
                      </div>
                      <p className="text-sm text-gray-500 mt-3 max-w-2xl">{item.hint}</p>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <span
                        className={clsx(
                          'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium',
                          item.configured ? statusStyles.ok : statusStyles.warning,
                        )}
                      >
                        {item.configured ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
                        {item.configured ? 'Configured' : 'Missing'}
                      </span>
                      {item.masked_value && (
                        <span className="text-xs text-gray-500 font-mono">{item.masked_value}</span>
                      )}
                    </div>
                  </div>

                  <div className="mt-5 grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_auto] gap-3">
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
                        {isBusy ? <RefreshCw size={16} className="animate-spin" /> : <RefreshCw size={16} />}
                        Check
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(item.provider)}
                        disabled={isBusy || !item.configured}
                        className="h-11 flex items-center gap-2 px-4 rounded-lg border border-red-200 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                      >
                        <Trash2 size={16} />
                        Clear
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
            })
          )}
        </div>
      </div>
    </Layout>
  );
};

export default SettingsPage;
