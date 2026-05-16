import React, { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { AlertCircle, FileText, Image as ImageIcon, Loader2, MessageCircle, RefreshCw } from 'lucide-react';
import clsx from 'clsx';
import Layout from '../components/Layout';
import { buildApiUrl } from '../api';
import { communityApi } from '../api/services';
import { CommunityPaperAnswer, CommunityTopic, CommunityTopicResponse } from '../types';

const CommunityPage: React.FC = () => {
  const [topics, setTopics] = useState<CommunityTopic[]>([]);
  const [selectedTopicId, setSelectedTopicId] = useState('');
  const [topicData, setTopicData] = useState<CommunityTopicResponse | null>(null);
  const [loadingTopics, setLoadingTopics] = useState(true);
  const [loadingTopic, setLoadingTopic] = useState(false);
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
                    <h3 className="mt-4 font-semibold text-gray-900">This topic is not ready yet</h3>
                    <p className="mt-2 text-sm text-gray-500 leading-6">
                      Community is cache-first. Answers are prepared offline and then shown here automatically.
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
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-500">
            {paper.answerability && (
              <span className={clsx(
                'rounded-full px-2 py-0.5 font-medium',
                paper.answerability === 'yes' ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-700',
              )}>
                {paper.answerability === 'yes' ? 'direct answer' : 'partial answer'}
              </span>
            )}
            <span>
            {paper.authors.slice(0, 5).join(', ')}
            {paper.authors.length > 5 ? ' et al.' : ''}
            {typeof paper.seconds === 'number' ? ` · ${paper.seconds.toFixed(1)}s generated` : ''}
            </span>
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

      {paper.answerability_reason && (
        <div className="mt-4 rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-600">
          {paper.answerability_reason}
        </div>
      )}

      {paper.answer ? (
        <div className="mt-6 text-[15px] leading-7 text-gray-800">
          <AnswerWithInlineFigures paper={paper} />
        </div>
      ) : (
        <div className="mt-6 text-sm text-gray-500">No answer generated.</div>
      )}
    </div>
  </article>
);

const markdownComponents = {
  p: ({ children }: { children?: React.ReactNode }) => <p className="mb-4">{children}</p>,
  strong: ({ children }: { children?: React.ReactNode }) => <strong className="font-semibold text-gray-950">{children}</strong>,
  ul: ({ children }: { children?: React.ReactNode }) => <ul className="mb-4 list-disc pl-5 space-y-1">{children}</ul>,
  ol: ({ children }: { children?: React.ReactNode }) => <ol className="mb-4 list-decimal pl-5 space-y-1">{children}</ol>,
};

const figureReferencePattern = /\b(?:fig(?:ure)?\.?|图)\s*([0-9]+[A-Za-z]?)/gi;

const normalizeFigureNumber = (value: string) => value.toLowerCase().replace(/[^0-9a-z]/g, '');

const figureNumber = (figure: CommunityPaperAnswer['figures'][number]) => {
  const fromLabel = figure.label.match(/(?:fig(?:ure)?\.?|图)\s*([0-9]+[A-Za-z]?)/i);
  if (fromLabel) {
    return normalizeFigureNumber(fromLabel[1]);
  }
  const fromId = figure.id.match(/fig_0*([0-9]+[A-Za-z]?)/i);
  return fromId ? normalizeFigureNumber(fromId[1]) : '';
};

const displayFigureLabel = (figure: CommunityPaperAnswer['figures'][number]) => {
  const number = figureNumber(figure);
  return number ? `图 ${number.toUpperCase()}` : figure.label;
};

const stripMarkdown = (value: string) =>
  value
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[[^\]]*]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]+)]\([^)]*\)/g, '$1')
    .replace(/[*_>#-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const figureCommentary = (block: string, figure: CommunityPaperAnswer['figures'][number]) => {
  const text = stripMarkdown(block);
  const escapedLabel = figure.label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const sentencePattern = new RegExp(`[^。！？.!?]*?(?:${escapedLabel}|(?:Fig(?:ure)?\\.?|图)\\s*${figureNumber(figure)})[^。！？.!?]*[。！？.!?]?`, 'i');
  const matched = text.match(sentencePattern)?.[0]?.trim();
  const evidence = (matched || text).slice(0, 150);
  return `我在这里提到 ${displayFigureLabel(figure)}，主要是想让你直接对照这张图看：${evidence}`;
};

const referencedFiguresForBlock = (
  block: string,
  figures: CommunityPaperAnswer['figures'],
  usedFigureIds: Set<string>,
) => {
  const referencedNumbers = new Set<string>();
  for (const match of block.matchAll(figureReferencePattern)) {
    referencedNumbers.add(normalizeFigureNumber(match[1]));
  }
  if (referencedNumbers.size === 0) {
    return [];
  }
  return figures.filter((figure) => {
    if (usedFigureIds.has(figure.id) || !figure.image_url) {
      return false;
    }
    return referencedNumbers.has(figureNumber(figure));
  });
};

const AnswerWithInlineFigures: React.FC<{ paper: CommunityPaperAnswer }> = ({ paper }) => {
  const usedFigureIds = new Set<string>();
  const blocks = paper.answer?.split(/\n{2,}/).filter((block) => block.trim()) || [];

  return (
    <>
      {blocks.map((block, index) => {
        const figures = referencedFiguresForBlock(block, paper.figures, usedFigureIds);
        figures.forEach((figure) => usedFigureIds.add(figure.id));
        return (
          <React.Fragment key={`${paper.paper_id}-block-${index}`}>
            <ReactMarkdown components={markdownComponents}>{block}</ReactMarkdown>
            {figures.map((figure) => (
              <InlineFigureCard
                key={figure.id}
                figure={figure}
                paperTitle={paper.title}
                commentary={figureCommentary(block, figure)}
              />
            ))}
          </React.Fragment>
        );
      })}
    </>
  );
};

const InlineFigureCard: React.FC<{
  figure: CommunityPaperAnswer['figures'][number];
  paperTitle: string;
  commentary: string;
}> = ({ figure, paperTitle, commentary }) => (
  <figure className="my-5 rounded-md border border-blue-100 bg-blue-50/50 px-3 py-3">
    <div className="mb-3 flex items-center justify-between gap-3 text-xs text-blue-700">
      <span className="inline-flex items-center gap-1.5 font-semibold">
        <ImageIcon size={14} />
        {displayFigureLabel(figure)}
      </span>
      <span>第 {figure.page_number} 页</span>
    </div>
    <div className="overflow-hidden rounded-md border border-gray-200 bg-white">
      <img
        src={buildApiUrl(figure.image_url || '')}
        alt={`${figure.label} from ${paperTitle}`}
        className="max-h-[520px] w-full object-contain"
        loading="lazy"
      />
    </div>
    <figcaption className="mt-3 text-sm leading-6 text-gray-700">
      {commentary}
    </figcaption>
  </figure>
);

export default CommunityPage;
