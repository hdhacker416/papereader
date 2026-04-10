import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, FlaskConical, ArrowRight } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import Layout from '../components/Layout';
import { researchApi } from '../api/services';
import { ResearchJob } from '../types';
import clsx from 'clsx';

const statusStyles: Record<string, string> = {
  created: 'bg-gray-100 text-gray-700',
  running: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
};

const ResearchJobsPage: React.FC = () => {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState<ResearchJob[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchJobs = async () => {
    try {
      const data = await researchApi.listJobs();
      setJobs(data);
    } catch (error) {
      console.error('Failed to fetch research jobs:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <Layout>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Deep Research</h1>
          <p className="text-gray-500 mt-1">Run conference-scoped research jobs before sending the best papers into the reading pipeline.</p>
        </div>
        <button
          onClick={() => navigate('/research/create')}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors shadow-sm"
        >
          <Plus size={18} />
          New Research
        </button>
      </div>

      {loading && jobs.length === 0 ? (
        <div className="text-center py-12 text-gray-500">Loading research jobs...</div>
      ) : jobs.length === 0 ? (
        <div className="bg-white border border-dashed border-gray-300 rounded-2xl py-16 px-8 text-center">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-blue-50 text-blue-600 mb-4">
            <FlaskConical size={24} />
          </div>
          <h2 className="text-lg font-semibold text-gray-900">No research jobs yet</h2>
          <p className="text-gray-500 mt-2 mb-6">Start with a conference slice and a question such as new large language model safety directions.</p>
          <button
            onClick={() => navigate('/research/create')}
            className="inline-flex items-center gap-2 text-blue-600 font-medium hover:text-blue-700"
          >
            Create your first research job
            <ArrowRight size={16} />
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {jobs.map((job) => (
            <button
              key={job.id}
              onClick={() => navigate(`/research/${job.id}`)}
              className="w-full text-left bg-white border border-gray-200 rounded-2xl p-6 hover:border-blue-300 hover:shadow-sm transition-all"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-3 mb-3">
                    <span className={clsx('px-2.5 py-1 rounded-full text-xs font-medium capitalize', statusStyles[job.status] || 'bg-gray-100 text-gray-700')}>
                      {job.status}
                    </span>
                    <span className="text-xs text-gray-400 capitalize">{job.stage.replace(/_/g, ' ')}</span>
                    <span className="text-xs text-gray-400">{formatDistanceToNow(new Date(job.created_at), { addSuffix: true })}</span>
                  </div>
                  <h2 className="text-lg font-semibold text-gray-900 truncate">{job.query}</h2>
                  <p className="text-sm text-gray-500 mt-2">
                    Conferences: {job.selected_conferences.join(', ')} · Candidates: {job.candidate_count}
                  </p>
                  {job.summary && (
                    <p className="text-sm text-gray-600 mt-4 line-clamp-2">{job.summary}</p>
                  )}
                </div>
                <div className="w-28 shrink-0">
                  <div className="text-right text-sm font-medium text-gray-700 mb-2">{job.progress}%</div>
                  <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div className="h-full bg-blue-600 rounded-full transition-all" style={{ width: `${job.progress}%` }} />
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </Layout>
  );
};

export default ResearchJobsPage;
