import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  CheckSquare,
  ChevronDown,
  ChevronRight,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  FolderPlus,
  KeyRound,
  Loader2,
  Package,
  RefreshCw,
  Save,
  Square,
  Terminal,
  Trash2,
  Upload,
  Wrench,
} from 'lucide-react';
import clsx from 'clsx';
import Layout from '../components/Layout';
import { deepResearchApi, settingsApi } from '../api/services';
import {
  ApiKeyCheckResponse,
  ApiKeyInfo,
  ApiKeyProvider,
  InstalledResearchPackInfo,
  PackBuildJob,
  PackTargetOptionsResponse,
  ReleaseInfo,
  ResearchPackInfo,
  SelfCheckResponse,
} from '../types';

const PREFERRED_PACK_RELEASE_TAG = 'research-packs-ai-top-2024-2026';
const LEGACY_PACK_RELEASE_TAGS = new Set(['research-packs-v1']);
const PACK_NAME_ALIASES: Record<string, string> = {
  nips: 'neurips',
};

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

type SectionKey = 'selfCheck' | 'packs' | 'api';

const normalizePackConference = (conference: string) => PACK_NAME_ALIASES[conference] || conference;

const assetKey = (releaseTag: string, assetName: string) => `${releaseTag}::${assetName}`;

const parseReleaseAssetIdentity = (assetName: string): { conference: string; year: number } | null => {
  const shortMatch = /^([a-z0-9_+-]+)-(\d{2})\.zip$/i.exec(assetName);
  if (shortMatch) {
    return {
      conference: shortMatch[1].toLowerCase(),
      year: 2000 + Number(shortMatch[2]),
    };
  }
  const legacyMatch = /^([a-z0-9_+-]+)-(\d{4})-v\d+\.zip$/i.exec(assetName);
  if (legacyMatch) {
    return {
      conference: legacyMatch[1].toLowerCase(),
      year: Number(legacyMatch[2]),
    };
  }
  return null;
};

