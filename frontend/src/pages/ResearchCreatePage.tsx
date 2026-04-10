import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Search, CheckSquare, Square, FolderPlus, Sparkles } from 'lucide-react';
import Layout from '../components/Layout';
import { deepResearchApi, researchApi, templatesApi } from '../api/services';
import { ConferenceSearchHit, ConferenceSource, Template } from '../types';
import clsx from 'clsx';

const ResearchCreatePage: React.FC = () => {
  const navigate = useNavigate();
  const [conferences, setConferences] = useState<ConferenceSource[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedCodes, setSelectedCodes] = useState<string[]>([]);
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState('quick');
  const [modelName, setModelName] = useState('gemini-3-flash-preview');
  const [workflow, setWorkflow] = useState<'job' | 'search'>('search');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<ConferenceSearchHit[]>([]);
  const [selectedHits, setSelectedHits] = useState<Set<string>>(new Set());
  const [taskName, setTaskName] = useState('Conference Search Task');
  const [templateId, setTemplateId] = useState('');
  const [creatingTask, setCreatingTask] = useState(false);

  useEffect(() => {
    const fetchConferences = async () => {
      try {
        const [conferenceData, templateData] = await Promise.all([
          researchApi.listConferences(),
          templatesApi.list(),
        ]);
        setConferences(conferenceData);
        setTemplates(templateData);
        const defaultTemplate = templateData.find((item) => item.is_default) || templateData[0];
        setTemplateId(defaultTemplate?.id || '');
        setConferences(conferenceData);
        setSelectedCodes(conferenceData.slice(0, 2).map((item) => item.code));
      } catch (error) {
        console.error('Failed to fetch conferences:', error);
      } finally {
        setLoading(false);
      }
    };
    fetchConferences();
  }, []);

  const totalPapers = useMemo(
    () => conferences.filter((conference) => selectedCodes.includes(conference.code)).reduce((sum, conference) => sum + conference.paper_count, 0),
    [conferences, selectedCodes],
  );

  const toggleConference = (code: string) => {
    setSelectedCodes((current) => current.includes(code) ? current.filter((item) => item !== code) : [...current, code]);
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

  const handleSubmit = async () => {
    if (!query.trim() || selectedCodes.length === 0 || submitting) {
      return;
    }

    setSubmitting(true);
    try {
      const job = await researchApi.createJob({
        query: query.trim(),
        conference_codes: selectedCodes,
        mode,
        model_name: modelName,
      });
      navigate(`/research/${job.id}`);
    } catch (error) {
      console.error('Failed to create research job:', error);
      setSubmitting(false);
    }
  };

  const handleSearch = async () => {
    if (!query.trim() || selectedCodes.length === 0 || searching) {
      return;
    }
    setSearching(true);
    try {
      const response = await deepResearchApi.search({
        query: query.trim(),
        conferences: selectedCodes,
        top_k_per_asset: 8,
        top_k_global: 24,
      });
      setHits(response.results);
      setSelectedHits(new Set(response.results.slice(0, 6).map((item) => item.paper_id)));
      if (!taskName.trim()) {
        setTaskName(`Search: ${query.trim().slice(0, 40)}`);
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
        description: `Created from conference search for: ${query.trim()}`,
        template_id: templateId || undefined,
        model_name: modelName,
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
    if (!query.trim() || selectedCodes.length === 0 || creatingTask) {
      return;
    }
    setCreatingTask(true);
    try {
      const result = await deepResearchApi.createTaskFromAutoResearch({
        query: query.trim(),
        name: `Deep Research: ${query.trim().slice(0, 40)}`,
        description: `Auto-selected from ${selectedCodes.join(', ')}`,
        conferences: selectedCodes,
        template_id: templateId || undefined,
        model_name: modelName,
        rerank_score_threshold: 0.5,
        min_papers: 5,
        max_papers: 12,
      });
      navigate(`/tasks/${result.task_id}`);
    } catch (error) {
      console.error('Failed to auto-create deep research task:', error);
    } finally {
      setCreatingTask(false);
    }
  };

  return (
    <Layout>
      <div className="max-w-5xl mx-auto">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Create Deep Research Job</h1>
          <p className="text-gray-500 mt-2">You can still launch the old research job flow, but the primary path now is conference search to task, or auto-select to task.</p>
        </div>

        <div className="flex rounded-xl bg-gray-100 p-1 mb-6 w-full max-w-md">
          <button
            type="button"
            onClick={() => setWorkflow('search')}
            className={clsx('flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors', workflow === 'search' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600')}
          >
            Search to Task
          </button>
          <button
            type="button"
            onClick={() => setWorkflow('job')}
            className={clsx('flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors', workflow === 'job' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600')}
          >
            Legacy Job
          </button>
        </div>

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
                <label className="block text-sm font-medium text-gray-700 mb-2">Mode</label>
                <select
                  name="research-mode"
                  value={mode}
                  onChange={(event) => setMode(event.target.value)}
                  className="w-full px-3 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="quick">Quick Scan</option>
                  <option value="deep">Deep Research</option>
                </select>
              </div>
              <div>
                {workflow === 'search' ? (
                  <>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Template</label>
                    <select
                      value={templateId}
                      onChange={(event) => setTemplateId(event.target.value)}
                      className="w-full px-3 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    >
                      <option value="">Default template</option>
                      {templates.map((template) => (
                        <option key={template.id} value={template.id}>{template.name}</option>
                      ))}
                    </select>
                  </>
                ) : (
                  <>
                <label className="block text-sm font-medium text-gray-700 mb-2">Model</label>
                <input
                  name="research-model"
                  value={modelName}
                  onChange={(event) => setModelName(event.target.value)}
                  className="w-full px-3 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
                  </>
                )}
              </div>
            </div>

            {workflow === 'search' && (
              <div className="mt-6 border-t border-gray-100 pt-6">
                <label className="block text-sm font-medium text-gray-700 mb-2">Task Name</label>
                <input
                  value={taskName}
                  onChange={(event) => setTaskName(event.target.value)}
                  className="w-full px-3 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
            )}
          </div>

          <div className="bg-white border border-gray-200 rounded-2xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">Conference Scope</h2>
              <span className="text-sm text-gray-500">{selectedCodes.length} selected</span>
            </div>

            {loading ? (
              <div className="text-sm text-gray-500">Loading conferences...</div>
            ) : (
              <div className="space-y-3">
                {conferences.map((conference) => {
                  const selected = selectedCodes.includes(conference.code);
                  return (
                    <button
                      key={conference.id}
                      type="button"
                      onClick={() => toggleConference(conference.code)}
                      className={`w-full border rounded-xl px-4 py-3 text-left transition-colors ${selected ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-blue-300'}`}
                    >
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5 text-blue-600">
                          {selected ? <CheckSquare size={18} /> : <Square size={18} />}
                        </div>
                        <div>
                          <div className="font-medium text-gray-900">{conference.name}</div>
                          <div className="text-sm text-gray-500 mt-1">{conference.paper_count} indexed papers</div>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}

            <div className="mt-6 p-4 bg-gray-50 rounded-xl">
              <div className="text-sm font-medium text-gray-900">Current Slice</div>
              <div className="text-sm text-gray-600 mt-1">{totalPapers} papers across {selectedCodes.length} conferences</div>
            </div>

            {workflow === 'job' ? (
              <button
                onClick={handleSubmit}
                disabled={submitting || !query.trim() || selectedCodes.length === 0}
                className="w-full mt-6 flex items-center justify-center gap-2 bg-blue-600 text-white px-4 py-3 rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-50"
              >
                {submitting ? <Loader2 size={18} className="animate-spin" /> : <Search size={18} />}
                Launch Research Job
              </button>
            ) : (
              <div className="space-y-3 mt-6">
                <button
                  onClick={handleSearch}
                  disabled={searching || !query.trim() || selectedCodes.length === 0}
                  className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white px-4 py-3 rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-50"
                >
                  {searching ? <Loader2 size={18} className="animate-spin" /> : <Search size={18} />}
                  Search Papers
                </button>
                <button
                  onClick={handleAutoCreateTask}
                  disabled={creatingTask || !query.trim() || selectedCodes.length === 0}
                  className="w-full flex items-center justify-center gap-2 bg-slate-900 text-white px-4 py-3 rounded-xl hover:bg-slate-800 transition-colors disabled:opacity-50"
                >
                  {creatingTask ? <Loader2 size={18} className="animate-spin" /> : <Sparkles size={18} />}
                  Auto-select to Task
                </button>
              </div>
            )}
          </div>
        </div>

        {workflow === 'search' && (
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
      </div>
    </Layout>
  );
};

export default ResearchCreatePage;
