import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowRight, CheckSquare, FolderPlus, Loader2, RefreshCw, Square } from 'lucide-react';
import Layout from '../components/Layout';
import { researchApi, tasksApi } from '../api/services';
import { ResearchCandidate, ResearchJob, Task } from '../types';
import clsx from 'clsx';

const statusStyles: Record<string, string> = {
  created: 'bg-gray-100 text-gray-700',
  running: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
};

const ResearchDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [candidates, setCandidates] = useState<ResearchCandidate[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<Set<string>>(new Set());
  const [targetMode, setTargetMode] = useState<'existing' | 'new'>('new');
  const [targetTaskId, setTargetTaskId] = useState('');
  const [newTaskName, setNewTaskName] = useState('');
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState('');

  const fetchData = useCallback(async () => {
    if (!id) {
      return;
    }
    try {
      const [jobData, candidateData, taskData] = await Promise.all([
        researchApi.getJob(id),
        researchApi.getCandidates(id),
        tasksApi.list(),
      ]);

      setJob(jobData);
      setCandidates(candidateData);
      setTasks(taskData);
      setTargetTaskId((current) => current || taskData[0]?.id || '');
      setNewTaskName((current) => current || `Research: ${jobData.query.slice(0, 40)}`);
      setSelectedCandidateIds((current) => {
        if (current.size > 0) {
          const validIds = candidateData.map((candidate) => candidate.id);
          const next = new Set(Array.from(current).filter((candidateId) => validIds.includes(candidateId)));
          if (next.size > 0) {
            return next;
          }
        }
        return new Set(candidateData.filter((candidate) => candidate.is_selected).map((candidate) => candidate.id));
      });
    } catch (error) {
      console.error('Failed to fetch research job details:', error);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (!job || job.status === 'completed' || job.status === 'failed') {
      return;
    }
    const interval = setInterval(fetchData, 2500);
    return () => clearInterval(interval);
  }, [fetchData, job]);

  const toggleCandidate = (candidateId: string) => {
    setSelectedCandidateIds((current) => {
      const next = new Set(current);
      if (next.has(candidateId)) {
        next.delete(candidateId);
      } else {
        next.add(candidateId);
      }
      return next;
    });
  };

  const selectedCandidates = useMemo(
    () => candidates.filter((candidate) => selectedCandidateIds.has(candidate.id)),
    [candidates, selectedCandidateIds],
  );

  const handleImport = async () => {
    if (!id || selectedCandidateIds.size === 0 || importing) {
      return;
    }
    setImporting(true);
    setImportResult('');
    try {
      const result = await researchApi.importToTask(id, {
        task_id: targetMode === 'existing' ? targetTaskId : undefined,
        new_task_name: targetMode === 'new' ? newTaskName.trim() : undefined,
        candidate_ids: Array.from(selectedCandidateIds),
      });
      setImportResult(`Imported ${result.imported_count} papers into ${result.task_name}.`);
      navigate(`/tasks/${result.task_id}`);
    } catch (error) {
      console.error('Failed to import candidates:', error);
      setImporting(false);
    }
  };

  if (loading || !job) {
    return <Layout><div className="text-gray-500">Loading research job...</div></Layout>;
  }

  return (
    <Layout>
      <div className="space-y-6">
        <div className="bg-white border border-gray-200 rounded-2xl p-6">
          <div className="flex items-start justify-between gap-6">
            <div className="min-w-0">
              <div className="flex items-center gap-3 mb-3">
                <span className={clsx('px-2.5 py-1 rounded-full text-xs font-medium capitalize', statusStyles[job.status] || 'bg-gray-100 text-gray-700')}>
                  {job.status}
                </span>
                <span className="text-sm text-gray-400 capitalize">{job.stage.replace(/_/g, ' ')}</span>
              </div>
              <h1 className="text-2xl font-bold text-gray-900">{job.query}</h1>
              <p className="text-sm text-gray-500 mt-3">Conferences: {job.selected_conferences.join(', ')}</p>
            </div>
            <button
              onClick={fetchData}
              className="flex items-center gap-2 px-3 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50"
            >
              <RefreshCw size={16} />
              Refresh
            </button>
          </div>

          <div className="mt-6">
            <div className="flex justify-between text-sm text-gray-600 mb-2">
              <span>Progress</span>
              <span>{job.progress}%</span>
            </div>
            <div className="w-full h-3 bg-gray-100 rounded-full overflow-hidden">
              <div className="h-full bg-blue-600 rounded-full transition-all" style={{ width: `${job.progress}%` }} />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1.25fr_0.95fr] gap-6">
          <div className="space-y-6">
            <div className="bg-white border border-gray-200 rounded-2xl p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Summary</h2>
              <p className="text-gray-700 leading-7">{job.summary || 'The research job is still building its synthesis.'}</p>
              {job.error_message && <p className="text-red-500 mt-4 text-sm">{job.error_message}</p>}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-white border border-gray-200 rounded-2xl p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">Themes</h2>
                <div className="flex flex-wrap gap-2">
                  {job.themes.length === 0 ? (
                    <span className="text-sm text-gray-500">No themes yet.</span>
                  ) : (
                    job.themes.map((theme) => (
                      <span key={theme} className="px-3 py-1 rounded-full bg-blue-50 text-blue-700 text-sm font-medium">
                        {theme}
                      </span>
                    ))
                  )}
                </div>
              </div>

              <div className="bg-white border border-gray-200 rounded-2xl p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">Opportunities</h2>
                <div className="space-y-3">
                  {job.opportunities.length === 0 ? (
                    <div className="text-sm text-gray-500">No opportunities generated yet.</div>
                  ) : (
                    job.opportunities.map((opportunity) => (
                      <div key={opportunity} className="text-sm text-gray-700 leading-6 bg-gray-50 rounded-xl px-4 py-3">
                        {opportunity}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>

            <div className="bg-white border border-gray-200 rounded-2xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-gray-900">Candidates</h2>
                <div className="text-sm text-gray-500">{selectedCandidates.length} selected / {candidates.length} total</div>
              </div>

              <div className="space-y-4">
                {candidates.length === 0 ? (
                  <div className="text-sm text-gray-500">No candidates yet. Wait for the job to finish screening the conference slice.</div>
                ) : (
                  candidates.map((candidate) => {
                    const selected = selectedCandidateIds.has(candidate.id);
                    return (
                      <button
                        key={candidate.id}
                        type="button"
                        onClick={() => toggleCandidate(candidate.id)}
                        className={`w-full text-left border rounded-2xl p-5 transition-colors ${selected ? 'border-blue-400 bg-blue-50/50' : 'border-gray-200 hover:border-blue-300'}`}
                      >
                        <div className="flex items-start gap-3">
                          <div className="mt-1 text-blue-600 shrink-0">
                            {selected ? <CheckSquare size={18} /> : <Square size={18} />}
                          </div>
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2 mb-2">
                              <h3 className="font-semibold text-gray-900">{candidate.title}</h3>
                              <span className="px-2 py-0.5 rounded-full bg-white border border-gray-200 text-xs text-gray-600">{candidate.conference_label}</span>
                              <span className="text-xs font-medium text-blue-700">Score {candidate.relevance_score.toFixed(1)}</span>
                            </div>
                            <p className="text-sm text-gray-600 leading-6">{candidate.abstract}</p>
                            {candidate.reason && <p className="text-sm text-gray-700 mt-3">{candidate.reason}</p>}
                          </div>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <div className="bg-white border border-gray-200 rounded-2xl p-6 sticky top-8">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Import to Reading Task</h2>
              <div className="flex rounded-xl bg-gray-100 p-1 mb-4">
                <button
                  type="button"
                  onClick={() => setTargetMode('new')}
                  className={clsx('flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors', targetMode === 'new' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600')}
                >
                  New Task
                </button>
                <button
                  type="button"
                  onClick={() => setTargetMode('existing')}
                  className={clsx('flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors', targetMode === 'existing' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600')}
                >
                  Existing Task
                </button>
              </div>

              {targetMode === 'new' ? (
                <input
                  name="research-new-task-name"
                  value={newTaskName}
                  onChange={(event) => setNewTaskName(event.target.value)}
                  placeholder="New task name"
                  className="w-full px-3 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              ) : (
                <select
                  name="research-target-task"
                  value={targetTaskId}
                  onChange={(event) => setTargetTaskId(event.target.value)}
                  className="w-full px-3 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  {tasks.map((task) => (
                    <option key={task.id} value={task.id}>{task.name}</option>
                  ))}
                </select>
              )}

              <div className="mt-4 space-y-3">
                <div className="flex items-center justify-between text-sm text-gray-600">
                  <span>Selected papers</span>
                  <span>{selectedCandidateIds.size}</span>
                </div>
                <div className="text-sm text-gray-500 leading-6">
                  Imported papers will enter the existing task pipeline, so the backend can search arXiv, download PDFs, and process them with the current reader stack.
                </div>
              </div>

              <button
                onClick={handleImport}
                disabled={importing || selectedCandidateIds.size === 0 || (targetMode === 'existing' && !targetTaskId) || (targetMode === 'new' && !newTaskName.trim())}
                className="w-full mt-6 flex items-center justify-center gap-2 bg-blue-600 text-white px-4 py-3 rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-50"
              >
                {importing ? <Loader2 size={18} className="animate-spin" /> : <FolderPlus size={18} />}
                Import Candidates
              </button>

              {importResult && <div className="mt-4 text-sm text-green-600">{importResult}</div>}

              {selectedCandidates.length > 0 && (
                <button
                  onClick={() => navigate('/tasks')}
                  className="w-full mt-3 flex items-center justify-center gap-2 border border-gray-200 text-gray-700 px-4 py-3 rounded-xl hover:bg-gray-50 transition-colors"
                >
                  Browse Tasks
                  <ArrowRight size={16} />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default ResearchDetailPage;