const formatBytes = (value: number) => `${(value / (1024 * 1024)).toFixed(1)} MB`;

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
    packs: false,
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

  const [packTargets, setPackTargets] = useState<PackTargetOptionsResponse | null>(null);
  const [selectedPackConferences, setSelectedPackConferences] = useState<string[]>([]);
  const [selectedPackYears, setSelectedPackYears] = useState<number[]>([]);
  const [releases, setReleases] = useState<ReleaseInfo[]>([]);
  const [selectedAssets, setSelectedAssets] = useState<Set<string>>(new Set());
  const [installedPacks, setInstalledPacks] = useState<InstalledResearchPackInfo[]>([]);
  const [packs, setPacks] = useState<ResearchPackInfo[]>([]);
  const [packJobs, setPackJobs] = useState<PackBuildJob[]>([]);
  const [loadingPacks, setLoadingPacks] = useState(false);
  const [loadingReleases, setLoadingReleases] = useState(false);
  const [installingAssets, setInstallingAssets] = useState(false);
  const [buildingPacks, setBuildingPacks] = useState(false);
  const [uploadingPackKey, setUploadingPackKey] = useState('');
  const [packMessage, setPackMessage] = useState('');
  const [releaseOwner, setReleaseOwner] = useState('hdhacker416');
  const [releaseRepo, setReleaseRepo] = useState('papereader');
  const [releaseTag, setReleaseTag] = useState(PREFERRED_PACK_RELEASE_TAG);

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

  const fetchReleases = async () => {
    setLoadingReleases(true);
    try {
      const response = await deepResearchApi.listReleases();
      setReleases(response.releases);
      setReleaseTag((current) => {
        const trimmed = current.trim();
        if (trimmed && !LEGACY_PACK_RELEASE_TAGS.has(trimmed)) {
          return current;
        }
        if (response.releases.some((release) => release.tag_name === PREFERRED_PACK_RELEASE_TAG)) {
          return PREFERRED_PACK_RELEASE_TAG;
        }
        return response.releases[0]?.tag_name || current;
      });
    } catch (err) {
      console.error('Failed to fetch GitHub releases:', err);
      setPackMessage('Failed to load GitHub releases.');
    } finally {
      setLoadingReleases(false);
    }
  };

  const fetchPacks = async () => {
    const [localResult, installedResult, jobsResult, targetsResult] = await Promise.allSettled([
      deepResearchApi.listPacks(),
      deepResearchApi.listInstalledPacks(),
      deepResearchApi.listPackBuildJobs(),
      deepResearchApi.listPackTargets(),
    ]);
    if (localResult.status === 'fulfilled') {
      setPacks(localResult.value);
    }
    if (installedResult.status === 'fulfilled') {
      setInstalledPacks(installedResult.value);
    }
    if (jobsResult.status === 'fulfilled') {
      setPackJobs(jobsResult.value);
    }
    if (targetsResult.status === 'fulfilled') {
      setPackTargets(targetsResult.value);
      setSelectedPackConferences((current) => current.length > 0 ? current : targetsResult.value.conferences.map((item) => item.code));
      setSelectedPackYears((current) => current.length > 0 ? current : targetsResult.value.default_years);
    }
  };

  const refreshPacks = async () => {
    setLoadingPacks(true);
    setPackMessage('');
    try {
      await Promise.all([fetchPacks(), fetchReleases()]);
    } finally {
      setLoadingPacks(false);
    }
  };

  useEffect(() => {
    if (!openSections.packs) {
      return;
    }
    refreshPacks();
  }, [openSections.packs]);

  const hasActivePackJobs = packJobs.some((job) => job.status === 'queued' || job.status === 'running');

  useEffect(() => {
    if (!openSections.packs || !hasActivePackJobs) {
      return;
    }
    const interval = window.setInterval(() => {
      fetchPacks();
    }, 3000);
    return () => window.clearInterval(interval);
  }, [openSections.packs, hasActivePackJobs]);

  const requestPackYears = useMemo(
    () => selectedPackYears.length > 0 ? [...selectedPackYears].sort((a, b) => b - a) : undefined,
    [selectedPackYears],
  );

  const effectivePackYears = useMemo(
    () => requestPackYears ?? (packTargets?.default_years ?? []),
    [packTargets, requestPackYears],
  );

  const filteredPackConferences = useMemo(() => {
    if (!packTargets) {
      return [];
    }
    const yearSet = new Set(effectivePackYears);
    return packTargets.conferences.filter((conference) =>
      conference.years.some((year) => yearSet.has(year)),
    );
  }, [effectivePackYears, packTargets]);

  const selectedPackTargets = useMemo(
    () => selectedPackConferences.flatMap((conference) => effectivePackYears.map((year) => ({
      conference,
      year,
      key: `${conference}-${year}`,
      releaseConference: normalizePackConference(conference),
    }))),
    [effectivePackYears, selectedPackConferences],
  );

  const matchingReleaseAssets = useMemo(() => {
    const wanted = new Map(selectedPackTargets.map((item) => [`${item.releaseConference}-${item.year}`, item]));
    const seen = new Set<string>();
    const matches: Array<{ releaseTag: string; assetName: string; downloadUrl: string; conference: string; year: number }> = [];
    for (const release of releases) {
      for (const asset of release.assets) {
        const identity = parseReleaseAssetIdentity(asset.name);
        if (!identity) {
          continue;
        }
        const wantedItem = wanted.get(`${identity.conference}-${identity.year}`);
        if (!wantedItem || seen.has(wantedItem.key)) {
          continue;
        }
        seen.add(wantedItem.key);
        matches.push({
          releaseTag: release.tag_name,
          assetName: asset.name,
          downloadUrl: asset.browser_download_url,
          conference: wantedItem.conference,
          year: wantedItem.year,
        });
      }
    }
    return matches;
  }, [releases, selectedPackTargets]);

  const totalReleaseAssets = releases.reduce((sum, release) => sum + release.assets.length, 0);
  const allPackYearsSelected = !!packTargets && packTargets.years.length > 0 && selectedPackYears.length === packTargets.years.length;
  const allVisiblePackConferencesSelected = filteredPackConferences.length > 0
    && filteredPackConferences.every((conference) => selectedPackConferences.includes(conference.code));

  const toggleAsset = (releaseTagValue: string, assetName: string) => {
    const key = assetKey(releaseTagValue, assetName);
    setSelectedAssets((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const toggleAllAssets = () => {
    const allAssets = releases.flatMap((release) => release.assets.map((asset) => assetKey(release.tag_name, asset.name)));
    setSelectedAssets((current) => current.size === allAssets.length ? new Set() : new Set(allAssets));
  };

  const togglePackYear = (year: number) => {
    setSelectedPackYears((current) => current.includes(year) ? current.filter((item) => item !== year) : [...current, year].sort((a, b) => b - a));
  };

  const toggleAllPackYears = () => {
    if (!packTargets) {
      return;
    }
    setSelectedPackYears(allPackYearsSelected ? [] : [...packTargets.years].sort((a, b) => b - a));
  };

  const togglePackConference = (code: string) => {
    setSelectedPackConferences((current) => current.includes(code) ? current.filter((item) => item !== code) : [...current, code]);
  };

  const toggleAllVisiblePackConferences = () => {
    if (filteredPackConferences.length === 0) {
      return;
    }
    if (allVisiblePackConferencesSelected) {
      setSelectedPackConferences((current) => current.filter((code) => !filteredPackConferences.some((conference) => conference.code === code)));
      return;
    }
    setSelectedPackConferences((current) => Array.from(new Set([...current, ...filteredPackConferences.map((item) => item.code)])));
  };

  const installSelectedAssets = async () => {
    if (installingAssets || selectedAssets.size === 0) {
      return;
    }
    setInstallingAssets(true);
    setPackMessage('');
    try {
      const assets = releases.flatMap((release) =>
        release.assets
          .filter((asset) => selectedAssets.has(assetKey(release.tag_name, asset.name)))
          .map((asset) => ({
            release_tag: release.tag_name,
            asset_name: asset.name,
            download_url: asset.browser_download_url,
          })),
      );
      const result = await deepResearchApi.installReleaseAssets({ assets });
      setPackMessage(`Installed ${result.installed_count} pack(s).`);
      setSelectedAssets(new Set());
      await fetchPacks();
    } catch (err) {
      console.error('Failed to install selected release assets:', err);
      setPackMessage('Install failed.');
    } finally {
      setInstallingAssets(false);
    }
  };

  const installMatchingAssets = async () => {
    if (installingAssets || matchingReleaseAssets.length === 0) {
      return;
    }
    setInstallingAssets(true);
    setPackMessage('');
    try {
      const result = await deepResearchApi.installReleaseAssets({
        assets: matchingReleaseAssets.map((asset) => ({
          release_tag: asset.releaseTag,
          asset_name: asset.assetName,
          download_url: asset.downloadUrl,
        })),
      });
      setPackMessage(`Installed ${result.installed_count} matching pack(s).`);
      await fetchPacks();
    } catch (err) {
      console.error('Failed to install matching release assets:', err);
      setPackMessage('Install failed.');
    } finally {
      setInstallingAssets(false);
    }
  };

  const buildPacks = async () => {
    if (buildingPacks || selectedPackConferences.length === 0) {
      return;
    }
    setBuildingPacks(true);
    setPackMessage('');
    try {
      const result = await deepResearchApi.createPackBuildJob({
        conferences: selectedPackConferences,
        years: requestPackYears,
        version: 'v1',
      });
      setPackMessage(`Build job queued: ${result.total_targets} target(s).`);
      await fetchPacks();
    } catch (err) {
      console.error('Failed to build packs:', err);
      setPackMessage('Build failed.');
    } finally {
      setBuildingPacks(false);
    }
  };

  const resumePackJob = async (jobId: string) => {
    setPackMessage('');
    try {
      const job = await deepResearchApi.resumePackBuildJob(jobId);
      setPackMessage(`Resumed build job ${job.id}.`);
      await fetchPacks();
    } catch (err) {
      console.error('Failed to resume pack build job:', err);
      setPackMessage('Resume failed.');
    }
  };

  const uploadPack = async (pack: ResearchPackInfo) => {
    const key = `${pack.conference}-${pack.year}-${pack.version}`;
    if (uploadingPackKey) {
      return;
    }
    setUploadingPackKey(key);
    setPackMessage('');
    try {
      const result = await deepResearchApi.uploadPack({
        conference: pack.conference,
        year: pack.year,
        version: pack.version,
        owner: releaseOwner.trim(),
        repo: releaseRepo.trim(),
        tag: releaseTag.trim(),
        release_name: releaseTag.trim(),
      });
      setPackMessage(`Uploaded ${pack.pack_name} to ${result.release_url}`);
      await fetchReleases();
    } catch (err) {
      console.error('Failed to upload pack:', err);
      setPackMessage(`Upload failed for ${pack.pack_name}. Check GITHUB_TOKEN.`);
    } finally {
      setUploadingPackKey('');
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
            <p className="text-gray-500 mt-1">Manage environment checks, research packs, and provider API keys.</p>
          </div>
          <button
            type="button"
            onClick={() => {
              loadKeys();
              if (openSections.packs) {
                refreshPacks();
              }
            }}
            disabled={loadingKeys || loadingPacks}
            className="flex items-center gap-2 px-4 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            <RefreshCw size={18} className={clsx((loadingKeys || loadingPacks) && 'animate-spin')} />
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
            description="Run the environment check for keys, search data, providers, and pack readiness."
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
            id="packs"
            title="Packs Management"
            description="Download installed research packs, build local packs, and upload packs to GitHub Releases."
            icon={<Package size={18} />}
            open={openSections.packs}
            onToggle={toggleSection}
          >
            <div className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="text-sm text-gray-600">
                  Installed: <span className="font-medium text-gray-900">{installedPacks.length}</span>
                  <span className="mx-2 text-gray-300">|</span>
                  Local: <span className="font-medium text-gray-900">{packs.length}</span>
                  <span className="mx-2 text-gray-300">|</span>
                  Release assets: <span className="font-medium text-gray-900">{totalReleaseAssets}</span>
                </div>
                <button
                  type="button"
                  onClick={refreshPacks}
                  disabled={loadingPacks || loadingReleases}
                  className="flex items-center gap-2 px-3 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                >
                  {(loadingPacks || loadingReleases) ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
                  Refresh Packs
                </button>
              </div>

              {packMessage && (
                <div className="border border-gray-200 bg-gray-50 rounded-lg px-4 py-3 text-sm text-gray-700">{packMessage}</div>
              )}

              <div className="border border-gray-200 rounded-lg p-4">
                <h3 className="font-semibold text-gray-900">Installed Packs</h3>
                <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                  {installedPacks.length === 0 ? (
                    <div className="text-sm text-gray-500">No installed packs yet.</div>
                  ) : installedPacks.map((pack) => (
                    <div key={`${pack.conference}-${pack.year}-${pack.version}`} className="border border-gray-200 rounded-lg px-3 py-2">
                      <div className="font-medium text-gray-900">{pack.pack_name}</div>
                      <div className="text-sm text-gray-500 mt-1">{pack.conference.toUpperCase()} {pack.year} · {pack.version}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="border border-gray-200 rounded-lg p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="font-semibold text-gray-900">Download From GitHub Releases</h3>
                    <p className="text-sm text-gray-500 mt-1">{matchingReleaseAssets.length} matching assets for the selected pack targets.</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={installMatchingAssets}
                      disabled={installingAssets || matchingReleaseAssets.length === 0}
                      className="flex items-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                    >
                      {installingAssets ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
                      Download Matching
                    </button>
                    <button
                      type="button"
                      onClick={installSelectedAssets}
                      disabled={installingAssets || selectedAssets.size === 0}
                      className="flex items-center gap-2 px-3 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                    >
                      {installingAssets ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
                      Download Selected
                    </button>
                  </div>
                </div>
                <div className="mt-4 flex items-center justify-between text-sm text-gray-600">
                  <button
                    type="button"
                    onClick={toggleAllAssets}
                    disabled={totalReleaseAssets === 0}
                    className="flex items-center gap-2 hover:text-blue-700 disabled:opacity-50"
                  >
                    {selectedAssets.size === totalReleaseAssets && totalReleaseAssets > 0 ? <CheckSquare size={18} /> : <Square size={18} />}
                    Select all assets
                  </button>
                  <span>{selectedAssets.size} selected / {totalReleaseAssets} assets</span>
                </div>
                <div className="mt-4 space-y-3">
                  {loadingReleases ? (
                    <div className="text-sm text-gray-500">Loading releases...</div>
                  ) : releases.length === 0 ? (
                    <div className="text-sm text-gray-500">No releases found.</div>
                  ) : releases.map((release) => (
                    <div key={release.id} className="border border-gray-200 rounded-lg p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <div className="font-medium text-gray-900">{release.name || release.tag_name}</div>
                          <div className="text-sm text-gray-500 mt-1">{release.tag_name}</div>
                        </div>
                        <a href={release.html_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700">
                          View <ExternalLink size={14} />
                        </a>
                      </div>
                      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2">
                        {release.assets.length === 0 ? (
                          <div className="text-sm text-gray-500">No zip assets in this release.</div>
                        ) : release.assets.map((asset) => {
                          const selected = selectedAssets.has(assetKey(release.tag_name, asset.name));
                          return (
                            <button
                              key={asset.id}
                              type="button"
                              onClick={() => toggleAsset(release.tag_name, asset.name)}
                              className={clsx(
                                'text-left border rounded-lg px-3 py-2 transition-colors',
                                selected ? 'border-blue-400 bg-blue-50' : 'border-gray-200 hover:border-blue-300',
                              )}
                            >
                              <div className="flex items-start gap-2">
                                <div className="mt-0.5 text-blue-600 shrink-0">{selected ? <CheckSquare size={16} /> : <Square size={16} />}</div>
                                <div className="min-w-0">
                                  <div className="font-medium text-gray-900 break-all">{asset.name}</div>
                                  <div className="text-xs text-gray-500 mt-1">{formatBytes(asset.size)} · {asset.download_count} downloads</div>
                                </div>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="border border-gray-200 rounded-lg p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="font-semibold text-gray-900">Build And Upload Local Packs</h3>
                    <p className="text-sm text-gray-500 mt-1">Developer workflow for generating packs locally and publishing them to a release.</p>
                  </div>
                  <button
                    type="button"
                    onClick={buildPacks}
                    disabled={buildingPacks || selectedPackConferences.length === 0}
                    className="flex items-center gap-2 px-3 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800 disabled:opacity-50"
                  >
                    {buildingPacks ? <Loader2 size={16} className="animate-spin" /> : <FolderPlus size={16} />}
                    Build Selected
                  </button>
                </div>

                <div className="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-3">
                  <input value={releaseOwner} onChange={(event) => setReleaseOwner(event.target.value)} placeholder="GitHub owner" className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  <input value={releaseRepo} onChange={(event) => setReleaseRepo(event.target.value)} placeholder="GitHub repo" className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  <input value={releaseTag} onChange={(event) => setReleaseTag(event.target.value)} placeholder="Release tag" className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                </div>

                <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-sm font-semibold text-gray-900">Target Years</h4>
                      <button type="button" onClick={toggleAllPackYears} className="text-xs text-blue-600 hover:text-blue-700">
                        {allPackYearsSelected ? 'Clear all' : 'Select all'}
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {(packTargets?.years || []).map((year) => (
                        <button
                          key={year}
                          type="button"
                          onClick={() => togglePackYear(year)}
                          className={clsx(
                            'px-3 py-1.5 rounded-lg border text-sm',
                            selectedPackYears.includes(year) ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-gray-200 text-gray-600',
                          )}
                        >
                          {year}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-sm font-semibold text-gray-900">Target Conferences</h4>
                      <button type="button" onClick={toggleAllVisiblePackConferences} className="text-xs text-blue-600 hover:text-blue-700">
                        {allVisiblePackConferencesSelected ? 'Clear all' : 'Select visible'}
                      </button>
                    </div>
                    <div className="max-h-36 overflow-y-auto flex flex-wrap gap-2 pr-1">
                      {filteredPackConferences.map((conference) => (
                        <button
                          key={conference.code}
                          type="button"
                          onClick={() => togglePackConference(conference.code)}
                          className={clsx(
                            'px-3 py-1.5 rounded-lg border text-sm',
                            selectedPackConferences.includes(conference.code) ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-gray-200 text-gray-600',
                          )}
                        >
                          {conference.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <div>
                    <h4 className="text-sm font-semibold text-gray-900 mb-2">Build Jobs</h4>
                    <div className="space-y-2">
                      {packJobs.length === 0 ? (
                        <div className="text-sm text-gray-500">No pack build jobs yet.</div>
                      ) : packJobs.map((job) => (
                        <div key={job.id} className="border border-gray-200 rounded-lg p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="font-medium text-gray-900">{job.total_targets} target(s) · {job.version}</div>
                              <div className="text-xs text-gray-500 mt-1">{job.completed_targets}/{job.total_targets} completed · {job.status}</div>
                            </div>
                            {job.can_resume && (
                              <button type="button" onClick={() => resumePackJob(job.id)} className="px-2 py-1 rounded-md bg-slate-900 text-white text-xs">
                                Resume
                              </button>
                            )}
                          </div>
                          <div className="mt-3 h-2 rounded-full bg-gray-100 overflow-hidden">
                            <div className={clsx('h-full', job.status === 'failed' ? 'bg-red-500' : 'bg-blue-600')} style={{ width: `${job.progress_percent}%` }} />
                          </div>
                          {job.progress_message && <div className="mt-2 text-xs text-gray-600">{job.progress_message}</div>}
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-gray-900 mb-2">Local Packs</h4>
                    <div className="space-y-2">
                      {packs.length === 0 ? (
                        <div className="text-sm text-gray-500">No local packs yet.</div>
                      ) : packs.map((pack) => {
                        const key = `${pack.conference}-${pack.year}-${pack.version}`;
                        return (
                          <div key={key} className="border border-gray-200 rounded-lg px-3 py-2 flex items-center justify-between gap-3">
                            <div className="min-w-0">
                              <div className="font-medium text-gray-900 break-all">{pack.pack_name}</div>
                              <div className="text-xs text-gray-500 mt-1">{pack.conference.toUpperCase()} {pack.year} · {formatBytes(pack.pack_size_bytes)}</div>
                            </div>
                            <button
                              type="button"
                              onClick={() => uploadPack(pack)}
                              disabled={uploadingPackKey !== '' || !releaseOwner.trim() || !releaseRepo.trim() || !releaseTag.trim()}
                              className="shrink-0 flex items-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
                            >
                              {uploadingPackKey === key ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
                              Upload
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </SettingsSection>

          <SettingsSection
            id="api"
            title="API Management"
            description="Configure Gemini, DeepSeek, DashScope, and GitHub credentials for your account."
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
