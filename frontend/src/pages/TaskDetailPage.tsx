import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Play, Pause, Square, Plus, RefreshCw, FileText, AlertCircle, Trash2, ScrollText, ChevronDown, ChevronRight } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import Layout from '../components/Layout';
import ReReadModal from '../components/ReReadModal';
import { tasksApi, papersApi, deepResearchApi } from '../api/services';
import { Task, Paper, DeepResearchReport } from '../types';
import clsx from 'clsx';
import { MODEL_OPTIONS } from '../constants/models';

const MIN_REPORT_PAPERS = 2;
const REPORT_SCROLL_KEY_PREFIX = 'task-report-scroll:';
const REPORT_PANEL_SCROLL_KEY_PREFIX = 'task-report-panel-scroll:';

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
  const [traceExpanded, setTraceExpanded] = useState(true);
  const [traceRoundsExpanded, setTraceRoundsExpanded] = useState(false);
  const [reportModel, setReportModel] = useState('gemini-3-flash-preview');
  const [reportModelDirty, setReportModelDirty] = useState(false);
  const reportContentRef = useRef<HTMLDivElement | null>(null);

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

  const fetchReport = useCallback(async () => {
    if (!id) return;
    try {
      const data = await deepResearchApi.getTaskReport(id);
      setReport(data);
    } catch {
      setReport(null);
    } finally {
      setLoadingReport(false);
    }
  }, [id]);

  useEffect(() => {
    fetchData();
    setLoadingReport(true);
    fetchReport();
    const interval = setInterval(() => {
      fetchData();
      fetchReport();
    }, 3000);
    return () => clearInterval(interval);
  }, [fetchData, fetchReport]);

  useEffect(() => {
    setReportModel('gemini-3-flash-preview');
    setReportModelDirty(false);
  }, [id]);

  useEffect(() => {
    if (reportModelDirty) return;
    const preferredModel = report?.model_name || task?.model_name || 'gemini-3-flash-preview';
    setReportModel(preferredModel);
  }, [task?.model_name, report?.model_name, reportModelDirty]);

  useEffect(() => {
    if (!id || !task || loadingReport) return;
    const pageKey = `${REPORT_SCROLL_KEY_PREFIX}${id}`;
    const panelKey = `${REPORT_PANEL_SCROLL_KEY_PREFIX}${id}`;
    const savedPage = sessionStorage.getItem(pageKey);
    const savedPanel = sessionStorage.getItem(panelKey);
    const top = Number(savedPage);
    const panelTop = Number(savedPanel);
    const hasPage = savedPage !== null && Number.isFinite(top);
    const hasPanel = savedPanel !== null && Number.isFinite(panelTop);
    if (!hasPage && !hasPanel) return;
    const timer = window.setTimeout(() => {
      if (hasPage) {
        window.scrollTo({ top, behavior: 'auto' });
        sessionStorage.removeItem(pageKey);
      }
      if (hasPanel && reportContentRef.current) {
        reportContentRef.current.scrollTop = panelTop;
        sessionStorage.removeItem(panelKey);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [id, task, loadingReport, report]);

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

  const handleReRead = async (
    templateId: string,
    modelName: string,
    customReadingPrompts: string[],
    onlyFailed: boolean,
  ) => {
    if (!id) return;
    try {
      await tasksApi.reRead(id, templateId, modelName, customReadingPrompts, onlyFailed);
      fetchData();
    } catch (error) {
      console.error('Failed to reread task:', error);
    }
  };

  const handleGenerateReport = async () => {
    if (!id || generatingReport || report?.status === 'queued' || report?.status === 'running' || (task.statistics?.done || 0) < MIN_REPORT_PAPERS) return;
    setGeneratingReport(true);
    try {
      const reportQuery =
        (typeof task.agent_trace?.用户问题 === 'string' && task.agent_trace.用户问题.trim()) ||
        task.description ||
        task.name;
      const data = await deepResearchApi.generateTaskReport(id, {
        query: reportQuery,
        source_type: 'task',
        model_name: reportModel,
      });
      setReport(data);
      setReportModel(data.model_name || reportModel);
      setReportModelDirty(false);
    } catch (error) {
      console.error('Failed to generate task report:', error);
    } finally {
      setGeneratingReport(false);
    }
  };

  if (loading) return <Layout><div>Loading...</div></Layout>;
  if (!task) return <Layout><div>Task not found</div></Layout>;

  const traceBudget = task.agent_trace?.预算 as Record<string, number> | undefined;
  const traceBrief = task.agent_trace?.研究简报 as Record<string, unknown> | undefined;
  const traceRounds = (task.agent_trace?.搜索轮次 as Array<Record<string, unknown>> | undefined) || [];
  const traceSelected = (task.agent_trace?.最终选中文章 as Array<Record<string, unknown>> | undefined) || [];
  const traceSummary = task.agent_trace?.汇总 as Record<string, unknown> | undefined;
  const traceRuntime = (task.agent_trace as Record<string, unknown> | undefined)?.['_agent_runtime'] as Record<string, unknown> | undefined;
  const traceError = String(traceRuntime?.['error'] ?? task.agent_trace?.错误 ?? '').trim();
  const traceErrorType = String(traceRuntime?.['error_type'] ?? '').trim();
  const traceErrorDetail = String(traceRuntime?.['error_detail'] ?? '').trim();
  const reportBusy = report?.status === 'queued' || report?.status === 'running';
  const reportProgressPercent = report && report.progress_total > 0
    ? Math.min(100, Math.max(0, (report.progress_completed / report.progress_total) * 100))
    : 0;

  return (
    <Layout>
      {/* Header */}
      <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm mb-6">
        <div className="flex justify-between items-start">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl font-bold text-gray-900">{task.name}</h1>
              <span className={clsx("px-2.5 py-0.5 rounded-full text-xs font-medium capitalize", 
                task.status === 'preparing' ? 'bg-purple-100 text-purple-800' :
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
            {task.status !== 'running' && task.status !== 'completed' && task.status !== 'preparing' && (
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

      {task.agent_trace && (
        <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm mb-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <button
                type="button"
                onClick={() => setTraceExpanded((current) => !current)}
                className="flex items-center gap-2 text-lg font-semibold text-gray-900"
              >
                {traceExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                <span>Agent Trace</span>
              </button>
              <p className="text-sm text-gray-500 mt-1">展示 agent 如何拆解问题、搜索、筛选和决定进入精读的论文。</p>
              {traceRuntime && (
                <div className="text-sm text-gray-600 mt-2">
                  当前状态：{String(traceRuntime['state'] ?? '-')} · 当前阶段：{String(traceRuntime['current_stage'] ?? '-')}
                </div>
              )}
              {traceError && (
                <div className="mt-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 max-w-3xl">
                  <div className="font-medium">
                    执行失败
                    {traceErrorType ? ` · ${traceErrorType}` : ''}
                  </div>
                  <div className="mt-1 break-words">{traceError}</div>
                  {traceErrorDetail && traceErrorDetail !== traceError && (
                    <div className="mt-2 text-xs text-red-700 whitespace-pre-wrap break-words">
                      {traceErrorDetail}
                    </div>
                  )}
                </div>
              )}
            </div>
            {traceSummary && (
              <div className="text-right text-sm text-gray-500">
                <div>实际搜索轮数：{String(traceSummary['实际搜索轮数'] ?? '-')}</div>
                <div>最终选中文章数：{String(traceSummary['最终选中文章数'] ?? '-')}</div>
              </div>
            )}
          </div>

          {traceExpanded && (
            <div className="mt-5 space-y-5">
              {traceBudget && (
                <div className="border border-gray-200 rounded-xl p-4">
                  <h3 className="text-sm font-semibold text-gray-900 mb-3">预算</h3>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
                    {Object.entries(traceBudget).map(([key, value]) => (
                      <div key={key} className="rounded-lg bg-gray-50 px-3 py-2">
                        <div className="text-gray-500">{key}</div>
                        <div className="font-medium text-gray-900 mt-1">{String(value)}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {traceBrief && (
                <div className="border border-gray-200 rounded-xl p-4">
                  <h3 className="text-sm font-semibold text-gray-900 mb-3">研究简报</h3>
                  <div className="space-y-3 text-sm">
                    <div>
                      <div className="text-gray-500">研究目标</div>
                      <div className="text-gray-900 mt-1">{String(traceBrief['研究目标'] ?? '-')}</div>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <div className="text-gray-500">范围模式</div>
                        <div className="text-gray-900 mt-1">{String(traceBrief['范围模式'] ?? '-')}</div>
                      </div>
                      <div>
                        <div className="text-gray-500">目标年份</div>
                        <div className="text-gray-900 mt-1">{Array.isArray(traceBrief['目标年份']) ? (traceBrief['目标年份'] as unknown[]).join(', ') : '-'}</div>
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-500">搜索方向</div>
                      <div className="flex flex-wrap gap-2 mt-2">
                        {Array.isArray(traceBrief['搜索方向']) ? (traceBrief['搜索方向'] as unknown[]).map((item, index) => (
                          <span key={`${item}-${index}`} className="px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 text-xs font-medium">
                            {String(item)}
                          </span>
                        )) : <span className="text-gray-900">-</span>}
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-500">初始查询</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {Array.isArray(traceBrief['初始查询']) ? (traceBrief['初始查询'] as unknown[]).map((item, index) => (
                          <code key={`${item}-${index}`} className="px-2.5 py-1 rounded bg-gray-100 text-gray-800 text-xs">
                            {String(item)}
                          </code>
                        )) : <span className="text-gray-900">-</span>}
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-500">精排查询</div>
                      <div className="text-gray-900 mt-1">{String(traceBrief['精排查询'] ?? '-')}</div>
                    </div>
                  </div>
                </div>
              )}

              <div className="border border-gray-200 rounded-xl p-4">
                <div className="flex items-center justify-between gap-3 mb-3">
                  <h3 className="text-sm font-semibold text-gray-900">搜索轮次</h3>
                  <button
                    type="button"
                    onClick={() => setTraceRoundsExpanded((current) => !current)}
                    className="inline-flex items-center gap-1.5 text-sm font-medium text-blue-700 hover:text-blue-900"
                  >
                    {traceRoundsExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    <span>{traceRoundsExpanded ? '收起搜索轮次' : '展开搜索轮次'}</span>
                  </button>
                </div>
                {traceRounds.length === 0 ? (
                  <div className="text-sm text-gray-500">没有可用的搜索轮次信息。</div>
                ) : !traceRoundsExpanded ? (
                  <div className="text-sm text-gray-500">
                    已收起 {traceRounds.length} 轮搜索过程。展开后可查看每轮 query、判断、候选和选文理由。
                  </div>
                ) : (
                  <div className="space-y-4">
                    {traceRounds.map((round, index) => (
                      <div key={`trace-round-${index}`} className="border border-gray-200 rounded-xl p-4">
                        <div className="flex items-center justify-between gap-4">
                          <div className="font-medium text-gray-900">第 {String(round['轮次'] ?? index + 1)} 轮</div>
                          <div className="text-xs text-gray-500">
                            粗排命中 {String(round['粗排命中数'] ?? 0)} · 合并候选 {String(round['合并候选数'] ?? 0)} · 精排候选 {String(round['精排候选数'] ?? 0)}
                          </div>
                        </div>
                        <div className="mt-3">
                          <div className="text-xs text-gray-500 mb-2">本轮查询</div>
                          <div className="flex flex-wrap gap-2">
                            {Array.isArray(round['本轮查询']) ? (round['本轮查询'] as unknown[]).map((item, queryIndex) => (
                              <code key={`${item}-${queryIndex}`} className="px-2.5 py-1 rounded bg-gray-100 text-gray-800 text-xs">
                                {String(item)}
                              </code>
                            )) : <span className="text-sm text-gray-900">-</span>}
                          </div>
                        </div>
                        <div className="mt-3 text-sm">
                          <div className="text-gray-500">本轮结果总结</div>
                          <div className="text-gray-900 mt-1">{String(round['本轮结果总结'] ?? '-')}</div>
                        </div>
                        <div className="mt-3 text-sm">
                          <div className="text-gray-500">本轮判断</div>
                          <div className="text-gray-900 mt-1">{String(round['本轮判断'] ?? '-')}</div>
                        </div>
                        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                          <div>
                            <div className="text-gray-500">缺失方向</div>
                            <div className="mt-1 text-gray-900">
                              {Array.isArray(round['缺失方向']) && (round['缺失方向'] as unknown[]).length > 0
                                ? (round['缺失方向'] as unknown[]).join(', ')
                                : '无'}
                            </div>
                          </div>
                          <div>
                            <div className="text-gray-500">下一轮查询</div>
                            <div className="mt-1 text-gray-900">
                              {Array.isArray(round['下一轮查询']) && (round['下一轮查询'] as unknown[]).length > 0
                                ? (round['下一轮查询'] as unknown[]).join(' | ')
                                : '无'}
                            </div>
                          </div>
                        </div>
                        <div className="mt-3">
                          <div className="text-xs text-gray-500 mb-2">本轮选中文章</div>
                          {Array.isArray(round['本轮选中文章']) && (round['本轮选中文章'] as unknown[]).length > 0 ? (
                            <div className="space-y-2">
                              {(round['本轮选中文章'] as Array<Record<string, unknown>>).map((item, paperIndex) => (
                                <div key={`round-paper-${paperIndex}`} className="rounded-lg bg-gray-50 px-3 py-2">
                                  <div className="text-sm font-medium text-gray-900">{String(item['论文标题'] ?? '-')}</div>
                                  <div className="text-xs text-gray-500 mt-1">
                                    {String(item['会议'] ?? '')} {String(item['年份'] ?? '')} · 方向 {String(item['方向'] ?? '-')} · 优先级 {String(item['优先级'] ?? '-')}
                                  </div>
                                  <div className="text-sm text-gray-700 mt-1">{String(item['选择理由'] ?? '-')}</div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="text-sm text-gray-500">本轮没有新增选中文章。</div>
                          )}
                        </div>
                        <div className="mt-3">
                          <div className="text-xs text-gray-500 mb-2">本轮候选判断</div>
                          {Array.isArray(round['本轮候选判断']) && (round['本轮候选判断'] as unknown[]).length > 0 ? (
                            <div className="space-y-2">
                              {(round['本轮候选判断'] as Array<Record<string, unknown>>).map((item, candidateIndex) => (
                                <div key={`round-candidate-${candidateIndex}`} className="rounded-lg border border-gray-200 px-3 py-2">
                                  <div className="flex items-start justify-between gap-3">
                                    <div className="min-w-0">
                                      <div className="text-sm font-medium text-gray-900">{String(item['论文标题'] ?? '-')}</div>
                                      <div className="text-xs text-gray-500 mt-1">
                                        {String(item['会议'] ?? '')} {String(item['年份'] ?? '')} · 方向 {String(item['方向'] ?? '-')} · 优先级 {String(item['优先级'] ?? '-')}
                                      </div>
                                    </div>
                                    <div className={clsx(
                                      'shrink-0 rounded-full px-2 py-0.5 text-xs font-medium',
                                      item['是否精读']
                                        ? 'bg-green-100 text-green-700'
                                        : 'bg-gray-100 text-gray-700'
                                    )}>
                                      {item['是否精读'] ? '进入精读' : '不进入精读'}
                                    </div>
                                  </div>
                                  <div className="text-sm text-gray-700 mt-2">{String(item['判断理由'] ?? '-')}</div>
                                  <div className="text-xs text-gray-500 mt-2">
                                    粗排 {String(item['粗排分数'] ?? '-')} · 精排 {String(item['精排分数'] ?? '-')}
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="text-sm text-gray-500">本轮没有候选判断信息。</div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="border border-gray-200 rounded-xl p-4">
                <h3 className="text-sm font-semibold text-gray-900 mb-3">最终进入精读的论文</h3>
                {traceSelected.length === 0 ? (
                  <div className="text-sm text-gray-500">没有最终选中的论文。</div>
                ) : (
                  <div className="space-y-3">
                    {traceSelected.map((item, index) => (
                      <div key={`selected-paper-${index}`} className="rounded-xl bg-gray-50 border border-gray-200 px-4 py-3">
                        <div className="flex items-start justify-between gap-4">
                          <div className="min-w-0">
                            <div className="font-medium text-gray-900">{String(item['论文标题'] ?? '-')}</div>
                            <div className="text-xs text-gray-500 mt-1">
                              {String(item['会议'] ?? '')} {String(item['年份'] ?? '')} · 方向 {String(item['方向'] ?? '-')} · 优先级 {String(item['优先级'] ?? '-')}
                            </div>
                            <div className="text-sm text-gray-700 mt-2">{String(item['选择理由'] ?? '-')}</div>
                          </div>
                          <div className="shrink-0 text-right text-xs text-gray-500">
                            <div>粗排 {String(item['粗排分数'] ?? '-')}</div>
                            <div className="mt-1">精排 {String(item['精排分数'] ?? '-')}</div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Paper List */}
        <div className="lg:col-span-2 space-y-4">
          <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm">
            <div className="flex items-center justify-between gap-4 mb-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Deep Research Report</h2>
                <p className="text-sm text-gray-500 mt-1">Aggregate the interpreted papers in this task into one report.</p>
              </div>
              <div className="flex items-center gap-3">
                <select
                  value={reportModel}
                  onChange={(e) => {
                    setReportModel(e.target.value);
                    setReportModelDirty(true);
                  }}
                  className="px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
                >
                  {MODEL_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <button
                  onClick={handleGenerateReport}
                  disabled={generatingReport || reportBusy || (task.statistics?.done || 0) < MIN_REPORT_PAPERS}
                  className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition-colors disabled:opacity-50"
                >
                  {(generatingReport || reportBusy) ? <RefreshCw size={18} className="animate-spin" /> : <ScrollText size={18} />}
                  {reportBusy ? 'Generating Report...' : report ? 'Regenerate Report' : 'Generate Report'}
                </button>
              </div>
            </div>
            <div className="text-xs text-gray-500 mb-4">
              Requires at least {MIN_REPORT_PAPERS} completed paper interpretations in this task. The selected report model applies only to this report generation.
            </div>
            {report && (
              <div className="mb-4 rounded-xl border border-gray-200 bg-gray-50 px-4 py-3">
                <div className="flex items-center justify-between gap-4">
                  <div className="text-sm">
                    <span className="font-medium text-gray-900">状态：</span>
                    <span className="text-gray-700">{report.status}</span>
                    {report.progress_stage && (
                      <>
                        <span className="mx-2 text-gray-400">·</span>
                        <span className="font-medium text-gray-900">阶段：</span>
                        <span className="text-gray-700">{report.progress_stage}</span>
                      </>
                    )}
                  </div>
                  <div className="text-xs text-gray-500">
                    {report.progress_total > 0 ? `${report.progress_completed}/${report.progress_total}` : '-'}
                  </div>
                </div>
                {report.progress_message && (
                  <div className="text-sm text-gray-700 mt-2">{report.progress_message}</div>
                )}
                {report.progress_total > 0 && (
                  <div className="mt-3 h-2 rounded-full bg-gray-200 overflow-hidden">
                    <div
                      className="h-full bg-slate-900 transition-all"
                      style={{ width: `${reportProgressPercent}%` }}
                    />
                  </div>
                )}
                {report.error && (
                  <div className="text-sm text-red-600 mt-2">{report.error}</div>
                )}
              </div>
            )}
            {loadingReport ? (
              <div className="text-sm text-gray-500">Loading report...</div>
            ) : report ? (
              <div
                ref={reportContentRef}
                className="rounded-xl bg-gray-50 border border-gray-200 p-4 text-sm leading-7 text-gray-800 max-h-[34rem] overflow-y-auto"
              >
                <div className="report-markdown">
                  <ReactMarkdown
                    remarkPlugins={[remarkMath]}
                    rehypePlugins={[rehypeKatex]}
                    components={{
                      a: ({ href, title, children }) => {
                        const linkHref = href || '#';
                        const isInternalReaderLink = linkHref.startsWith('/reader/');
                        return (
                          <a
                            href={linkHref}
                            title={title}
                            className={clsx(
                              isInternalReaderLink
                                ? "inline-flex items-center justify-center min-w-[1.4rem] h-5 px-1 mr-1 rounded bg-blue-50 text-[11px] font-semibold leading-none text-blue-700 no-underline align-super hover:bg-blue-100 hover:text-blue-900"
                                : "underline underline-offset-2 decoration-dotted text-blue-600 hover:text-blue-800"
                            )}
                            onClick={(event) => {
                              if (!isInternalReaderLink) {
                                return;
                              }
                              if (
                                event.button !== 0 ||
                                event.metaKey ||
                                event.ctrlKey ||
                                event.shiftKey ||
                                event.altKey
                              ) {
                                return;
                              }
                              event.preventDefault();
                              if (id) {
                                sessionStorage.setItem(`${REPORT_SCROLL_KEY_PREFIX}${id}`, String(window.scrollY));
                                sessionStorage.setItem(
                                  `${REPORT_PANEL_SCROLL_KEY_PREFIX}${id}`,
                                  String(reportContentRef.current?.scrollTop ?? 0),
                                );
                              }
                              navigate(linkHref);
                            }}
                          >
                            {children}
                          </a>
                        );
                      },
                    }}
                  >
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
        initialTemplateId={task.template_id}
        initialModelName={task.model_name}
        initialPrompts={task.custom_reading_prompts}
      />
    </Layout>
  );
};

export default TaskDetailPage;
