import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Play, Pause, Square, Plus, RefreshCw, FileText, AlertCircle, Trash2, ScrollText } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import Layout from '../components/Layout';
import ReReadModal from '../components/ReReadModal';
import { tasksApi, papersApi, deepResearchApi } from '../api/services';
import { Task, Paper, DeepResearchReport } from '../types';
import clsx from 'clsx';

const MIN_REPORT_PAPERS = 2;

const TaskDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [task, setTask] = useState<Task | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);
  const [paperList, setPaperList] = useState<string[]>(['']);
  const [addingPapers, setAddingPapers] = useState(false);
  const [isReReadModalOpen, setIsReReadModalOpen] = useState(false);
  const [report, setReport] = useState<DeepResearchReport | null>(null);
  const [loadingReport, setLoadingReport] = useState(false);
  const [generatingReport, setGeneratingReport] = useState(false);

  const fetchData = useCallback(async () => {
    if (!id) return;
    try {
      const [taskData, papersData] = await Promise.all([
        tasksApi.get(id),
        tasksApi.getPapers(id)
      ]);
      setTask(taskData);
      setPapers(papersData);
    } catch (error) {
      console.error('Failed to fetch task details:', error);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000); // Poll for updates
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    if (!id) return;
    const fetchReport = async () => {
      setLoadingReport(true);
      try {
        const data = await deepResearchApi.getTaskReport(id);
        setReport(data);
      } catch {
        setReport(null);
      } finally {
        setLoadingReport(false);
      }
    };
    fetchReport();
  }, [id]);

  const handleStatusChange = async (status: string) => {
    if (!id) return;
    try {
      await tasksApi.updateStatus(id, status);
      fetchData();
    } catch (error) {
      console.error('Failed to update status:', error);
    }
  };

  const handleAddPapers = async () => {
    if (!id) return;
    const validPapers = paperList.filter(t => t.trim());
    if (validPapers.length === 0) return;

    setAddingPapers(true);
    try {
      await tasksApi.addPapers(id, { titles: validPapers });
      setPaperList(['']);
      fetchData();
    } catch (error) {
      console.error('Failed to add papers:', error);
    } finally {
      setAddingPapers(false);
    }
  };

  const handleAddRow = () => {
    setPaperList([...paperList, '']);
  };

  const handleRemoveRow = (index: number) => {
    const newList = paperList.filter((_, i) => i !== index);
    setPaperList(newList.length ? newList : ['']);
  };

  const handlePaperChange = (index: number, value: string) => {
    const newList = [...paperList];
    newList[index] = value;
    setPaperList(newList);
  };

  const handleRetry = async (paperId: string) => {
    try {
      await papersApi.retry(paperId);
      fetchData();
    } catch (error) {
      console.error('Failed to retry paper:', error);
    }
  };

  const handleDelete = async (paperId: string) => {
    if (!window.confirm('Are you sure you want to delete this paper?')) return;
    try {
      await papersApi.delete(paperId);
      fetchData();
    } catch (error) {
      console.error('Failed to delete paper:', error);
    }
  };

  const handleReRead = async (templateId: string, modelName: string) => {
    if (!id) return;
    try {
      await tasksApi.reRead(id, templateId, modelName);
      fetchData();
    } catch (error) {
      console.error('Failed to reread task:', error);
    }
  };

  const handleGenerateReport = async () => {
    if (!id || generatingReport || (task.statistics?.done || 0) < MIN_REPORT_PAPERS) return;
    setGeneratingReport(true);
    try {
      const data = await deepResearchApi.generateTaskReport(id, {
        query: task.description || task.name,
        source_type: 'task',
      });
      setReport(data);
    } catch (error) {
      console.error('Failed to generate task report:', error);
    } finally {
      setGeneratingReport(false);
    }
  };

  if (loading) return <Layout><div>Loading...</div></Layout>;
  if (!task) return <Layout><div>Task not found</div></Layout>;

  return (
    <Layout>
      {/* Header */}
      <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm mb-6">
        <div className="flex justify-between items-start">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl font-bold text-gray-900">{task.name}</h1>
              <span className={clsx("px-2.5 py-0.5 rounded-full text-xs font-medium capitalize", 
                task.status === 'running' ? 'bg-green-100 text-green-800' :
                task.status === 'paused' ? 'bg-yellow-100 text-yellow-800' :
                task.status === 'completed' ? 'bg-blue-100 text-blue-800' :
                'bg-gray-100 text-gray-800'
              )}>
                {task.status}
              </span>
            </div>
            <p className="text-gray-500">{task.description}</p>
          </div>
          
          <div className="flex gap-2">
            {task.status !== 'running' && task.status !== 'completed' && (
              <button
                onClick={() => handleStatusChange('running')}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
              >
                <Play size={18} /> Start
              </button>
            )}
            {task.status === 'running' && (
              <button
                onClick={() => handleStatusChange('paused')}
                className="flex items-center gap-2 px-4 py-2 bg-yellow-500 text-white rounded-lg hover:bg-yellow-600 transition-colors"
              >
                <Pause size={18} /> Pause
              </button>
            )}
            {task.status !== 'completed' && (
              <button
                onClick={() => handleStatusChange('completed')}
                className="flex items-center gap-2 px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors"
              >
                <Square size={18} /> Finish
              </button>
            )}
            <button
                onClick={() => setIsReReadModalOpen(true)}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
            >
                <RefreshCw size={18} /> Re-read
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-5 gap-4 mt-6 pt-6 border-t border-gray-100">
          <div className="text-center">
            <div className="text-2xl font-bold text-gray-900">{task.statistics?.total || 0}</div>
            <div className="text-xs text-gray-500 uppercase tracking-wide mt-1">Total</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-green-600">{task.statistics?.done || 0}</div>
            <div className="text-xs text-gray-500 uppercase tracking-wide mt-1">Done</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-blue-600">{task.statistics?.processing || 0}</div>
            <div className="text-xs text-gray-500 uppercase tracking-wide mt-1">Processing</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-red-600">{task.statistics?.failed || 0}</div>
            <div className="text-xs text-gray-500 uppercase tracking-wide mt-1">Failed</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-gray-600">{task.statistics?.queued || 0}</div>
            <div className="text-xs text-gray-500 uppercase tracking-wide mt-1">Queued</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Paper List */}
        <div className="lg:col-span-2 space-y-4">
          <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm">
            <div className="flex items-center justify-between gap-4 mb-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Deep Research Report</h2>
                <p className="text-sm text-gray-500 mt-1">Aggregate the interpreted papers in this task into one report.</p>
              </div>
              <button
                onClick={handleGenerateReport}
                disabled={generatingReport || (task.statistics?.done || 0) < MIN_REPORT_PAPERS}
                className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition-colors disabled:opacity-50"
              >
                {generatingReport ? <RefreshCw size={18} className="animate-spin" /> : <ScrollText size={18} />}
                {report ? 'Regenerate Report' : 'Generate Report'}
              </button>
            </div>
            <div className="text-xs text-gray-500 mb-4">
              Requires at least {MIN_REPORT_PAPERS} completed paper interpretations in this task.
            </div>
            {loadingReport ? (
              <div className="text-sm text-gray-500">Loading report...</div>
            ) : report ? (
              <div className="rounded-xl bg-gray-50 border border-gray-200 p-4 text-sm leading-7 text-gray-800 max-h-[34rem] overflow-y-auto">
                <div className="report-markdown">
                  <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                    {report.content}
                  </ReactMarkdown>
                </div>
              </div>
            ) : (
              <div className="text-sm text-gray-500">
                No report yet. Generate one after some papers in this task have finished interpretation.
              </div>
            )}
          </div>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Papers</h2>
          {papers.length === 0 ? (
            <div className="text-center py-12 bg-white rounded-xl border border-gray-200 text-gray-500">
              No papers yet. Add some titles to get started.
            </div>
          ) : (
            papers.map(paper => (
              <div key={paper.id} className="bg-white p-4 rounded-xl border border-gray-200 hover:shadow-sm transition-shadow">
                <div className="flex justify-between items-start gap-4">
                  <div className="flex-1">
                    <h3 className="font-medium text-gray-900 mb-1">{paper.title}</h3>
                    <div className="flex items-center gap-3 text-sm text-gray-500">
                      {paper.source && <span className="uppercase text-xs font-bold px-2 py-0.5 bg-gray-100 rounded">{paper.source}</span>}
                      {paper.failure_reason && <span className="text-red-500 flex items-center gap-1"><AlertCircle size={14} /> {paper.failure_reason}</span>}
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    {paper.status === 'done' && (
                      <button
                        onClick={() => navigate(`/reader/${paper.id}`)}
                        className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-base font-medium shadow-sm"
                      >
                        <FileText size={18} /> Read
                      </button>
                    )}
                    {paper.status === 'processing' && (
                      <span className="flex items-center gap-1 text-blue-500 text-sm">
                        <RefreshCw size={16} className="animate-spin" /> Processing
                      </span>
                    )}
                    {paper.status === 'queued' && (
                      <span className="text-gray-400 text-sm">Queued</span>
                    )}
                    {paper.status === 'failed' && (
                      <div className="flex items-center gap-2">
                        <span className="text-red-500 text-sm font-medium">Failed</span>
                        <button
                          onClick={() => handleRetry(paper.id)}
                          className="p-2 text-gray-600 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                          title="Retry"
                        >
                          <RefreshCw size={18} />
                        </button>
                      </div>
                    )}
                    
                    <button
                      onClick={() => handleDelete(paper.id)}
                      className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors ml-2"
                      title="Delete"
                    >
                      <Trash2 size={18} />
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Add Papers Sidebar */}
        <div className="space-y-6">
          <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm sticky top-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <Plus size={20} /> Add Papers
            </h3>
            
            <div className="space-y-2 mb-3">
                {paperList.map((paper, index) => (
                    <div key={index} className="flex gap-2">
                        <input
                            name={`paper-title-${index}`}
                            type="text"
                            value={paper}
                            onChange={(e) => handlePaperChange(index, e.target.value)}
                            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
                            placeholder="Paper title..."
                        />
                        <button
                            type="button"
                            onClick={() => handleRemoveRow(index)}
                            className="p-2 text-gray-400 hover:text-red-500 transition-colors"
                        >
                            <Trash2 size={16} />
                        </button>
                    </div>
                ))}
            </div>
            
            <button
                onClick={handleAddRow}
                className="mb-4 text-sm text-blue-600 hover:text-blue-700 flex items-center gap-1 font-medium"
            >
                <Plus size={16} /> Add Row
            </button>

            <button
              onClick={handleAddPapers}
              disabled={addingPapers || paperList.every(t => !t.trim())}
              className="w-full bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 flex justify-center items-center gap-2"
            >
              {addingPapers ? <RefreshCw className="animate-spin" size={18} /> : <Plus size={18} />}
              Add to Queue
            </button>
            <p className="text-xs text-gray-500 mt-3">
              The system will automatically process these papers if the task is running.
            </p>
          </div>
        </div>
      </div>

      <ReReadModal
        isOpen={isReReadModalOpen}
        onClose={() => setIsReReadModalOpen(false)}
        onConfirm={handleReRead}
        title="Re-read Task"
      />
    </Layout>
  );
};

export default TaskDetailPage;
