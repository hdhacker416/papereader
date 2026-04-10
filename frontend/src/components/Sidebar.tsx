import React, { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { LayoutDashboard, FileText, FolderOpen, BookOpen, ChevronRight, ChevronDown, Folder, FlaskConical } from 'lucide-react';
import clsx from 'clsx';
import { tasksApi, collectionsApi } from '../api/services';
import { Task, Paper, Collection } from '../types';

interface SidebarLocation {
    pathname: string;
}

const SidebarCollectionNode: React.FC<{
    collection: Collection;
    allCollections: Collection[];
    level: number;
    navigate: (path: string) => void;
    location: SidebarLocation;
}> = ({ collection, allCollections, level, navigate, location }) => {
    const [expanded, setExpanded] = useState(false);
    const [papers, setPapers] = useState<Paper[]>([]);
    const [loading, setLoading] = useState(false);
    const [loaded, setLoaded] = useState(false);

    const children = allCollections.filter(c => c.parent_id === collection.id);
    const hasChildren = children.length > 0;

    const toggleExpand = async (e: React.MouseEvent) => {
        e.stopPropagation();
        setExpanded(!expanded);
        if (!loaded && !expanded) {
            setLoading(true);
            try {
                const data = await collectionsApi.getPapers(collection.id);
                setPapers(data);
                setLoaded(true);
            } catch (error) {
                console.error("Failed to load papers", error);
            } finally {
                setLoading(false);
            }
        }
    };

    return (
        <div className="select-none">
            <div 
                className={clsx(
                    "flex items-center gap-2 py-1 px-2 hover:bg-gray-100 rounded cursor-pointer text-sm text-gray-700",
                    level > 0 && "ml-3"
                )}
                onClick={toggleExpand}
            >
                <div className="text-gray-400 w-4 h-4 flex items-center justify-center shrink-0">
                    {(hasChildren || papers.length > 0 || !loaded) ? (
                        expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />
                    ) : <div className="w-3" />}
                </div>
                
                <Folder className={clsx("shrink-0", expanded ? "text-blue-500" : "text-gray-400")} size={14} />
                <span className="truncate">{collection.name}</span>
            </div>

            {expanded && (
                <div className="ml-2 border-l border-gray-100 pl-1">
                    {children.map(child => (
                        <SidebarCollectionNode 
                            key={child.id} 
                            collection={child} 
                            allCollections={allCollections}
                            level={level + 1}
                            navigate={navigate}
                            location={location}
                        />
                    ))}
                    
                    {loading && <div className="text-xs text-gray-400 py-1 ml-4">Loading...</div>}
                    
                    {papers.map(paper => (
                        <div 
                            key={paper.id}
                            onClick={(e) => {
                                e.stopPropagation();
                                navigate(`/reader/${paper.id}`);
                            }}
                            className={clsx(
                                "flex items-center gap-2 py-1 px-2 ml-4 rounded cursor-pointer text-xs truncate transition-colors",
                                location.pathname === `/reader/${paper.id}` 
                                    ? "bg-blue-100 text-blue-700 font-medium" 
                                    : "text-gray-500 hover:bg-gray-100 hover:text-gray-900"
                            )}
                            title={paper.title}
                        >
                            <FileText size={12} className="shrink-0" />
                            <span className="truncate">{paper.title}</span>
                        </div>
                    ))}
                    
                    {!loading && papers.length === 0 && children.length === 0 && (
                        <div className="text-xs text-gray-400 py-1 ml-6">Empty</div>
                    )}
                </div>
            )}
        </div>
    );
};

const Sidebar: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  
  // Library State
  const [isLibraryExpanded, setIsLibraryExpanded] = useState(false);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [expandedTaskIds, setExpandedTaskIds] = useState<Set<string>>(new Set());
  const [taskPapers, setTaskPapers] = useState<Record<string, Paper[]>>({});
  const [loadingTasks, setLoadingTasks] = useState(false);
  const [loadingCollections, setLoadingCollections] = useState(false);

  // Load data when Library is expanded
  useEffect(() => {
    if (isLibraryExpanded) {
      if (tasks.length === 0) {
        const loadTasks = async () => {
          setLoadingTasks(true);
          try {
            const data = await tasksApi.list();
            setTasks(data);
          } catch (e) { console.error(e); } finally { setLoadingTasks(false); }
        };
        loadTasks();
      }
      if (collections.length === 0) {
        const loadCollections = async () => {
            setLoadingCollections(true);
            try {
                const data = await collectionsApi.list();
                setCollections(data);
            } catch (e) { console.error(e); } finally { setLoadingCollections(false); }
        };
        loadCollections();
      }
    }
  }, [collections.length, isLibraryExpanded, tasks.length]);

  const toggleTaskExpand = async (taskId: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    const newSet = new Set(expandedTaskIds);
    if (newSet.has(taskId)) {
      newSet.delete(taskId);
    } else {
      newSet.add(taskId);
      // Fetch papers if not loaded
      if (!taskPapers[taskId]) {
        try {
          const papers = await tasksApi.getPapers(taskId);
          setTaskPapers(prev => ({...prev, [taskId]: papers}));
        } catch (e) {
          console.error(e);
        }
      }
    }
    setExpandedTaskIds(newSet);
  };

  const navItems = [
    { path: '/tasks', label: 'Tasks', icon: LayoutDashboard },
    { path: '/research', label: 'Research', icon: FlaskConical },
    { path: '/collections', label: 'Collections', icon: FolderOpen },
    { path: '/templates', label: 'Templates', icon: FileText },
  ];

  return (
    <div className="w-64 bg-white border-r border-gray-200 flex flex-col shrink-0 h-full">
      <div className="p-6 border-b border-gray-100 shrink-0">
        <h1 className="text-xl font-bold text-blue-600 flex items-center gap-2">
          <span className="bg-blue-600 text-white p-1 rounded">PR</span>
          PaperReader
        </h1>
      </div>
      <nav className="p-4 space-y-1 flex-1 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = location.pathname === item.path || (item.path !== '/' && location.pathname.startsWith(item.path));
          // Special handling for Tasks root redirect
          const isTasksActive = item.path === '/tasks' && (location.pathname === '/' || location.pathname.startsWith('/tasks'));
          const active = isActive || isTasksActive;

          return (
            <Link
              key={item.path}
              to={item.path}
              className={clsx(
                "flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors",
                active 
                  ? "bg-blue-50 text-blue-700" 
                  : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
              )}
            >
              <Icon size={20} />
              {item.label}
            </Link>
          );
        })}

        {/* Library Section */}
        <div className="pt-2">
            <button
                onClick={() => setIsLibraryExpanded(!isLibraryExpanded)}
                className={clsx(
                    "w-full flex items-center justify-between px-4 py-3 rounded-lg text-sm font-medium transition-colors",
                    isLibraryExpanded ? "text-blue-700 bg-blue-50" : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                )}
            >
                <div className="flex items-center gap-3">
                    <BookOpen size={20} />
                    Library
                </div>
                {isLibraryExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            </button>

            {isLibraryExpanded && (
                <div className="mt-1 ml-4 space-y-1 border-l-2 border-gray-100 pl-2 overflow-hidden">
                    {/* Tasks Section */}
                    <div className="mb-4">
                        <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 px-2">Tasks</div>
                        {loadingTasks && <div className="text-xs text-gray-400 py-1 px-2">Loading tasks...</div>}
                        {!loadingTasks && tasks.length === 0 && <div className="text-xs text-gray-400 py-1 px-2">No tasks found</div>}
                        
                        {tasks.map(task => {
                            const isExpanded = expandedTaskIds.has(task.id);
                            const papers = taskPapers[task.id] || [];
                            
                            return (
                                <div key={task.id} className="py-1">
                                    <button
                                        onClick={(e) => toggleTaskExpand(task.id, e)}
                                        className="flex items-center gap-2 w-full text-left text-sm text-gray-700 hover:text-blue-600 px-2"
                                    >
                                        {isExpanded ? <ChevronDown size={14} className="shrink-0" /> : <ChevronRight size={14} className="shrink-0" />}
                                        <span className="truncate">{task.name}</span>
                                    </button>
                                    
                                    {isExpanded && (
                                        <div className="ml-5 mt-1 space-y-1">
                                            {papers.length === 0 ? (
                                                <div className="text-xs text-gray-400 pl-2">No papers</div>
                                            ) : (
                                                papers.map(paper => (
                                                    <button
                                                        key={paper.id}
                                                        onClick={() => navigate(`/reader/${paper.id}`)}
                                                        className={clsx(
                                                            "block w-full text-left text-xs py-1 px-2 rounded truncate transition-colors",
                                                            location.pathname === `/reader/${paper.id}` 
                                                                ? "bg-blue-100 text-blue-700 font-medium" 
                                                                : "text-gray-500 hover:bg-gray-100 hover:text-gray-900"
                                                        )}
                                                        title={paper.title}
                                                    >
                                                        {paper.title}
                                                    </button>
                                                ))
                                            )}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>

                    {/* Collections Section */}
                    <div>
                        <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 px-2">Collections</div>
                        {loadingCollections && <div className="text-xs text-gray-400 py-1 px-2">Loading collections...</div>}
                        {!loadingCollections && collections.length === 0 && <div className="text-xs text-gray-400 py-1 px-2">No collections found</div>}
                        
                        {collections.filter(c => !c.parent_id).map(collection => (
                            <SidebarCollectionNode
                                key={collection.id}
                                collection={collection}
                                allCollections={collections}
                                level={0}
                                navigate={navigate}
                                location={location}
                            />
                        ))}
                    </div>
                </div>
            )}
        </div>
      </nav>
    </div>
  );
};

export default Sidebar;
