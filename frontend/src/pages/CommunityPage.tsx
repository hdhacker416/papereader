import React, { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Loader2, MessageCircle, Search, FileText, Image as ImageIcon, AlertCircle } from 'lucide-react';
import clsx from 'clsx';
import Layout from '../components/Layout';
import { communityApi } from '../api/services';
import { CommunityAnswerResponse, CommunityPaperAnswer } from '../types';

const DEFAULT_QUERY = '对于大模型越狱攻击，最有效的防御思路是什么，如何在安全性和有用性之间取舍？';

const CommunityPage: React.FC = () => {
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [limit, setLimit] = useState(5);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [response, setResponse] = useState<CommunityAnswerResponse | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);

  const selectedPaper = useMemo<CommunityPaperAnswer | null>(() => {
    if (!response?.results.length) {
      return null;
    }
    return response.results[Math.min(selectedIndex, response.results.length - 1)];
  }, [response, selectedIndex]);

  const runSearch = async () => {
    const cleanQuery = query.trim();
    if (!cleanQuery || loading) {
      return;
    }
    setLoading(true);
    setError('');
    setResponse(null);
    setSelectedIndex(0);
    try {
      const result = await communityApi.generateAnswers({
        query: cleanQuery,
        limit,
        max_text_chars: 120000,
        figure_max_pages: 12,
      });
      setResponse(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to generate community answers';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout>
      <div className="h-[calc(100vh-4rem)] min-h-[680px] flex flex-col">
        <div className="shrink-0 border-b border-gray-200 pb-5 mb-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-600 text-white flex items-center justify-center">
              <MessageCircle size={22} />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Community</h1>
              <p className="text-sm text-gray-500 mt-1">Ask a question and let relevant papers answer in first person.</p>
            </div>
          </div>
        </div>

        <div className="flex-1 min-h-0 flex gap-5">
          <aside className="w-[360px] shrink-0 border border-gray-200 bg-white rounded-lg flex flex-col min-h-0">
            <div className="p-4 border-b border-gray-100">
              <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Question
              </label>
              <textarea
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="w-full h-28 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
              />
              <div className="flex items-center gap-3 mt-3">
                <label className="text-sm text-gray-600">Top papers</label>
                <input
                  type="number"
                  min={1}
                  max={8}
                  value={limit}
                  onChange={(event) => setLimit(Math.max(1, Math.min(8, Number(event.target.value) || 1)))}
                  className="w-20 rounded-md border border-gray-300 px-2 py-1.5 text-sm"
                />
                <button
                  type="button"
                  onClick={runSearch}
                  disabled={loading || !query.trim()}
                  className="ml-auto inline-flex items-center gap-2 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
                  Run
                </button>
              </div>
            </div>

            {response && (
              <div className="px-4 py-3 border-b border-gray-100 text-xs text-gray-500">
                {response.results.length} papers · {response.elapsed_sec.toFixed(1)}s · {response.route}
              </div>
            )}

            <div className="flex-1 min-h-0 overflow-y-auto p-2">
              {error && (
                <div className="m-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 flex gap-2">
                  <AlertCircle size={16} className="shrink-0 mt-0.5" />
                  <span>{error}</span>
                </div>
              )}

              {loading && (
                <div className="p-4 text-sm text-gray-500 flex items-center gap-2">
                  <Loader2 size={16} className="animate-spin" />
                  Searching, downloading PDFs, extracting figures, and generating answers...
                </div>
              )}

              {!loading && !response && !error && (
                <div className="p-4 text-sm text-gray-500">
                  Results will appear here after the first run.
                </div>
              )}

              {response?.results.map((paper, index) => (
                <button
                  key={`${paper.conference}-${paper.year}-${paper.paper_id}`}
                  type="button"
                  onClick={() => setSelectedIndex(index)}
                  className={clsx(
                    'w-full text-left rounded-md px-3 py-3 mb-1 border transition-colors',
                    index === selectedIndex
                      ? 'border-blue-200 bg-blue-50'
                      : 'border-transparent hover:bg-gray-50'
                  )}
                >
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 w-6 h-6 rounded bg-gray-100 text-gray-600 text-xs font-semibold flex items-center justify-center shrink-0">
                      {paper.rank}
                    </span>
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-gray-900 line-clamp-2">{paper.title}</div>
                      <div className="mt-1 text-xs text-gray-500">
                        {paper.conference.toUpperCase()} {paper.year}
                        {typeof paper.seconds === 'number' ? ` · ${paper.seconds.toFixed(1)}s` : ''}
                      </div>
                      <div className="mt-1 flex items-center gap-3 text-xs text-gray-500">
                        <span className="inline-flex items-center gap-1">
                          <ImageIcon size={12} />
                          {paper.figure_count}
                        </span>
                        <span className={paper.status === 'ok' ? 'text-green-600' : 'text-red-600'}>
                          {paper.status}
                        </span>
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </aside>

          <section className="flex-1 min-w-0 border border-gray-200 bg-white rounded-lg overflow-hidden flex flex-col">
            {!selectedPaper ? (
              <div className="h-full flex items-center justify-center text-gray-500 text-sm">
                Select or generate a paper answer.
              </div>
            ) : (
              <>
                <div className="shrink-0 border-b border-gray-100 px-6 py-5">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-blue-600 uppercase tracking-wide">
                        {selectedPaper.conference} {selectedPaper.year}
                      </div>
                      <h2 className="mt-1 text-xl font-semibold text-gray-900 leading-snug">{selectedPaper.title}</h2>
                      <div className="mt-2 text-xs text-gray-500">
                        {selectedPaper.authors.slice(0, 5).join(', ')}
                        {selectedPaper.authors.length > 5 ? ' et al.' : ''}
                      </div>
                    </div>
                    {selectedPaper.source_url && (
                      <a
                        href={selectedPaper.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="shrink-0 inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                      >
                        <FileText size={16} />
                        Source
                      </a>
                    )}
                  </div>
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto px-6 py-5">
                  {selectedPaper.error && (
                    <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                      {selectedPaper.error}
                    </div>
                  )}

                  {selectedPaper.answer ? (
                    <div className="max-w-4xl text-[15px] leading-7 text-gray-800">
                      <ReactMarkdown
                        components={{
                          p: ({ children }) => <p className="mb-4">{children}</p>,
                          strong: ({ children }) => <strong className="font-semibold text-gray-950">{children}</strong>,
                          ul: ({ children }) => <ul className="mb-4 list-disc pl-5 space-y-1">{children}</ul>,
                          ol: ({ children }) => <ol className="mb-4 list-decimal pl-5 space-y-1">{children}</ol>,
                        }}
                      >
                        {selectedPaper.answer}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <div className="text-sm text-gray-500">No answer generated.</div>
                  )}

                  {selectedPaper.figures.length > 0 && (
                    <div className="mt-8 pt-5 border-t border-gray-100">
                      <h3 className="text-sm font-semibold text-gray-900 mb-3">Referenced Figures</h3>
                      <div className="space-y-3">
                        {selectedPaper.figures.map((figure) => (
                          <div key={figure.id} className="rounded-md border border-gray-200 px-3 py-3">
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
              </>
            )}
          </section>
        </div>
      </div>
    </Layout>
  );
};

export default CommunityPage;
