import React, { useEffect, useState } from 'react';
import Layout from '../components/Layout';
import { templatesApi } from '../api/services';
import { Template } from '../types';
import { Plus, Trash2, Check, Star } from 'lucide-react';
import clsx from 'clsx';

const TemplatesPage: React.FC = () => {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [newName, setNewName] = useState('');
  const [newContent, setNewContent] = useState<string[]>(['']);

  const fetchTemplates = async () => {
    try {
      const data = await templatesApi.list();
      setTemplates(data);
    } catch (error) {
      console.error('Failed to fetch templates:', error);
    }
  };

  useEffect(() => {
    fetchTemplates();
  }, []);

  const handleCreate = async () => {
    try {
      const validContent = newContent.filter(c => c.trim());
      if (validContent.length === 0) return;
      
      await templatesApi.create({ name: newName, content: validContent });
      // Reset form but keep it open or close? User said "Delete all popups", so inline form is better.
      // We'll keep the form expanded or collapse it? Let's just reset fields.
      setNewName('');
      setNewContent(['']);
      fetchTemplates();
      // Optional: hide form
      setShowModal(false); 
    } catch (error) {
      console.error('Failed to create template:', error);
    }
  };

  const handleDelete = async (id: string) => {
    // Direct delete without confirmation
    try {
      await templatesApi.delete(id);
      fetchTemplates();
    } catch (error) {
      console.error('Failed to delete template:', error);
    }
  };

  const handleSetDefault = async (id: string) => {
    try {
      await templatesApi.setDefault(id);
      fetchTemplates();
    } catch (error) {
      console.error('Failed to set default template:', error);
    }
  };

  const addStep = () => {
    setNewContent([...newContent, '']);
  };

  const updateStep = (index: number, value: string) => {
    const updated = [...newContent];
    updated[index] = value;
    setNewContent(updated);
  };

  const removeStep = (index: number) => {
    if (newContent.length === 1) return;
    const updated = newContent.filter((_, i) => i !== index);
    setNewContent(updated);
  };

  return (
    <Layout>
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Templates</h1>
        <button
          onClick={() => setShowModal(!showModal)}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
        >
          {showModal ? 'Cancel' : <><Plus size={20} /> New Template</>}
        </button>
      </div>

      {showModal && (
        <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm mb-8 animate-in fade-in slide-in-from-top-4">
          <h2 className="text-xl font-bold mb-4">Create Template</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                placeholder="Template Name"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Prompts (Multi-turn)</label>
              <div className="space-y-3">
                  {newContent.map((step, idx) => (
                      <div key={idx} className="relative">
                          <div className="flex justify-between items-center mb-1">
                              <span className="text-xs font-medium text-gray-500">Step {idx + 1}</span>
                              {newContent.length > 1 && (
                                  <button 
                                      onClick={() => removeStep(idx)}
                                      className="text-red-500 hover:text-red-700 text-xs"
                                  >
                                      Remove
                                  </button>
                              )}
                          </div>
                          <textarea
                            value={step}
                            onChange={(e) => updateStep(idx, e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg h-24 font-mono text-sm"
                            placeholder={`Enter prompt for step ${idx + 1}...`}
                          />
                      </div>
                  ))}
              </div>
              <button
                  onClick={addStep}
                  className="mt-2 text-sm text-blue-600 hover:text-blue-700 flex items-center gap-1"
              >
                  <Plus size={16} /> Add Next Step
              </button>
            </div>

            <div className="flex justify-end gap-2 pt-4 border-t mt-4">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={!newName || newContent.every(c => !c.trim())}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {templates.map((template) => (
          <div key={template.id} className={clsx(
            "bg-white p-6 rounded-xl border shadow-sm relative group flex flex-col",
            template.is_default ? "border-blue-500 ring-1 ring-blue-500" : "border-gray-200"
          )}>
            <div className="absolute top-4 right-4 flex gap-2">
                {!template.is_default && (
                    <button 
                        onClick={() => handleSetDefault(template.id)}
                        className="text-gray-400 hover:text-yellow-500 opacity-0 group-hover:opacity-100 transition-opacity"
                        title="Set as Default"
                    >
                        <Star size={18} />
                    </button>
                )}
                {template.is_default && (
                    <span className="text-blue-500" title="Default Template">
                        <Check size={18} />
                    </span>
                )}
                <button 
                    onClick={() => handleDelete(template.id)}
                    className="text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Delete"
                >
                    <Trash2 size={18} />
                </button>
            </div>
            
            <h3 className="font-semibold text-gray-900 mb-2 pr-16">{template.name}</h3>
            
            <div className="flex-1 space-y-2 mb-4">
                {template.content.map((step, idx) => (
                    <div key={idx} className="text-sm text-gray-600 bg-gray-50 p-2 rounded border border-gray-100">
                        <span className="font-xs font-bold text-gray-400 block mb-1">Step {idx + 1}</span>
                        <p className="line-clamp-3 whitespace-pre-wrap font-mono">{step}</p>
                    </div>
                ))}
            </div>
            
            {template.is_default && (
                <div className="text-xs font-medium text-blue-600 bg-blue-50 px-2 py-1 rounded self-start">
                    Default
                </div>
            )}
          </div>
        ))}
      </div>

{/* Modal removed */}
    </Layout>
  );
};

export default TemplatesPage;
