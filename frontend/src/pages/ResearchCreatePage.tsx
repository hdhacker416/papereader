import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Search, CheckSquare, Square, FolderPlus, Sparkles, RefreshCw, Download, Upload, ChevronDown, ChevronRight } from 'lucide-react';
import Layout from '../components/Layout';
import PromptListEditor from '../components/PromptListEditor';
import { deepResearchApi, templatesApi } from '../api/services';
import {
  ConferenceSearchHit,
  DeepResearchTargetOptionsResponse,
  PackBuildJob,
  PackTargetOptionsResponse,
  ReleaseInfo,
  ResearchPackInfo,
  Template,
} from '../types';
import clsx from 'clsx';

const PACK_NAME_ALIASES: Record<string, string> = {
  nips: 'neurips',
};

const PREFERRED_PACK_RELEASE_TAG = 'research-packs-ai-top-2024-2026';
const LEGACY_PACK_RELEASE_TAGS = new Set(['research-packs-v1']);
const RESEARCH_PREFERENCES_STORAGE_KEY = 'research-create-preferences-v1';
const ALLOWED_MODEL_NAMES = new Set(['gemini-3-flash-preview', 'gemini-3-pro-preview']);

const normalizePackConference = (conference: string) => PACK_NAME_ALIASES[conference] || conference;

type ResearchPreferences = {
  selectedTargetConferences?: string[];
  selectedTargetYears?: number[];
  searchTopKPerAsset?: number;
  searchTopKGlobal?: number;
  maxSearchRounds?: number;
  maxQueriesPerRound?: number;
  maxFullReads?: number;
  modelName?: string;
  templateId?: string;
  customReadingPrompts?: string[];
};

