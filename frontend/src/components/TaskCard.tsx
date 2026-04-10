import React from 'react';
import { Task } from '../types';
import { format } from 'date-fns';
import { Clock, File, Trash2, CheckSquare, Square } from 'lucide-react';
import clsx from 'clsx';

interface TaskCardProps {
  task: Task;
  onClick: () => void;
  selected?: boolean;
  onSelect?: (selected: boolean) => void;
  onDelete?: () => void;
}

const TaskCard: React.FC<TaskCardProps> = ({ task, onClick, selected, onSelect, onDelete }) => {
  const stats = task.statistics || { total: 0, done: 0, failed: 0, skipped: 0, queued: 0, processing: 0 };
  
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return 'bg-green-100 text-green-800';
      case 'paused': return 'bg-yellow-100 text-yellow-800';
      case 'completed': return 'bg-blue-100 text-blue-800';
      case 'failed': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const handleSelect = (e: React.MouseEvent) => {
    e.stopPropagation();
    onSelect?.(!selected);
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (window.confirm('Are you sure you want to delete this task?')) {
        onDelete?.();
    }
  };

  return (
    <div 
      className={clsx(
        "bg-white rounded-xl border shadow-sm hover:shadow-md transition-all cursor-pointer p-5 relative group",
        selected ? "border-blue-500 ring-1 ring-blue-500" : "border-gray-200"
      )}
      onClick={onClick}
    >
      {/* Selection Checkbox (Visible on hover or selected) */}
      {(onSelect || selected) && (
        <div 
            className={clsx(
                "absolute top-4 right-4 z-10 p-1 rounded hover:bg-gray-100 transition-opacity",
                selected ? "opacity-100 text-blue-600" : "opacity-0 group-hover:opacity-100 text-gray-400"
            )}
            onClick={handleSelect}
        >
            {selected ? <CheckSquare size={20} /> : <Square size={20} />}
        </div>
      )}

      {/* Delete Button (Visible on hover) */}
      {onDelete && (
          <div 
              className="absolute bottom-4 right-4 z-10 opacity-0 group-hover:opacity-100 transition-opacity"
              onClick={handleDelete}
          >
              <button className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors" title="Delete Task">
                  <Trash2 size={18} />
              </button>
          </div>
      )}

      <div className="flex justify-between items-start mb-4 pr-8">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 line-clamp-1" title={task.name}>{task.name}</h3>
          <p className="text-sm text-gray-500 mt-1 line-clamp-2 min-h-[2.5em]">{task.description || "No description"}</p>
        </div>
        <span className={clsx("px-2.5 py-0.5 rounded-full text-xs font-medium capitalize shrink-0 ml-2", getStatusColor(task.status))}>
          {task.status}
        </span>
      </div>

      <div className="flex items-center gap-4 text-sm text-gray-600 mb-4">
        <div className="flex items-center gap-1.5">
          <Clock size={16} />
          {format(new Date(task.created_at), 'MMM d, yyyy')}
        </div>
        <div className="flex items-center gap-1.5">
          <File size={16} />
          {stats.total} papers
        </div>
        {task.model_name && (
            <div className="flex items-center gap-1.5 text-xs bg-gray-50 px-2 py-0.5 rounded text-gray-500">
                Model: {task.model_name.replace('gemini-3-', '').replace('-preview', '')}
            </div>
        )}
      </div>

      {/* Progress Bar */}
      <div className="space-y-2">
        <div className="flex justify-between text-xs text-gray-500">
          <span>Progress</span>
          <span>{Math.round((stats.done / (stats.total || 1)) * 100)}%</span>
        </div>
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden flex">
          <div style={{ width: `${(stats.done / (stats.total || 1)) * 100}%` }} className="bg-green-500 h-full" />
          <div style={{ width: `${(stats.failed / (stats.total || 1)) * 100}%` }} className="bg-red-500 h-full" />
          <div style={{ width: `${(stats.processing / (stats.total || 1)) * 100}%` }} className="bg-blue-500 h-full animate-pulse" />
        </div>
        <div className="flex gap-3 text-xs text-gray-500 mt-2">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500"></span> {stats.done} Done</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-500"></span> {stats.processing} Proc</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500"></span> {stats.failed} Fail</span>
        </div>
      </div>
    </div>
  );
};

export default TaskCard;
