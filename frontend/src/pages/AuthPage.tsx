import React, { useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { BookOpen, Loader2, LogIn, UserPlus } from 'lucide-react';
import clsx from 'clsx';
import { useAuth } from '../auth/AuthContext';

const AuthPage: React.FC = () => {
  const location = useLocation();
  const { user, loading, login, register } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center text-gray-500">
        <Loader2 size={22} className="animate-spin mr-2" />
        Loading...
      </div>
    );
  }

  if (user) {
    const redirectTo = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname || '/tasks';
    return <Navigate to={redirectTo} replace />;
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      if (mode === 'register') {
        await register(email, password, name);
      } else {
        await login(email, password);
      }
    } catch (err) {
      const detail = typeof err === 'object' && err && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || 'Authentication failed.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto w-12 h-12 rounded-xl bg-blue-600 text-white flex items-center justify-center">
            <BookOpen size={26} />
          </div>
          <h1 className="mt-4 text-2xl font-bold text-gray-900">PaperReader</h1>
          <p className="mt-2 text-sm text-gray-500">Sign in to your cloud paper workspace.</p>
        </div>

        <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-6">
          <div className="flex rounded-lg bg-gray-100 p-1 mb-6">
            <button
              type="button"
              onClick={() => setMode('login')}
              className={clsx('flex-1 px-3 py-2 rounded-md text-sm font-medium', mode === 'login' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600')}
            >
              Login
            </button>
            <button
              type="button"
              onClick={() => setMode('register')}
              className={clsx('flex-1 px-3 py-2 rounded-md text-sm font-medium', mode === 'register' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600')}
            >
              Register
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === 'register' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  className="w-full h-11 px-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Your name"
                />
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="w-full h-11 px-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="you@example.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full h-11 px-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="At least 8 characters"
              />
            </div>

            {error && (
              <div className="border border-red-200 bg-red-50 text-red-700 rounded-lg px-3 py-2 text-sm">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full h-11 flex items-center justify-center gap-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {submitting ? <Loader2 size={18} className="animate-spin" /> : mode === 'register' ? <UserPlus size={18} /> : <LogIn size={18} />}
              {mode === 'register' ? 'Create account' : 'Login'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default AuthPage;
