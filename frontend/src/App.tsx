import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useLocation } from 'react-router-dom';
import TaskListPage from './pages/TaskListPage';
import TaskCreatePage from './pages/TaskCreatePage';
import TaskDetailPage from './pages/TaskDetailPage';
import ReadingRoomPage from './pages/ReadingRoomPage';
import TemplatesPage from './pages/TemplatesPage';
import CollectionsPage from './pages/CollectionsPage';
import ResearchCreatePage from './pages/ResearchCreatePage';
import CommunityPage from './pages/CommunityPage';
import SettingsPage from './pages/SettingsPage';
import AuthPage from './pages/AuthPage';
import { AuthProvider, useAuth } from './auth/AuthContext';

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="min-h-screen bg-gray-50 flex items-center justify-center text-gray-500">Loading...</div>;
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <>{children}</>;
};

function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<AuthPage />} />
          <Route path="/" element={<ProtectedRoute><TaskListPage /></ProtectedRoute>} />
          <Route path="/tasks" element={<ProtectedRoute><TaskListPage /></ProtectedRoute>} />
          <Route path="/tasks/create" element={<ProtectedRoute><TaskCreatePage /></ProtectedRoute>} />
          <Route path="/tasks/:id" element={<ProtectedRoute><TaskDetailPage /></ProtectedRoute>} />
          <Route path="/reader/:paperId" element={<ProtectedRoute><ReadingRoomPage /></ProtectedRoute>} />
          <Route path="/templates" element={<ProtectedRoute><TemplatesPage /></ProtectedRoute>} />
          <Route path="/collections" element={<ProtectedRoute><CollectionsPage /></ProtectedRoute>} />
          <Route path="/research" element={<ProtectedRoute><ResearchCreatePage /></ProtectedRoute>} />
          <Route path="/community" element={<ProtectedRoute><CommunityPage /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
          <Route path="/research/create" element={<Navigate to="/research" replace />} />
          <Route path="/research/:id" element={<Navigate to="/research" replace />} />
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