const loadResearchPreferences = (): ResearchPreferences | null => {
  try {
    const raw = window.localStorage.getItem(RESEARCH_PREFERENCES_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed as ResearchPreferences : null;
  } catch (error) {
    console.error('Failed to load research preferences:', error);
    return null;
  }
};

const saveResearchPreferences = (preferences: ResearchPreferences) => {
  try {
    window.localStorage.setItem(RESEARCH_PREFERENCES_STORAGE_KEY, JSON.stringify(preferences));
  } catch (error) {
    console.error('Failed to save research preferences:', error);
  }
};

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

const ResearchCreatePage: React.FC = () => {
  const navigate = useNavigate();
  const [targetOptions, setTargetOptions] = useState<DeepResearchTargetOptionsResponse | null>(null);
  const [packTargetOptions, setPackTargetOptions] = useState<PackTargetOptionsResponse | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedTargetConferences, setSelectedTargetConferences] = useState<string[]>([]);
  const [selectedTargetYears, setSelectedTargetYears] = useState<number[]>([]);
  const [selectedPackConferences, setSelectedPackConferences] = useState<string[]>([]);
  const [selectedPackYears, setSelectedPackYears] = useState<number[]>([]);
  const [searchTopKPerAsset, setSearchTopKPerAsset] = useState(8);
  const [searchTopKGlobal, setSearchTopKGlobal] = useState(24);
  const [maxSearchRounds, setMaxSearchRounds] = useState(3);
  const [maxQueriesPerRound, setMaxQueriesPerRound] = useState(4);
  const [maxFullReads, setMaxFullReads] = useState(8);
  const [query, setQuery] = useState('');
  const [modelName, setModelName] = useState('gemini-3-flash-preview');
  const [workflow, setWorkflow] = useState<'research' | 'packs'>('research');
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<ConferenceSearchHit[]>([]);
  const [selectedHits, setSelectedHits] = useState<Set<string>>(new Set());
  const [taskName, setTaskName] = useState('Research Task');
  const [templateId, setTemplateId] = useState('');
  const [customReadingPrompts, setCustomReadingPrompts] = useState<string[]>(['']);
  const [creatingTask, setCreatingTask] = useState(false);
  const [releases, setReleases] = useState<ReleaseInfo[]>([]);
  const [loadingReleases, setLoadingReleases] = useState(false);
  const [installingAssets, setInstallingAssets] = useState(false);
  const [selectedAssets, setSelectedAssets] = useState<Set<string>>(new Set());
  const [installMessage, setInstallMessage] = useState('');
  const [packs, setPacks] = useState<ResearchPackInfo[]>([]);
  const [loadingPacks, setLoadingPacks] = useState(false);
  const [packJobs, setPackJobs] = useState<PackBuildJob[]>([]);
  const [loadingPackJobs, setLoadingPackJobs] = useState(false);
  const [buildingPacks, setBuildingPacks] = useState(false);
  const [uploadingPackKey, setUploadingPackKey] = useState('');
  const [packMessage, setPackMessage] = useState('');
  const [releaseOwner, setReleaseOwner] = useState('hdhacker416');
  const [releaseRepo, setReleaseRepo] = useState('papereader');
  const [releaseTag, setReleaseTag] = useState(PREFERRED_PACK_RELEASE_TAG);
  const [researchYearsExpanded, setResearchYearsExpanded] = useState(true);
  const [researchConferencesExpanded, setResearchConferencesExpanded] = useState(true);
  const [packYearsExpanded, setPackYearsExpanded] = useState(true);
  const [packConferencesExpanded, setPackConferencesExpanded] = useState(true);
  const [preferencesHydrated, setPreferencesHydrated] = useState(false);

  useEffect(() => {
    const fetchInitialData = async () => {
      const savedPreferences = loadResearchPreferences();
      try {
        const [templateResult, targetResult, packResult] = await Promise.allSettled([
          templatesApi.list(),
          deepResearchApi.listTargets(),
          deepResearchApi.listPackTargets(),
        ]);

        if (templateResult.status === 'fulfilled') {
          const templateData = templateResult.value;
          setTemplates(templateData);
          const defaultTemplate = templateData.find((item) => item.is_default) || templateData[0];
          const validTemplateIds = new Set(templateData.map((item) => item.id));
          const preferredTemplateId = savedPreferences?.templateId && validTemplateIds.has(savedPreferences.templateId)
            ? savedPreferences.templateId
            : (defaultTemplate?.id || '');
          setTemplateId(preferredTemplateId);
          const preferredTemplate = templateData.find((item) => item.id === preferredTemplateId) || defaultTemplate;
          const savedPrompts = (savedPreferences?.customReadingPrompts || [])
            .map((item) => item.trim())
            .filter(Boolean);
          if (savedPrompts.length > 0) {
            setCustomReadingPrompts(savedPrompts);
          } else {
            setCustomReadingPrompts(preferredTemplate?.content.length ? preferredTemplate.content : ['']);
          }
          if (savedPreferences?.modelName && ALLOWED_MODEL_NAMES.has(savedPreferences.modelName)) {
            setModelName(savedPreferences.modelName);
          }
          if (typeof savedPreferences?.searchTopKPerAsset === 'number') {
            setSearchTopKPerAsset(savedPreferences.searchTopKPerAsset);
          }
          if (typeof savedPreferences?.searchTopKGlobal === 'number') {
            setSearchTopKGlobal(savedPreferences.searchTopKGlobal);
          }
          if (typeof savedPreferences?.maxSearchRounds === 'number') {
            setMaxSearchRounds(savedPreferences.maxSearchRounds);
          }
          if (typeof savedPreferences?.maxQueriesPerRound === 'number') {
            setMaxQueriesPerRound(savedPreferences.maxQueriesPerRound);
          }
          if (typeof savedPreferences?.maxFullReads === 'number') {
            setMaxFullReads(savedPreferences.maxFullReads);
          }
        } else {
          console.error('Failed to fetch templates:', templateResult.reason);
        }

        if (targetResult.status === 'fulfilled') {
          const targetData = targetResult.value;
          setTargetOptions(targetData);
          const availableConferenceCodes = new Set(targetData.conferences.map((item) => item.code));
          const savedConferences = (savedPreferences?.selectedTargetConferences || [])
            .filter((item) => availableConferenceCodes.has(item));
          const savedYears = (savedPreferences?.selectedTargetYears || [])
            .filter((item) => targetData.years.includes(item));
          setSelectedTargetConferences(
            savedConferences.length > 0 ? savedConferences : targetData.conferences.map((item) => item.code),
          );
          setSelectedTargetYears(savedYears.length > 0 ? savedYears : targetData.default_years);
        } else {
          console.error('Failed to fetch research target options:', targetResult.reason);
        }

        if (packResult.status === 'fulfilled') {
          const packData = packResult.value;
          setPackTargetOptions(packData);
          setSelectedPackConferences(packData.conferences.map((item) => item.code));
          setSelectedPackYears(packData.default_years);
        } else {
          console.error('Failed to fetch pack target options:', packResult.reason);
        }
      } catch (error) {
        console.error('Failed to fetch research setup data:', error);
      } finally {
        setPreferencesHydrated(true);
        setLoading(false);
      }
    };
    fetchInitialData();
  }, []);

  const requestTargetYears = useMemo(
    () => selectedTargetYears.length > 0 ? [...selectedTargetYears].sort((a, b) => b - a) : undefined,
    [selectedTargetYears],
  );

  const effectiveTargetYears = useMemo(
    () => requestTargetYears ?? (targetOptions?.default_years ?? []),
    [requestTargetYears, targetOptions],
  );

  const filteredTargetConferences = useMemo(() => {
    if (!targetOptions) {
      return [];
    }
    const yearSet = new Set(effectiveTargetYears);
    return targetOptions.conferences.filter((conference) =>
      conference.years.some((item) => yearSet.has(item.year)),
    );
  }, [effectiveTargetYears, targetOptions]);

  const totalTargetPapers = useMemo(() => {
    if (!targetOptions) {
      return 0;
    }
    const conferenceSet = new Set(selectedTargetConferences);
    const yearSet = new Set(effectiveTargetYears);
    return targetOptions.conferences
      .filter((conference) => conferenceSet.has(conference.code))
      .reduce(
        (sum, conference) => sum + conference.years
          .filter((item) => yearSet.has(item.year))
          .reduce((yearSum, item) => yearSum + item.paper_count, 0),
        0,
      );
  }, [effectiveTargetYears, selectedTargetConferences, targetOptions]);

  const normalizedSearchTopKPerAsset = Math.max(1, Math.floor(searchTopKPerAsset));
  const normalizedSearchTopKGlobal = Math.max(normalizedSearchTopKPerAsset, Math.floor(searchTopKGlobal));
  const normalizedMaxSearchRounds = Math.min(20, Math.max(1, Math.floor(maxSearchRounds)));
  const normalizedMaxQueriesPerRound = Math.min(10, Math.max(1, Math.floor(maxQueriesPerRound)));
  const normalizedMaxFullReads = Math.max(1, Math.floor(maxFullReads));
  const normalizedCustomReadingPrompts = customReadingPrompts.map((item) => item.trim()).filter(Boolean);

  const requestPackYears = useMemo(
    () => selectedPackYears.length > 0 ? [...selectedPackYears].sort((a, b) => b - a) : undefined,
    [selectedPackYears],
  );

  const effectivePackYears = useMemo(
    () => requestPackYears ?? (packTargetOptions?.default_years ?? []),
    [packTargetOptions, requestPackYears],
  );

  const filteredPackConferences = useMemo(() => {
    if (!packTargetOptions) {
      return [];
    }
    const yearSet = new Set(effectivePackYears);
    return packTargetOptions.conferences.filter((conference) =>
      conference.years.some((year) => yearSet.has(year)),
    );
  }, [effectivePackYears, packTargetOptions]);

  const totalReleaseAssets = releases.reduce((sum, release) => sum + release.assets.length, 0);
  const hasActivePackJobs = packJobs.some((job) => job.status === 'queued' || job.status === 'running');
  const allTargetYearsSelected = !!targetOptions && targetOptions.years.length > 0 && selectedTargetYears.length === targetOptions.years.length;
  const allVisibleTargetConferencesSelected = filteredTargetConferences.length > 0
    && filteredTargetConferences.every((conference) => selectedTargetConferences.includes(conference.code));
  const allPackYearsSelected = !!packTargetOptions && packTargetOptions.years.length > 0 && selectedPackYears.length === packTargetOptions.years.length;
  const allVisiblePackConferencesSelected = filteredPackConferences.length > 0
    && filteredPackConferences.every((conference) => selectedPackConferences.includes(conference.code));
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
    const matches: Array<{
      releaseTag: string;
      assetName: string;
      downloadUrl: string;
      conference: string;
      year: number;
    }> = [];
    for (const release of releases) {
      for (const asset of release.assets) {
        const identity = parseReleaseAssetIdentity(asset.name);
        if (!identity) {
          continue;
        }
        const wantedItem = wanted.get(`${identity.conference}-${identity.year}`);
        if (!wantedItem) {
          continue;
        }
        if (seen.has(wantedItem.key)) {
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
  const matchingReleaseTargetKeys = new Set(matchingReleaseAssets.map((item) => `${item.conference}-${item.year}`));
  const missingReleaseTargets = selectedPackTargets.filter((item) => !matchingReleaseTargetKeys.has(item.key));

  useEffect(() => {
    const allowed = new Set(filteredTargetConferences.map((conference) => conference.code));
    setSelectedTargetConferences((current) => current.filter((code) => allowed.has(code)));
  }, [filteredTargetConferences]);

  useEffect(() => {
    if (workflow !== 'packs') {
      return;
    }
    fetchPackJobs();
    const interval = window.setInterval(() => {
      fetchPackJobs();
      if (hasActivePackJobs) {
        fetchPacks();
      }
    }, hasActivePackJobs ? 2500 : 10000);
    return () => window.clearInterval(interval);
  }, [workflow, hasActivePackJobs]);

  useEffect(() => {
    const allowed = new Set(filteredPackConferences.map((conference) => conference.code));
    setSelectedPackConferences((current) => current.filter((code) => allowed.has(code)));
  }, [filteredPackConferences]);

  useEffect(() => {
    if (!preferencesHydrated) {
      return;
    }
    saveResearchPreferences({
      selectedTargetConferences,
      selectedTargetYears,
      searchTopKPerAsset,
      searchTopKGlobal,
      maxSearchRounds,
      maxQueriesPerRound,
      maxFullReads,
      modelName,
      templateId,
      customReadingPrompts: customReadingPrompts.map((item) => item.trim()).filter(Boolean),
    });
  }, [
    preferencesHydrated,
    selectedTargetConferences,
    selectedTargetYears,
    searchTopKPerAsset,
    searchTopKGlobal,
    maxSearchRounds,
    maxQueriesPerRound,
    maxFullReads,
    modelName,
    templateId,
    customReadingPrompts,
  ]);

  const toggleTargetConference = (code: string) => {
    setSelectedTargetConferences((current) => current.includes(code) ? current.filter((item) => item !== code) : [...current, code]);
  };

  const toggleTargetYear = (year: number) => {
    setSelectedTargetYears((current) => current.includes(year) ? current.filter((item) => item !== year) : [...current, year].sort((a, b) => b - a));
  };

  const toggleAllTargetYears = () => {
    if (!targetOptions) {
      return;
    }
    setSelectedTargetYears(allTargetYearsSelected ? [] : [...targetOptions.years].sort((a, b) => b - a));
  };

  const toggleAllVisibleTargetConferences = () => {
    if (filteredTargetConferences.length === 0) {
      return;
    }
    if (allVisibleTargetConferencesSelected) {
      setSelectedTargetConferences((current) => current.filter((code) => !filteredTargetConferences.some((conference) => conference.code === code)));
      return;
    }
    setSelectedTargetConferences((current) => {
      const next = new Set(current);
      for (const conference of filteredTargetConferences) {
        next.add(conference.code);
      }
      return Array.from(next);
    });
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
    setSelectedPackConferences((current) => {
      const next = new Set(current);
      for (const conference of filteredPackConferences) {
        next.add(conference.code);
      }
      return Array.from(next);
    });
  };

  const togglePackYear = (year: number) => {
    setSelectedPackYears((current) => current.includes(year) ? current.filter((item) => item !== year) : [...current, year].sort((a, b) => b - a));
  };

  const handleTemplateChange = (nextTemplateId: string) => {
    setTemplateId(nextTemplateId);
    const selectedTemplate = templates.find((item) => item.id === nextTemplateId);
    setCustomReadingPrompts(selectedTemplate?.content.length ? selectedTemplate.content : ['']);
  };

  const toggleAllPackYears = () => {
    if (!packTargetOptions) {
      return;
    }
    setSelectedPackYears(allPackYearsSelected ? [] : [...packTargetOptions.years].sort((a, b) => b - a));
  };

  const toggleHit = (paperId: string) => {
    setSelectedHits((current) => {
      const next = new Set(current);
      if (next.has(paperId)) {
        next.delete(paperId);
      } else {
        next.add(paperId);
      }
      return next;
    });
  };

  const assetKey = (releaseTagValue: string, assetName: string) => `${releaseTagValue}::${assetName}`;

  const fetchReleases = async () => {
    setLoadingReleases(true);
    try {
      const response = await deepResearchApi.listReleases();
      setReleases(response.releases);
      setReleaseTag((current) => {
        const trimmed = current.trim();
        const shouldReplace = trimmed === '' || LEGACY_PACK_RELEASE_TAGS.has(trimmed);
        if (!shouldReplace) {
          return current;
        }
        if (response.releases.some((release) => release.tag_name === PREFERRED_PACK_RELEASE_TAG)) {
          return PREFERRED_PACK_RELEASE_TAG;
        }
        return response.releases[0]?.tag_name || current;
      });
    } catch (error) {
      console.error('Failed to fetch GitHub releases:', error);
    } finally {
      setLoadingReleases(false);
    }
  };

  const fetchPacks = async () => {
    setLoadingPacks(true);
    try {
      const data = await deepResearchApi.listPacks();
      setPacks(data);
    } catch (error) {
      console.error('Failed to fetch local packs:', error);
    } finally {
      setLoadingPacks(false);
    }
  };

  const fetchPackJobs = async () => {
    setLoadingPackJobs(true);
    try {
      const data = await deepResearchApi.listPackBuildJobs();
      setPackJobs(data);
    } catch (error) {
      console.error('Failed to fetch pack build jobs:', error);
    } finally {
      setLoadingPackJobs(false);
    }
  };

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

  const handleToggleAllAssets = () => {
    const allAssets = releases.flatMap((release) => release.assets.map((asset) => assetKey(release.tag_name, asset.name)));
    setSelectedAssets((current) => {
      if (current.size === allAssets.length) {
        return new Set();
      }
      return new Set(allAssets);
    });
  };

  const handleBuildPacks = async () => {
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
      await fetchPackJobs();
    } catch (error) {
      console.error('Failed to build packs:', error);
      setPackMessage('Build failed.');
    } finally {
      setBuildingPacks(false);
    }
  };

  const handleResumePackJob = async (jobId: string) => {
    try {
      const job = await deepResearchApi.resumePackBuildJob(jobId);
      setPackMessage(`Resumed build job ${job.id}.`);
      await fetchPackJobs();
    } catch (error) {
      console.error('Failed to resume pack build job:', error);
      setPackMessage('Resume failed.');
    }
  };

  const handleUploadPack = async (pack: ResearchPackInfo) => {
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
    } catch (error) {
      console.error('Failed to upload pack:', error);
      setPackMessage(`Upload failed for ${pack.pack_name}. Check GITHUB_TOKEN on the backend.`);
    } finally {
      setUploadingPackKey('');
    }
  };

  const handleSearch = async () => {
    if (!query.trim() || selectedTargetConferences.length === 0 || searching) {
      return;
    }
    setSearching(true);
    try {
      const response = await deepResearchApi.search({
        query: query.trim(),
        conferences: selectedTargetConferences,
        years: requestTargetYears,
        top_k_per_asset: normalizedSearchTopKPerAsset,
        top_k_global: normalizedSearchTopKGlobal,
      });
      setHits(response.results);
      setSelectedHits(new Set(response.results.slice(0, 6).map((item) => item.paper_id)));
      if (!taskName.trim()) {
        setTaskName(`Research: ${query.trim().slice(0, 40)}`);
      }
    } catch (error) {
      console.error('Failed to search conference papers:', error);
    } finally {
      setSearching(false);
    }
  };

  const handleCreateTaskFromSelection = async () => {
    if (creatingTask || !taskName.trim() || selectedHits.size === 0) {
      return;
    }
    setCreatingTask(true);
    try {
      const selectedPapers = hits
        .filter((item) => selectedHits.has(item.paper_id))
        .map((item) => ({
          paper_id: item.paper_id,
          conference: item.conference,
          year: item.year,
        }));
      const result = await deepResearchApi.createTaskFromSelection({
        name: taskName.trim(),
        description: `Created from research search for: ${query.trim()}`,
        template_id: templateId || undefined,
        model_name: modelName,
        custom_reading_prompts: normalizedCustomReadingPrompts.length > 0 ? normalizedCustomReadingPrompts : undefined,
        selected_papers: selectedPapers,
      });
      navigate(`/tasks/${result.task_id}`);
    } catch (error) {
      console.error('Failed to create task from selection:', error);
    } finally {
      setCreatingTask(false);
    }
  };

  const handleAutoCreateTask = async () => {
    if (!query.trim() || selectedTargetConferences.length === 0 || creatingTask) {
      return;
    }
    setCreatingTask(true);
    try {
      const result = await deepResearchApi.createTaskFromAutoResearch({
        query: query.trim(),
        name: taskName.trim() || `Deep Research: ${query.trim().slice(0, 40)}`,
        description: `Agent-selected from ${selectedTargetConferences.join(', ')} (${effectiveTargetYears.join(', ')})`,
        conferences: selectedTargetConferences,
        years: requestTargetYears,
        template_id: templateId || undefined,
        model_name: modelName,
        custom_reading_prompts: normalizedCustomReadingPrompts.length > 0 ? normalizedCustomReadingPrompts : undefined,
        max_search_rounds: normalizedMaxSearchRounds,
        max_queries_per_round: normalizedMaxQueriesPerRound,
        max_full_reads: normalizedMaxFullReads,
      });
      navigate(`/tasks/${result.task_id}`);
    } catch (error) {
      console.error('Failed to auto-create deep research task:', error);
    } finally {
      setCreatingTask(false);
    }
  };

  const handleInstallSelectedAssets = async () => {
    if (installingAssets || selectedAssets.size === 0) {
      return;
    }
    setInstallingAssets(true);
    setInstallMessage('');
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
      setInstallMessage(`Installed ${result.installed_count} pack(s).`);
    } catch (error) {
      console.error('Failed to install selected release assets:', error);
      setInstallMessage('Install failed.');
    } finally {
      setInstallingAssets(false);
    }
  };

  const handleInstallMatchingPackAssets = async () => {
    if (installingAssets || matchingReleaseAssets.length === 0) {
      return;
    }
    setInstallingAssets(true);
    setInstallMessage('');
    try {
      const result = await deepResearchApi.installReleaseAssets({
        assets: matchingReleaseAssets.map((asset) => ({
          release_tag: asset.releaseTag,
          asset_name: asset.assetName,
          download_url: asset.downloadUrl,
        })),
      });
      setInstallMessage(`Installed ${result.installed_count} matching pack(s).`);
      await fetchPacks();
    } catch (error) {
      console.error('Failed to install matching pack assets:', error);
      setInstallMessage('Install failed.');
    } finally {
      setInstallingAssets(false);
    }
  };

  const targetYearButtons = targetOptions ? (
    <div className="flex flex-wrap gap-2">
      {targetOptions.years.map((year) => {
        const selected = selectedTargetYears.includes(year);
        return (
          <button
            key={year}
            type="button"
            onClick={() => toggleTargetYear(year)}
            className={clsx(
              'px-3 py-2 rounded-lg border text-sm font-medium transition-colors',
              selected ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-gray-200 text-gray-600 hover:border-blue-300',
            )}
          >
            {year}
          </button>
        );
      })}
    </div>
  ) : (
    <div className="text-sm text-gray-500">Loading target years...</div>
  );

  const targetConferenceButtons = targetOptions ? (
    filteredTargetConferences.length === 0 ? (
      <div className="text-sm text-gray-500">No conferences have resources for the selected years.</div>
    ) : (
    <div className="space-y-3">
      {filteredTargetConferences.map((conference) => {
        const selected = selectedTargetConferences.includes(conference.code);
        return (
          <button
            key={conference.code}
            type="button"
            onClick={() => toggleTargetConference(conference.code)}
            className={`w-full border rounded-xl px-3 py-2.5 text-left transition-colors ${selected ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-blue-300'}`}
          >
            <div className="flex items-start gap-3">
              <div className="mt-0.5 text-blue-600">
                {selected ? <CheckSquare size={16} /> : <Square size={16} />}
              </div>
              <div>
                <div className="text-sm font-medium text-gray-900 leading-5">{conference.label}</div>
                <div className="text-xs text-gray-500 mt-0.5 leading-4">
                  {conference.years.map((item) => item.year).join(', ')} · {conference.total_paper_count} papers
                </div>
              </div>
            </div>
          </button>
        );
      })}
    </div>
    )
  ) : (
    <div className="text-sm text-gray-500">Loading target conferences...</div>
  );

  const packYearButtons = packTargetOptions ? (
    <div className="flex flex-wrap gap-2">
      {packTargetOptions.years.map((year) => {
        const selected = selectedPackYears.includes(year);
        return (
          <button
            key={year}
            type="button"
            onClick={() => togglePackYear(year)}
            className={clsx(
              'px-3 py-2 rounded-lg border text-sm font-medium transition-colors',
              selected ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-gray-200 text-gray-600 hover:border-blue-300',
            )}
          >
            {year}
          </button>
        );
      })}
    </div>
  ) : (
    <div className="text-sm text-gray-500">Loading pack years...</div>
  );

  const packConferenceButtons = packTargetOptions ? (
    filteredPackConferences.length === 0 ? (
      <div className="text-sm text-gray-500">No conferences have resources for the selected years.</div>
    ) : (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
      {filteredPackConferences.map((conference) => {
        const selected = selectedPackConferences.includes(conference.code);
        return (
          <button
            key={conference.code}
            type="button"
            onClick={() => togglePackConference(conference.code)}
            className={`w-full border rounded-lg px-2 py-1.5 text-left transition-colors ${selected ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-blue-300'}`}
          >
            <div className="flex items-start gap-1.5">
              <div className="mt-0.5 text-blue-600 shrink-0">
                {selected ? <CheckSquare size={14} /> : <Square size={14} />}
              </div>
              <div className="min-w-0">
                <div className="font-medium text-xs text-gray-900 leading-4">{conference.label}</div>
                <div className="text-[11px] text-gray-500 mt-0.5 truncate leading-4">
                  {conference.years.filter((year) => effectivePackYears.includes(year)).join(', ')}
                </div>
              </div>
            </div>
          </button>
        );
      })}
    </div>
    )
  ) : (
    <div className="text-sm text-gray-500">Loading pack conferences...</div>
  );

  return (
    <Layout>
      <div className="max-w-5xl mx-auto">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Create Research Task</h1>
          <p className="text-gray-500 mt-2">Research now uses one unified task flow. Search papers manually or let the system auto-select papers, then continue reading and reporting inside the task.</p>
        </div>

        <div className="flex rounded-xl bg-gray-100 p-1 mb-6 w-full max-w-sm">
          <button
            type="button"
            onClick={() => setWorkflow('research')}
            className={clsx('flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors', workflow === 'research' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600')}
          >
            Research
          </button>
          <button
            type="button"
            onClick={() => {
              setWorkflow('packs');
              fetchPacks();
              fetchPackJobs();
              if (releases.length === 0) {
                fetchReleases();
              }
            }}
            className={clsx('flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors', workflow === 'packs' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600')}
          >
            Packs
          </button>
        </div>

        {workflow === 'packs' ? (
          <div className="bg-white border border-gray-200 rounded-2xl p-6">
            <div className="grid grid-cols-1 xl:grid-cols-[0.95fr_1.05fr] gap-6">
              <div className="border border-gray-200 rounded-2xl p-5">
                <div className="flex items-center justify-between gap-4 mb-5">
                  <div>
                    <h2 className="text-xl font-semibold text-gray-900">Local Packs</h2>
                    <p className="text-sm text-gray-500 mt-1">One-click build from raw conference paperlists: normalize, create embeddings, then pack. After that, upload if you want to publish.</p>
                  </div>
                  <button
                    type="button"
                    onClick={fetchPacks}
                    disabled={loadingPacks}
                    className="flex items-center gap-2 px-3 py-2 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
                  >
                    {loadingPacks ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
                    Refresh
                  </button>
                </div>

                <div className="grid grid-cols-1 gap-3 mb-4">
                  <input
                    value={releaseOwner}
                    onChange={(event) => setReleaseOwner(event.target.value)}
                    placeholder="GitHub owner"
                    className="w-full px-3 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                  <input
                    value={releaseRepo}
                    onChange={(event) => setReleaseRepo(event.target.value)}
                    placeholder="GitHub repo"
                    className="w-full px-3 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                  <input
                    value={releaseTag}
                    onChange={(event) => setReleaseTag(event.target.value)}
                    placeholder="Release tag"
                    className="w-full px-3 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                </div>

                <div className="mb-5 border border-gray-200 rounded-2xl p-4 space-y-4">
                  <div>
                    <div className="flex items-center justify-between gap-4 mb-2">
                      <button
                        type="button"
                        onClick={() => setPackYearsExpanded((current) => !current)}
                        className="flex items-center gap-2 text-sm font-semibold text-gray-900"
                      >
                        {packYearsExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                        <span>Target Years</span>
                      </button>
                      <div className="flex items-center gap-3">
                        <button
                          type="button"
                          onClick={toggleAllPackYears}
                          disabled={!packTargetOptions || packTargetOptions.years.length === 0}
                          className="text-xs text-blue-600 hover:text-blue-700 disabled:opacity-50"
                        >
                          {allPackYearsSelected ? 'Clear all' : 'Select all'}
                        </button>
                        <span className="text-xs text-gray-500">
                          {selectedPackYears.length > 0 ? effectivePackYears.join(', ') : `Default: ${effectivePackYears.join(', ')}`}
                        </span>
                      </div>
                    </div>
                    {packYearsExpanded && packYearButtons}
                  </div>
                  <div>
                    <div className="flex items-center justify-between gap-4 mb-2">
                      <button
                        type="button"
                        onClick={() => setPackConferencesExpanded((current) => !current)}
                        className="flex items-center gap-2 text-sm font-semibold text-gray-900"
                      >
                        {packConferencesExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                        <span>Target Conferences</span>
                      </button>
                      <div className="flex items-center gap-3">
                        <button
                          type="button"
                          onClick={toggleAllVisiblePackConferences}
                          disabled={filteredPackConferences.length === 0}
                          className="text-xs text-blue-600 hover:text-blue-700 disabled:opacity-50"
                        >
                          {allVisiblePackConferencesSelected ? 'Clear all' : 'Select all'}
                        </button>
                        <span className="text-xs text-gray-500">{selectedPackConferences.length} selected</span>
                      </div>
                    </div>
                    {packConferencesExpanded && (
                      <div className="max-h-80 overflow-y-auto pr-1">
                        {packConferenceButtons}
                      </div>
                    )}
                  </div>
                </div>

                <div className="mb-5 border border-gray-200 rounded-2xl p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h3 className="text-sm font-semibold text-gray-900">Release Availability</h3>
                      <div className="text-sm text-gray-500 mt-1">
                        {matchingReleaseAssets.length} / {selectedPackTargets.length} selected pack targets are already available in GitHub releases.
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={handleInstallMatchingPackAssets}
                      disabled={installingAssets || matchingReleaseAssets.length === 0}
                      className="shrink-0 flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
                    >
                      {installingAssets ? <Loader2 size={18} className="animate-spin" /> : <Download size={18} />}
                      Download Matching
                    </button>
                  </div>
                  {matchingReleaseAssets.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {matchingReleaseAssets.map((asset) => (
                        <span
                          key={`${asset.releaseTag}:${asset.assetName}`}
                          className="px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-medium"
                        >
                          {asset.conference.toUpperCase()} {asset.year} · {asset.releaseTag}
                        </span>
                      ))}
                    </div>
                  )}
                  {missingReleaseTargets.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {missingReleaseTargets.map((item) => (
                        <span
                          key={item.key}
                          className="px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 text-xs font-medium"
                        >
                          {item.conference.toUpperCase()} {item.year} · not in release
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <button
                  type="button"
                  onClick={handleBuildPacks}
                  disabled={buildingPacks || selectedPackConferences.length === 0}
                  className="w-full mb-4 flex items-center justify-center gap-2 px-4 py-3 bg-slate-900 text-white rounded-xl hover:bg-slate-800 transition-colors disabled:opacity-50"
                >
                  {buildingPacks ? <Loader2 size={18} className="animate-spin" /> : <FolderPlus size={18} />}
                  One-click Build Selected Packs
                </button>

                {packMessage && <div className="mb-4 text-sm text-gray-700 bg-gray-50 border border-gray-200 rounded-xl px-4 py-3">{packMessage}</div>}

                <div className="mb-5 border border-gray-200 rounded-2xl p-4">
                  <div className="flex items-center justify-between gap-4 mb-3">
                    <h3 className="text-sm font-semibold text-gray-900">Build Jobs</h3>
                    <button
                      type="button"
                      onClick={fetchPackJobs}
                      disabled={loadingPackJobs}
                      className="text-sm text-blue-600 hover:text-blue-700 disabled:opacity-50"
                    >
                      {loadingPackJobs ? 'Refreshing...' : 'Refresh'}
                    </button>
                  </div>
                  {packJobs.length === 0 ? (
                    <div className="text-sm text-gray-500">No pack build jobs yet.</div>
                  ) : (
                    <div className="space-y-3">
                      {packJobs.map((job) => (
                        <div key={job.id} className="border border-gray-200 rounded-xl p-3">
                          <div className="flex items-start justify-between gap-4">
                            <div className="min-w-0">
                              <div className="font-medium text-gray-900">
                                {job.total_targets} target(s) · {job.version}
                              </div>
                              <div className="text-sm text-gray-500 mt-1">
                                {job.completed_targets}/{job.total_targets} completed
                                {job.current_conference && job.current_year ? ` · ${job.current_conference.toUpperCase()} ${job.current_year}` : ''}
                                {job.current_stage ? ` · ${job.current_stage}` : ''}
                              </div>
                            </div>
                            <div className="shrink-0 flex items-center gap-2">
                              <span className={clsx(
                                'px-2 py-1 rounded-full text-xs font-medium',
                                job.status === 'completed' && 'bg-emerald-50 text-emerald-700',
                                job.status === 'running' && 'bg-blue-50 text-blue-700',
                                job.status === 'queued' && 'bg-amber-50 text-amber-700',
                                job.status === 'failed' && 'bg-red-50 text-red-700',
                              )}>
                                {job.status}
                              </span>
                              {job.can_resume && (
                                <button
                                  type="button"
                                  onClick={() => handleResumePackJob(job.id)}
                                  className="px-3 py-1.5 rounded-lg bg-slate-900 text-white text-sm hover:bg-slate-800"
                                >
                                  Resume
                                </button>
                              )}
                            </div>
                          </div>
                          <div className="mt-3 h-2 rounded-full bg-gray-100 overflow-hidden">
                            <div
                              className={clsx(
                                'h-full transition-all',
                                job.status === 'failed' ? 'bg-red-500' : 'bg-blue-600',
                              )}
                              style={{ width: `${job.progress_percent}%` }}
                            />
                          </div>
                          <div className="mt-2 text-xs text-gray-600">
                            {job.progress_message || 'Waiting to start.'}
                          </div>
                          {job.error && (
                            <div className="mt-2 text-xs text-red-600">
                              {job.error}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {loadingPacks ? (
                  <div className="text-sm text-gray-500">Loading local packs...</div>
                ) : packs.length === 0 ? (
                  <div className="text-sm text-gray-500">No local packs yet.</div>
                ) : (
                  <div className="space-y-3">
                    {packs.map((pack) => {
                      const key = `${pack.conference}-${pack.year}-${pack.version}`;
                      return (
                        <div key={key} className="border border-gray-200 rounded-xl px-4 py-3 flex items-center justify-between gap-4">
                          <div className="min-w-0">
                            <div className="font-medium text-gray-900">{pack.pack_name}</div>
                            <div className="text-sm text-gray-500 mt-1">
                              {pack.conference.toUpperCase()} {pack.year} · {(pack.pack_size_bytes / (1024 * 1024)).toFixed(1)} MB
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => handleUploadPack(pack)}
                            disabled={uploadingPackKey !== '' || !releaseOwner.trim() || !releaseRepo.trim() || !releaseTag.trim()}
                            className="shrink-0 flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
                          >
                            {uploadingPackKey === key ? <Loader2 size={18} className="animate-spin" /> : <Upload size={18} />}
                            Upload
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="border border-gray-200 rounded-2xl p-5">
                <div className="flex items-center justify-between gap-4 mb-6">
                  <div>
                    <h2 className="text-xl font-semibold text-gray-900">GitHub Releases</h2>
                    <p className="text-sm text-gray-500 mt-1">Refresh the latest release assets, select the packs you want, then download and install them locally.</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={fetchReleases}
                      disabled={loadingReleases}
                      className="flex items-center gap-2 px-4 py-2 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
                    >
                      {loadingReleases ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
                      Refresh
                    </button>
                    <button
                      type="button"
                      onClick={handleInstallSelectedAssets}
                      disabled={installingAssets || selectedAssets.size === 0}
                      className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
                    >
                      {installingAssets ? <Loader2 size={18} className="animate-spin" /> : <Download size={18} />}
                      Download Selected
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between mb-4 text-sm text-gray-600">
                  <button
                    type="button"
                    onClick={handleToggleAllAssets}
                    disabled={totalReleaseAssets === 0}
                    className="flex items-center gap-2 hover:text-blue-700 transition-colors"
                  >
                    {selectedAssets.size === totalReleaseAssets && totalReleaseAssets > 0 ? <CheckSquare size={18} /> : <Square size={18} />}
                    Select all assets
                  </button>
                  <span>{selectedAssets.size} selected / {totalReleaseAssets} assets</span>
                </div>

                {installMessage && <div className="mb-4 text-sm text-green-700">{installMessage}</div>}

                {loadingReleases ? (
                  <div className="text-sm text-gray-500">Loading releases...</div>
                ) : releases.length === 0 ? (
                  <div className="text-sm text-gray-500">No releases found yet.</div>
                ) : (
                  <div className="space-y-4">
                    {releases.map((release) => (
                      <div key={release.id} className="border border-gray-200 rounded-2xl p-5">
                        <div className="flex items-start justify-between gap-4 mb-4">
                          <div>
                            <h3 className="font-semibold text-gray-900">{release.name}</h3>
                            <div className="text-sm text-gray-500 mt-1">
                              {release.tag_name}
                              {release.published_at ? ` · ${new Date(release.published_at).toLocaleString()}` : ''}
                            </div>
                          </div>
                          <a href={release.html_url} target="_blank" rel="noreferrer" className="text-sm text-blue-600 hover:text-blue-700">
                            View release
                          </a>
                        </div>

                        {release.assets.length === 0 ? (
                          <div className="text-sm text-gray-500">No zip assets in this release.</div>
                        ) : (
                          <div className="space-y-3">
                            {release.assets.map((asset) => {
                              const selected = selectedAssets.has(assetKey(release.tag_name, asset.name));
                              return (
                                <button
                                  key={asset.id}
                                  type="button"
                                  onClick={() => toggleAsset(release.tag_name, asset.name)}
                                  className={`w-full text-left border rounded-xl px-4 py-3 transition-colors ${selected ? 'border-blue-400 bg-blue-50/50' : 'border-gray-200 hover:border-blue-300'}`}
                                >
                                  <div className="flex items-start gap-3">
                                    <div className="mt-1 text-blue-600 shrink-0">
                                      {selected ? <CheckSquare size={18} /> : <Square size={18} />}
                                    </div>
                                    <div className="min-w-0">
                                      <div className="font-medium text-gray-900">{asset.name}</div>
                                      <div className="text-sm text-gray-500 mt-1">
                                        {(asset.size / (1024 * 1024)).toFixed(1)} MB · {asset.download_count} downloads
                                      </div>
                                    </div>
                                  </div>
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_0.9fr] gap-6">
              <div className="bg-white border border-gray-200 rounded-2xl p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">Research Question</h2>
                <textarea
                  name="research-query"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  rows={6}
                  placeholder="请你帮我看一下，有没有什么关于大语言模型安全的新课题可以做的。"
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
                />

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Template</label>
                    <select
                      value={templateId}
                      onChange={(event) => handleTemplateChange(event.target.value)}
                      className="w-full px-3 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    >
                      <option value="">Default template</option>
                      {templates.map((template) => (
                        <option key={template.id} value={template.id}>{template.name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Model</label>
                    <select
                      value={modelName}
                      onChange={(event) => setModelName(event.target.value)}
                      className="w-full px-3 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    >
                      <option value="gemini-3-flash-preview">Gemini 3 Flash (Faster/Cheaper)</option>
                      <option value="gemini-3-pro-preview">Gemini 3 Pro (Stronger)</option>
                    </select>
                  </div>
                </div>

                <div className="mt-6 border-t border-gray-100 pt-6">
                  <label className="block text-sm font-medium text-gray-700 mb-2">Task Name</label>
                  <input
                    value={taskName}
                    onChange={(event) => setTaskName(event.target.value)}
                    className="w-full px-3 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                </div>

                <div className="mt-6 border-t border-gray-100 pt-6">
                  <PromptListEditor
                    title="Reading Prompts"
                    description="These prompts will be stored on the task and used for paper interpretation. They override the selected template content for this task."
                    prompts={customReadingPrompts}
                    onChange={setCustomReadingPrompts}
                  />
                </div>
              </div>

              <div className="bg-white border border-gray-200 rounded-2xl p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold text-gray-900">Target Scope</h2>
                  <span className="text-sm text-gray-500">{selectedTargetConferences.length} conferences</span>
                </div>

                {loading ? (
                  <div className="text-sm text-gray-500">Loading scope...</div>
                ) : (
                  <div className="space-y-5">
                    <div>
                      <div className="flex items-center justify-between gap-4 mb-2">
                        <button
                          type="button"
                          onClick={() => setResearchYearsExpanded((current) => !current)}
                          className="flex items-center gap-2 text-sm font-semibold text-gray-900"
                        >
                          {researchYearsExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                          <span>Target Years</span>
                        </button>
                        <div className="flex items-center gap-3">
                          <button
                            type="button"
                            onClick={toggleAllTargetYears}
                            disabled={!targetOptions || targetOptions.years.length === 0}
                            className="text-xs text-blue-600 hover:text-blue-700 disabled:opacity-50"
                          >
                            {allTargetYearsSelected ? 'Clear all' : 'Select all'}
                          </button>
                          <span className="text-xs text-gray-500">
                            {selectedTargetYears.length > 0 ? effectiveTargetYears.join(', ') : `Default: ${effectiveTargetYears.join(', ')}`}
                          </span>
                        </div>
                      </div>
                      {researchYearsExpanded && targetYearButtons}
                      <div className="text-xs text-gray-500 mt-2">Clear all years to use the backend default: recent 3 available years.</div>
                    </div>
                    <div>
                      <div className="flex items-center justify-between gap-4 mb-2">
                        <button
                          type="button"
                          onClick={() => setResearchConferencesExpanded((current) => !current)}
                          className="flex items-center gap-2 text-sm font-semibold text-gray-900"
                        >
                          {researchConferencesExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                          <span>Target Conferences</span>
                        </button>
                        <div className="flex items-center gap-3">
                          <button
                            type="button"
                            onClick={toggleAllVisibleTargetConferences}
                            disabled={filteredTargetConferences.length === 0}
                            className="text-xs text-blue-600 hover:text-blue-700 disabled:opacity-50"
                          >
                            {allVisibleTargetConferencesSelected ? 'Clear all' : 'Select all'}
                          </button>
                          <span className="text-xs text-gray-500">{selectedTargetConferences.length} selected</span>
                        </div>
                      </div>
                      {researchConferencesExpanded && (
                        <div className="max-h-[28rem] overflow-y-auto pr-1">
                          {targetConferenceButtons}
                        </div>
                      )}
                    </div>
                    <div className="border border-gray-200 rounded-2xl p-4 space-y-4">
                      <div>
                        <h3 className="text-sm font-semibold text-gray-900 mb-3">Search Budget</h3>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          <label className="text-sm text-gray-700">
                            <span className="block mb-1">Top K Per Asset</span>
                            <input
                              type="number"
                              min={1}
                              value={searchTopKPerAsset}
                              onChange={(event) => setSearchTopKPerAsset(Number(event.target.value) || 1)}
                              className="w-full px-3 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            />
                          </label>
                          <label className="text-sm text-gray-700">
                            <span className="block mb-1">Top K Global</span>
                            <input
                              type="number"
                              min={1}
                              value={searchTopKGlobal}
                              onChange={(event) => setSearchTopKGlobal(Number(event.target.value) || 1)}
                              className="w-full px-3 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            />
                          </label>
                        </div>
                      </div>
                      <div>
                        <h3 className="text-sm font-semibold text-gray-900 mb-3">Agent Budget</h3>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          <label className="text-sm text-gray-700">
                            <span className="block mb-1">Max Search Rounds</span>
                            <input
                              type="number"
                              min={1}
                              max={20}
                              value={maxSearchRounds}
                              onChange={(event) => setMaxSearchRounds(Number(event.target.value) || 1)}
                              className="w-full px-3 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            />
                          </label>
                          <label className="text-sm text-gray-700">
                            <span className="block mb-1">Max Queries / Round</span>
                            <input
                              type="number"
                              min={1}
                              max={10}
                              value={maxQueriesPerRound}
                              onChange={(event) => setMaxQueriesPerRound(Number(event.target.value) || 1)}
                              className="w-full px-3 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            />
                          </label>
                          <label className="text-sm text-gray-700">
                            <span className="block mb-1">Max Full Reads</span>
                            <input
                              type="number"
                              min={1}
                              value={maxFullReads}
                              onChange={(event) => setMaxFullReads(Number(event.target.value) || 1)}
                              className="w-full px-3 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            />
                          </label>
                        </div>
                        <div className="text-xs text-gray-500 mt-2">
                          The bounded agent can search for up to {normalizedMaxSearchRounds} rounds, propose up to {normalizedMaxQueriesPerRound} queries per round, then import at most {normalizedMaxFullReads} papers into the task for full reading.
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                <div className="mt-6 p-4 bg-gray-50 rounded-xl">
                  <div className="text-sm font-medium text-gray-900">Current Slice</div>
                  <div className="text-sm text-gray-600 mt-1">{totalTargetPapers} papers across {selectedTargetConferences.length} conferences · years {effectiveTargetYears.join(', ')}</div>
                </div>

                <div className="space-y-3 mt-6">
                  <button
                    onClick={handleSearch}
                    disabled={searching || !query.trim() || selectedTargetConferences.length === 0}
                    className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white px-4 py-3 rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-50"
                  >
                    {searching ? <Loader2 size={18} className="animate-spin" /> : <Search size={18} />}
                    Search Papers
                  </button>
                  <button
                    onClick={handleAutoCreateTask}
                    disabled={creatingTask || !query.trim() || selectedTargetConferences.length === 0}
                    className="w-full flex items-center justify-center gap-2 bg-slate-900 text-white px-4 py-3 rounded-xl hover:bg-slate-800 transition-colors disabled:opacity-50"
                  >
                    {creatingTask ? <Loader2 size={18} className="animate-spin" /> : <Sparkles size={18} />}
                    Agent-select to Task
                  </button>
                </div>
              </div>
            </div>

            {workflow === 'research' && (
              <div className="mt-6 bg-white border border-gray-200 rounded-2xl p-6">
                <div className="flex items-center justify-between gap-4 mb-4">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900">Search Results</h2>
                    <p className="text-sm text-gray-500 mt-1">Pick the papers you want, then create a task and let the existing reading pipeline process them.</p>
                  </div>
                  <button
                    onClick={handleCreateTaskFromSelection}
                    disabled={creatingTask || selectedHits.size === 0 || !taskName.trim()}
                    className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors disabled:opacity-50"
                  >
                    {creatingTask ? <Loader2 size={18} className="animate-spin" /> : <FolderPlus size={18} />}
                    Create Task from Selection
                  </button>
                </div>
                {hits.length === 0 ? (
                  <div className="text-sm text-gray-500">No search results yet.</div>
                ) : (
                  <div className="space-y-4">
                    {hits.map((hit) => {
                      const selected = selectedHits.has(hit.paper_id);
                      return (
                        <button
                          key={`${hit.conference}-${hit.year}-${hit.paper_id}`}
                          type="button"
                          onClick={() => toggleHit(hit.paper_id)}
                          className={`w-full text-left border rounded-2xl p-5 transition-colors ${selected ? 'border-blue-400 bg-blue-50/50' : 'border-gray-200 hover:border-blue-300'}`}
                        >
                          <div className="flex items-start gap-3">
                            <div className="mt-1 text-blue-600 shrink-0">
                              {selected ? <CheckSquare size={18} /> : <Square size={18} />}
                            </div>
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2 mb-2">
                                <h3 className="font-semibold text-gray-900">{hit.title}</h3>
                                <span className="px-2 py-0.5 rounded-full bg-white border border-gray-200 text-xs text-gray-600">
                                  {hit.conference.toUpperCase()} {hit.year}
                                </span>
                                <span className="text-xs font-medium text-blue-700">Score {hit.coarse_score.toFixed(3)}</span>
                              </div>
                              <p className="text-sm text-gray-600 leading-6">{hit.abstract}</p>
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </Layout>
  );
};

export default ResearchCreatePage;
