import React, { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { AlertCircle, FileText, Image as ImageIcon, Loader2, MessageCircle, RefreshCw, Sparkles } from 'lucide-react';
import clsx from 'clsx';
import Layout from '../components/Layout';
import { communityApi } from '../api/services';
import { CommunityPaperAnswer, CommunityTopic, CommunityTopicResponse } from '../types';

const CommunityPage: React.FC = () => {
  const [topics, setTopics] = useState<CommunityTopic[]>([]);
  const [selectedTopicId, setSelectedTopicId] = useState('');
  const [topicData, setTopicData] = useState<CommunityTopicResponse | null>(null);
  const [loadingTopics, setLoadingTopics] = useState(true);
  const [loadingTopic, setLoadingTopic] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');

  const selectedTopic = useMemo(
    () => topics.find((topic) => topic.id === selectedTopicId) || topics[0] || null,
    [selectedTopicId, topics],
  );

  const loadTopics = async () => {
    setLoadingTopics(true);
    setError('');
    try {
      const response = await communityApi.listTopics();
      setTopics(response.topics);
      if (!selectedTopicId && response.topics.length > 0) {
        setSelectedTopicId(response.topics[0].id);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load community topics';
      setError(message);
    } finally {
      setLoadingTopics(false);
    }
  };

  const loadTopic = async (topicId: string) => {
    if (!topicId) {
      return;
    }
    setLoadingTopic(true);
    setError('');
    try {
      const response = await communityApi.getTopic(topicId);
      setTopicData(response);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load topic';
      setError(message);
    } finally {
      setLoadingTopic(false);
    }
  };

  useEffect(() => {
    loadTopics();
  }, []);

  useEffect(() => {
    if (selectedTopicId) {
      loadTopic(selectedTopicId);
    }
  }, [selectedTopicId]);

  const precomputeTopic = async () => {
    if (!selectedTopic || generating) {
      return;
    }
    setGenerating(true);
    setError('');
    try {
      const response = await communityApi.generateTopic(selectedTopic.id, {
        limit: 5,
        max_text_chars: 120000,
        figure_max_pages: 12,
      });
      setTopicData(response);
      await loadTopics();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to precompute answers';
      setError(message);
    } finally {
      setGenerating(false);
    }
  };

  const answers = topicData?.results || [];

  return (
    <Layout>
      <div className="h-[calc(100vh-4rem)] min-h-[680px] flex flex-col">
        <div className="shrink-0 border-b border-gray-200 pb-5 mb-5">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-10 h-10 rounded-lg bg-blue-600 text-white flex items-center justify-center">
                <MessageCircle size={22} />
              </div>
              <div className="min-w-0">
                <h1 className="text-2xl font-bold text-gray-900">Community</h1>
                <p className="text-sm text-gray-500 mt-1">Browse precomputed questions and swipe through paper answers.</p>
              </div>
            </div>
            <button
              type="button"
              onClick={loadTopics}
              disabled={loadingTopics}
              className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              <RefreshCw size={16} className={clsx(loadingTopics && 'animate-spin')} />
              Refresh
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 flex items-center gap-2">
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        <div className="flex-1 min-h-0 flex gap-5">
          <aside className="w-[380px] shrink-0 border border-gray-200 bg-white rounded-lg flex flex-col min-h-0">
            <div className="px-4 py-3 border-b border-gray-100">
              <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Questions</div>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto p-2">
              {loadingTopics && (
                <div className="p-4 text-sm text-gray-500 flex items-center gap-2">
                  <Loader2 size={16} className="animate-spin" />
                  Loading questions...
                </div>
              )}
              {!loadingTopics && topics.map((topic) => (
                <button
                  key={topic.id}
                  type="button"
                  onClick={() => setSelectedTopicId(topic.id)}
                  className={clsx(
                    'w-full text-left rounded-md border px-3 py-3 mb-2 transition-colors',
                    selectedTopic?.id === topic.id ? 'border-blue-200 bg-blue-50' : 'border-gray-100 hover:bg-gray-50',
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-gray-900 leading-5">{topic.question}</div>
                      <div className="text-xs text-gray-500 mt-2 leading-5">{topic.description}</div>
                    </div>
                    <span className={clsx(
                      'shrink-0 rounded-full px-2 py-1 text-[11px] font-medium',
                      topic.cached ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500',
                    )}>
                      {topic.cached ? `${topic.answer_count} answers` : 'empty'}
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {topic.tags.map((tag) => (
                      <span key={tag} className="rounded-full bg-white border border-gray-200 px-2 py-0.5 text-[11px] text-gray-600">
                        {tag}
                      </span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
          </aside>

          <section className="flex-1 min-w-0 border border-gray-200 bg-white rounded-lg overflow-hidden flex flex-col">
            <div className="shrink-0 border-b border-gray-100 px-6 py-5">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-blue-600 uppercase tracking-wide">
                    {selectedTopic?.tags.join(' / ') || 'Community'}
                  </div>
                  <h2 className="mt-1 text-xl font-semibold text-gray-900 leading-snug">
                    {selectedTopic?.question || 'Select a question'}
                  </h2>
                  {topicData?.topic.updated_at && (
                    <div className="mt-2 text-xs text-gray-500">
                      Updated {new Date(topicData.topic.updated_at).toLocaleString()}
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  onClick={precomputeTopic}
                  disabled={!selectedTopic || generating}
                  className="shrink-0 inline-flex items-center gap-2 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {generating ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
                  Precompute
                </button>
              </div>
            </div>

            <div className="flex-1 min-h-0 overflow-y-auto snap-y snap-mandatory bg-gray-50">
              {loadingTopic && (
                <div className="h-full flex items-center justify-center text-sm text-gray-500 gap-2">
                  <Loader2 size={16} className="animate-spin" />
                  Loading cached answers...
                </div>
              )}

              {!loadingTopic && answers.length === 0 && (
                <div className="h-full flex items-center justify-center px-8">
                  <div className="max-w-md text-center">
                    <div className="mx-auto w-12 h-12 rounded-lg bg-gray-100 text-gray-500 flex items-center justify-center">
                      <MessageCircle size={24} />
                    </div>
                    <h3 className="mt-4 font-semibold text-gray-900">No precomputed answers yet</h3>
                    <p className="mt-2 text-sm text-gray-500 leading-6">
                      This page is now a feed-style browser. Generate this topic once, then future visits will load the cached paper answers immediately.
                    </p>
                  </div>
                </div>
              )}

              {!loadingTopic && answers.map((paper) => (
                <PaperAnswerCard key={`${paper.conference}-${paper.year}-${paper.paper_id}`} paper={paper} />
              ))}
            </div>
          </section>
        </div>
      </div>
    </Layout>
  );
};

const PaperAnswerCard: React.FC<{ paper: CommunityPaperAnswer }> = ({ paper }) => (
  <article className="snap-start min-h-full bg-white border-b border-gray-200 px-8 py-7">
    <div className="max-w-4xl">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-xs font-semibold text-blue-600 uppercase tracking-wide">
            Answer {paper.rank} · {paper.conference} {paper.year}
          </div>
          <h3 className="mt-1 text-xl font-semibold text-gray-950 leading-snug">{paper.title}</h3>
          <div className="mt-2 text-xs text-gray-500">
            {paper.authors.slice(0, 5).join(', ')}
            {paper.authors.length > 5 ? ' et al.' : ''}
            {typeof paper.seconds === 'number' ? ` · ${paper.seconds.toFixed(1)}s generated` : ''}
          </div>
        </div>
        {paper.source_url && (
          <a
            href={paper.source_url}
            target="_blank"
            rel="noreferrer"
            className="shrink-0 inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            <FileText size={16} />
            Source
          </a>
        )}
      </div>

      {paper.error && (
        <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {paper.error}
        </div>
      )}

      {paper.answer ? (
        <div className="mt-6 text-[15px] leading-7 text-gray-800">
          <ReactMarkdown
            components={{
              p: ({ children }) => <p className="mb-4">{children}</p>,
              strong: ({ children }) => <strong className="font-semibold text-gray-950">{children}</strong>,
              ul: ({ children }) => <ul className="mb-4 list-disc pl-5 space-y-1">{children}</ul>,
              ol: ({ children }) => <ol className="mb-4 list-decimal pl-5 space-y-1">{children}</ol>,
            }}
          >
            {paper.answer}
          </ReactMarkdown>
        </div>
      ) : (
        <div className="mt-6 text-sm text-gray-500">No answer generated.</div>
      )}

      {paper.figures.length > 0 && (
        <div className="mt-8 pt-5 border-t border-gray-100">
          <div className="flex items-center gap-2 text-sm font-semibold text-gray-900 mb-3">
            <ImageIcon size={16} />
            Figures Mentioned
          </div>
          <div className="space-y-3">
            {paper.figures.map((figure) => (
              <div key={figure.id} className="rounded-md border border-gray-200 px-3 py-3 bg-gray-50">
                <div className="flex items-center justify-between gap-3 text-xs text-gray-500">
                  <span className="font-medium text-gray-800">{figure.label}</span>
                  <span>Page {figure.page_number} · confidence {figure.confidence.toFixed(2)}</span>
                </div>
                <p className="mt-2 text-sm text-gray-700 leading-6">{figure.caption}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  </article>
);

export default CommunityPage;
