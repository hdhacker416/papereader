import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import TaskListPage from './pages/TaskListPage';
import TaskCreatePage from './pages/TaskCreatePage';
import TaskDetailPage from './pages/TaskDetailPage';
import ReadingRoomPage from './pages/ReadingRoomPage';
import TemplatesPage from './pages/TemplatesPage';
import CollectionsPage from './pages/CollectionsPage';
import ResearchJobsPage from './pages/ResearchJobsPage';
import ResearchCreatePage from './pages/ResearchCreatePage';
import ResearchDetailPage from './pages/ResearchDetailPage';

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
        <Route path="/research" element={<ResearchJobsPage />} />
        <Route path="/research/create" element={<ResearchCreatePage />} />
        <Route path="/research/:id" element={<ResearchDetailPage />} />
      </Routes>
    </Router>
  );
}

export default App;
