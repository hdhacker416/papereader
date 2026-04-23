import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Trash2 } from 'lucide-react';
import Layout from '../components/Layout';
import PromptListEditor from '../components/PromptListEditor';
import { tasksApi, templatesApi } from '../api/services';
import { Template } from '../types';
import { MODEL_OPTIONS } from '../constants/models';

const TaskCreatePage: React.FC = () => {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [templateId, setTemplateId] = useState('');
  const [customReadingPrompts, setCustomReadingPrompts] = useState<string[]>(['']);
  const [modelName, setModelName] = useState('gemini-3-flash-preview');
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(false);
  const [paperList, setPaperList] = useState<string[]>(['']);

  useEffect(() => {
    const fetchTemplates = async () => {
      try {
        const data = await templatesApi.list();
        setTemplates(data);
        if (data.length > 0) {
          // Select default or first
          const def = data.find(t => t.is_default);
          if (def) {
              setTemplateId(def.id);
          } else {
              setTemplateId(data[0].id);
          }
        }
      } catch (error) {
        console.error('Failed to fetch templates:', error);
      }
    };
    fetchTemplates();
  }, []);

  useEffect(() => {
    const selectedTemplate = templates.find((item) => item.id === templateId);
    if (!selectedTemplate) {
      return;
    }
    setCustomReadingPrompts(selectedTemplate.content.length > 0 ? selectedTemplate.content : ['']);
  }, [templateId, templates]);

  const handleAddRow = () => {
    setPaperList([...paperList, '']);
  };

  const handleRemoveRow = (index: number) => {
    const newList = paperList.filter((_, i) => i !== index);
    setPaperList(newList.length ? newList : ['']);
  };

  const handlePaperChange = (index: number, value: string) => {
    const newList = [...paperList];
    newList[index] = value;
    setPaperList(newList);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !templateId) return;

    setLoading(true);
    try {
      // 1. Create Task
      const task = await tasksApi.create({
        name,
        description,
        template_id: templateId,
        model_name: modelName,
        custom_reading_prompts: customReadingPrompts.map((item) => item.trim()).filter(Boolean),
      });

      // 2. Add Papers if any
      const validPapers = paperList.filter(t => t.trim());
      if (validPapers.length > 0) {
        await tasksApi.addPapers(task.id, { titles: validPapers });
      }
      
      navigate(`/tasks/${task.id}`);
    } catch (error) {
      console.error('Failed to create task:', error);
      // Removed alert
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout>
      <div className="max-w-3xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Create New Task</h1>
        
        <form onSubmit={handleSubmit} className="space-y-6 bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Task Name</label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="e.g., Weekly Reading List"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
                <select
                  required
                  value={modelName}
                  onChange={(e) => setModelName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  {MODEL_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Template</label>
                <select
                  required
                  value={templateId}
                  onChange={(e) => setTemplateId(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="" disabled>Select a template</option>
                  {templates.map(t => (
                    <option key={t.id} value={t.id}>
                      {t.name} {t.is_default ? '(Default)' : ''}
                    </option>
                  ))}
                </select>
                {templates.length === 0 && (
                    <p className="text-xs text-red-500 mt-1">No templates found. Please create one first.</p>
                )}
              </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              rows={2}
              placeholder="Optional description..."
            />
          </div>

          <PromptListEditor
            title="Reading Prompts"
            description="These prompts will be saved on the task and used when the papers are interpreted."
            prompts={customReadingPrompts}
            onChange={setCustomReadingPrompts}
          />

          <div className="border-t pt-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">Initial Papers</label>
            <div className="space-y-2">
                {paperList.map((paper, index) => (
                    <div key={index} className="flex gap-2">
                        <input
                            type="text"
                            value={paper}
                            onChange={(e) => handlePaperChange(index, e.target.value)}
                            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
                            placeholder="Enter paper title..."
                        />
                        <button
                            type="button"
                            onClick={() => handleRemoveRow(index)}
                            className="p-2 text-gray-400 hover:text-red-500 transition-colors"
                            title="Remove row"
                        >
                            <Trash2 size={18} />
                        </button>
                    </div>
                ))}
            </div>
            <button
                type="button"
                onClick={handleAddRow}
                className="mt-2 flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700 font-medium"
            >
                <Plus size={16} /> Add Another Paper
            </button>
          </div>

          <div className="pt-4 flex justify-end">
            <button
              type="submit"
              disabled={loading || !name || !templateId}
              className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 font-medium"
            >
              {loading ? 'Creating...' : 'Create Task'}
            </button>
          </div>
        </form>
      </div>
    </Layout>
  );
};

export default TaskCreatePage;
