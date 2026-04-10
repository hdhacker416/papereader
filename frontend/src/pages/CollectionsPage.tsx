import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import ReReadModal from '../components/ReReadModal';
import { collectionsApi } from '../api/services';
import { Collection, Paper } from '../types';
import { Plus, Folder, Trash2, ChevronRight, ChevronDown, FileText, RefreshCw } from 'lucide-react';
import clsx from 'clsx';

// Tree Node Component
const CollectionNode: React.FC<{
  collection: Collection;
  level: number;
  allCollections: Collection[];
  onDelete: (id: string) => void;
  onCreateSub: (parentId: string) => void;
  onReRead: (id: string) => void;
}> = ({ collection, level, allCollections, onDelete, onCreateSub, onReRead }) => {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loadingPapers, setLoadingPapers] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const children = allCollections.filter(c => c.parent_id === collection.id);
  const hasChildren = children.length > 0;

  const toggleExpand = async () => {
    setExpanded(!expanded);
    if (!loaded && !expanded) {
      setLoadingPapers(true);
      try {
        const data = await collectionsApi.getPapers(collection.id);
        setPapers(data);
        setLoaded(true);
      } catch (error) {
        console.error("Failed to load papers", error);
      } finally {
        setLoadingPapers(false);
      }
    }
  };

  return (
    <div className="select-none">
      <div 
        className={clsx(
          "flex items-center gap-2 p-2 hover:bg-gray-50 rounded cursor-pointer group",
          level > 0 && "ml-4"
        )}
        onClick={toggleExpand}
      >
        <div className="text-gray-400 w-4 h-4 flex items-center justify-center">
          {(hasChildren || papers.length > 0 || !loaded) ? (
            expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
          ) : null}
        </div>
        
        <Folder className="text-blue-500" size={18} />
        <span className="font-medium text-gray-900 flex-1">{collection.name}</span>
        
        <div className="opacity-0 group-hover:opacity-100 flex gap-2">
            <button 
                onClick={(e) => { e.stopPropagation(); onReRead(collection.id); }}
                className="p-1 text-gray-400 hover:text-indigo-500"
                title="Re-read Collection"
            >
                <RefreshCw size={14} />
            </button>
            <button 
                onClick={(e) => { e.stopPropagation(); onCreateSub(collection.id); }}
                className="p-1 text-gray-400 hover:text-blue-500"
                title="Create Sub-collection"
            >
                <Plus size={14} />
            </button>
            <button 
                onClick={(e) => { e.stopPropagation(); onDelete(collection.id); }}
                className="p-1 text-gray-400 hover:text-red-500"
                title="Delete"
            >
                <Trash2 size={14} />
            </button>
        </div>
      </div>

      {expanded && (
        <div className="ml-2 border-l border-gray-100 pl-2">
          {/* Sub-collections */}
          {children.map(child => (
            <CollectionNode 
                key={child.id} 
                collection={child} 
                level={level + 1} 
                allCollections={allCollections}
                onDelete={onDelete}
                onCreateSub={onCreateSub}
                onReRead={onReRead}
            />
          ))}
          
          {/* Papers */}
          {loadingPapers && <div className="text-xs text-gray-400 p-2 ml-6">Loading papers...</div>}
          {papers.map(paper => (
              <div 
                  key={paper.id} 
                  className="flex items-center gap-2 p-2 ml-4 hover:bg-gray-100 rounded text-sm text-gray-700 cursor-pointer"
                  onClick={() => navigate(`/reader/${paper.id}`)}
              >
                  <FileText size={14} className="text-blue-500" />
                  <span className="truncate hover:text-blue-600 hover:underline">{paper.title}</span>
              </div>
          ))}
          
          {!loadingPapers && papers.length === 0 && children.length === 0 && (
              <div className="text-xs text-gray-400 p-2 ml-6">Empty</div>
          )}
        </div>
      )}
    </div>
  );
};

const CollectionsPage: React.FC = () => {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [targetParentId, setTargetParentId] = useState<string | undefined>(undefined);
  const [reReadTargetId, setReReadTargetId] = useState<string | null>(null);

  const fetchCollections = async () => {
    try {
      const data = await collectionsApi.list();
      setCollections(data);
    } catch (error) {
      console.error('Failed to fetch collections:', error);
    }
  };

  useEffect(() => {
    fetchCollections();
  }, []);

  const handleCreate = async () => {
    try {
      await collectionsApi.create(newName, targetParentId);
      setNewName('');
      setTargetParentId(undefined);
      setShowCreate(false);
      fetchCollections();
    } catch (error) {
      console.error('Failed to create collection:', error);
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('Are you sure you want to delete this collection?')) return;
    try {
      await collectionsApi.delete(id);
      fetchCollections();
    } catch (error) {
      console.error('Failed to delete collection:', error);
    }
  };

  const handleReReadClick = (id: string) => {
    setReReadTargetId(id);
  };

  const handleReReadConfirm = async (templateId: string, modelName: string) => {
    if (!reReadTargetId) return;
    try {
      await collectionsApi.reRead(reReadTargetId, templateId, modelName);
      // Optional: show toast or something
    } catch (error) {
      console.error('Failed to reread collection:', error);
    }
  };

  const openCreate = (parentId?: string) => {
      setTargetParentId(parentId);
      setNewName('');
      setShowCreate(true);
  };

  // Roots are collections with no parent
  const rootCollections = collections.filter(c => !c.parent_id);

  return (
    <Layout>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Collections</h1>
        <button
          onClick={() => openCreate()}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus size={20} /> New Root Collection
        </button>
      </div>

      {showCreate && (
          <div className="bg-white p-4 rounded-xl border border-blue-200 shadow-sm mb-6 flex gap-3 items-center animate-in fade-in slide-in-from-top-2">
              <span className="text-sm font-medium text-gray-500 whitespace-nowrap">
                  {targetParentId ? 'New Sub-collection:' : 'New Root Collection:'}
              </span>
              <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="flex-1 px-3 py-1.5 border border-gray-300 rounded-lg text-sm"
                  placeholder="Collection Name"
                  autoFocus
                  onKeyDown={(e) => e.key === 'Enter' && newName && handleCreate()}
              />
              <button
                  onClick={handleCreate}
                  disabled={!newName}
                  className="px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm"
              >
                  Create
              </button>
              <button
                  onClick={() => setShowCreate(false)}
                  className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 text-sm"
              >
                  Cancel
              </button>
          </div>
      )}

      {/* Root Collections */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {rootCollections.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
                No collections yet. Create one to get started.
            </div>
        ) : (
            rootCollections.map(collection => (
                <CollectionNode 
                    key={collection.id} 
                    collection={collection} 
                    level={0} 
                    allCollections={collections}
                    onDelete={handleDelete}
                    onCreateSub={(parentId) => openCreate(parentId)}
                    onReRead={handleReReadClick}
                />
            ))
        )}
      </div>

      <ReReadModal
        isOpen={!!reReadTargetId}
        onClose={() => setReReadTargetId(null)}
        onConfirm={handleReReadConfirm}
        title="Re-read Collection"
      />
    </Layout>
  );
};

export default CollectionsPage;
