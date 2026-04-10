import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Trash2, ChevronDown, ChevronRight, CheckSquare, Square } from 'lucide-react';
import { format, isToday, isYesterday } from 'date-fns';
import Layout from '../components/Layout';
import TaskCard from '../components/TaskCard';
import { tasksApi } from '../api/services';
import { Task } from '../types';

const TaskListPage: React.FC = () => {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTasks, setSelectedTasks] = useState<Set<string>>(new Set());
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  const fetchTasks = async () => {
    try {
      const data = await tasksApi.list();
      setTasks(data);
    } catch (error) {
      console.error('Failed to fetch tasks:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
    const interval = setInterval(fetchTasks, 2000); // Poll for updates every 2s
    return () => clearInterval(interval);
  }, []);

  const handleDeleteTask = async (id: string) => {
    try {
        await tasksApi.delete(id);
        fetchTasks();
    } catch (error) {
        console.error('Failed to delete task:', error);
        alert('Failed to delete task');
    }
  };

  const handleBatchDelete = async () => {
    if (selectedTasks.size === 0) return;
    if (!window.confirm(`Are you sure you want to delete ${selectedTasks.size} tasks?`)) return;
    
    try {
        await tasksApi.batchDelete(Array.from(selectedTasks));
        setSelectedTasks(new Set());
        fetchTasks();
    } catch (error) {
        console.error('Failed to delete tasks:', error);
        alert('Failed to delete tasks');
    }
  };

  const toggleSelection = (id: string) => {
    const newSet = new Set(selectedTasks);
    if (newSet.has(id)) {
        newSet.delete(id);
    } else {
        newSet.add(id);
    }
    setSelectedTasks(newSet);
  };

  const toggleGroupCollapse = (date: string) => {
    const newSet = new Set(collapsedGroups);
    if (newSet.has(date)) {
        newSet.delete(date);
    } else {
        newSet.add(date);
    }
    setCollapsedGroups(newSet);
  };

  const toggleGroupSelection = (date: string, groupTasks: Task[]) => {
    const allSelected = groupTasks.every(t => selectedTasks.has(t.id));
    const newSet = new Set(selectedTasks);
    
    if (allSelected) {
        groupTasks.forEach(t => newSet.delete(t.id));
    } else {
        groupTasks.forEach(t => newSet.add(t.id));
    }
    setSelectedTasks(newSet);
  };

  // Group tasks by date
  const groupedTasks = tasks.reduce((groups, task) => {
    const date = new Date(task.created_at);
    let dateStr = format(date, 'yyyy-MM-dd');
    if (isToday(date)) dateStr = 'Today';
    else if (isYesterday(date)) dateStr = 'Yesterday';
    
    if (!groups[dateStr]) {
        groups[dateStr] = [];
    }
    groups[dateStr].push(task);
    return groups;
  }, {} as Record<string, Task[]>);

  // Sort dates (Today first)
  const sortedDates = Object.keys(groupedTasks).sort((a, b) => {
      if (a === 'Today') return -1;
      if (b === 'Today') return 1;
      if (a === 'Yesterday') return -1;
      if (b === 'Yesterday') return 1;
      return b.localeCompare(a);
  });

  return (
    <Layout>
      <div className="flex justify-between items-center mb-8 sticky top-0 bg-gray-50 z-20 py-4 border-b border-gray-200/50">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Tasks</h1>
          <p className="text-gray-500 mt-1">Manage your paper reading tasks</p>
        </div>
        <div className="flex gap-3">
            {selectedTasks.size > 0 && (
                <button
                    onClick={handleBatchDelete}
                    className="flex items-center gap-2 bg-red-50 text-red-600 px-4 py-2 rounded-lg hover:bg-red-100 transition-colors border border-red-200"
                >
                    <Trash2 size={20} />
                    Delete ({selectedTasks.size})
                </button>
            )}
            <button
            onClick={() => navigate('/tasks/create')}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors shadow-sm"
            >
            <Plus size={20} />
            New Task
            </button>
        </div>
      </div>

      {loading && tasks.length === 0 ? (
        <div className="text-center py-12 text-gray-500">Loading tasks...</div>
      ) : tasks.length === 0 ? (
        <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-xl">
          <p className="text-gray-500 mb-4">No tasks found. Create one to get started!</p>
          <button
            onClick={() => navigate('/tasks/create')}
            className="text-blue-600 font-medium hover:underline"
          >
            Create your first task
          </button>
        </div>
      ) : (
        <div className="space-y-8 pb-12">
            {sortedDates.map(date => {
                const groupTasks = groupedTasks[date];
                const isCollapsed = collapsedGroups.has(date);
                const allSelected = groupTasks.every(t => selectedTasks.has(t.id));
                const someSelected = groupTasks.some(t => selectedTasks.has(t.id));

                return (
                    <div key={date} className="animate-in fade-in duration-300">
                        <div className="flex items-center gap-4 mb-4 group">
                            <button 
                                onClick={() => toggleGroupCollapse(date)}
                                className="flex items-center gap-2 text-2xl font-bold text-gray-800 hover:text-blue-600 transition-colors"
                            >
                                {isCollapsed ? <ChevronRight size={24} /> : <ChevronDown size={24} />}
                                {date}
                                <span className="text-sm font-normal text-gray-400 ml-2 bg-gray-100 px-2 py-0.5 rounded-full">
                                    {groupTasks.length}
                                </span>
                            </button>
                            
                            <div className="h-px bg-gray-200 flex-1 opacity-50"></div>
                            
                            <button
                                onClick={() => toggleGroupSelection(date, groupTasks)}
                                className="p-2 text-gray-400 hover:text-blue-600 opacity-0 group-hover:opacity-100 transition-opacity"
                                title="Select All in Group"
                            >
                                {allSelected ? <CheckSquare size={20} /> : (someSelected ? <div className="relative"><Square size={20} /><div className="absolute inset-0 flex items-center justify-center"><div className="w-2 h-2 bg-blue-600 rounded-sm"></div></div></div> : <Square size={20} />)}
                            </button>
                        </div>

                        {!isCollapsed && (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                {groupTasks.map((task) => (
                                    <TaskCard 
                                        key={task.id} 
                                        task={task} 
                                        onClick={() => navigate(`/tasks/${task.id}`)}
                                        selected={selectedTasks.has(task.id)}
                                        onSelect={() => toggleSelection(task.id)}
                                        onDelete={() => handleDeleteTask(task.id)}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
      )}
    </Layout>
  );
};

export default TaskListPage;
