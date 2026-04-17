import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import TaskListPage from './pages/TaskListPage';
import TaskCreatePage from './pages/TaskCreatePage';
import TaskDetailPage from './pages/TaskDetailPage';
import ReadingRoomPage from './pages/ReadingRoomPage';
import TemplatesPage from './pages/TemplatesPage';
import CollectionsPage from './pages/CollectionsPage';
import ResearchCreatePage from './pages/ResearchCreatePage';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<TaskListPage />} />
        <Route path="/tasks" element={<TaskListPage />} />
        <Route path="/tasks/create" element={<TaskCreatePage />} />
        <Route path="/tasks/:id" element={<TaskDetailPage />} />
        <Route path="/reader/:paperId" element={<ReadingRoomPage />} />
        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/collections" element={<CollectionsPage />} />
        <Route path="/research" element={<ResearchCreatePage />} />
        <Route path="/research/create" element={<Navigate to="/research" replace />} />
        <Route path="/research/:id" element={<Navigate to="/research" replace />} />
      </Routes>
    </Router>
  );
}

export default App;
