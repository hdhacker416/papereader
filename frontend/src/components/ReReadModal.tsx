import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import PromptListEditor from './PromptListEditor';
import { templatesApi } from '../api/services';
import { Template } from '../types';

interface ReReadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (templateId: string, modelName: string, customReadingPrompts: string[]) => Promise<void>;
  title: string;
  initialTemplateId?: string;
  initialModelName?: string;
  initialPrompts?: string[];
}

const ReReadModal: React.FC<ReReadModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  initialTemplateId,
  initialModelName,
  initialPrompts,
}) => {
  const [templateId, setTemplateId] = useState('');
  const [modelName, setModelName] = useState('gemini-3-flash-preview');
  const [templates, setTemplates] = useState<Template[]>([]);
  const [customReadingPrompts, setCustomReadingPrompts] = useState<string[]>(['']);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      const fetchTemplates = async () => {
        try {
          const data = await templatesApi.list();
          setTemplates(data);
          if (data.length > 0) {
            const selected = data.find((item) => item.id === initialTemplateId)
              || data.find(t => t.is_default)
              || data[0];
            setTemplateId(selected.id);
            setModelName(initialModelName || 'gemini-3-flash-preview');
            setCustomReadingPrompts(
              initialPrompts && initialPrompts.length > 0
                ? initialPrompts
                : (selected.content.length > 0 ? selected.content : [''])
            );
          }
        } catch (error) {
          console.error('Failed to fetch templates:', error);
        }
      };
      fetchTemplates();
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    if (initialPrompts && initialPrompts.length > 0) {
      return;
    }
    const selectedTemplate = templates.find((item) => item.id === templateId);
    if (!selectedTemplate) {
      return;
    }
    setCustomReadingPrompts(selectedTemplate.content.length > 0 ? selectedTemplate.content : ['']);
  }, [initialPrompts, isOpen, templateId, templates]);

  const handleConfirm = async () => {
    setLoading(true);
    try {
      await onConfirm(
        templateId,
        modelName,
        customReadingPrompts.map((item) => item.trim()).filter(Boolean),
      );
      onClose();
    } catch (error) {
      console.error('Failed to reread:', error);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6 relative">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600"
        >
          <X size={20} />
        </button>

        <h2 className="text-xl font-semibold mb-4">{title}</h2>
        <p className="text-sm text-gray-500 mb-6">
          This will re-process all papers in this task/collection using the selected configuration.
          Existing interpretations will be overwritten.
        </p>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
            <select
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="gemini-3-flash-preview">Gemini 3 Flash (Faster/Cheaper)</option>
              <option value="gemini-3-pro-preview">Gemini 3 Pro (Higher Quality)</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Template</label>
            <select
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {templates.map(t => (
                <option key={t.id} value={t.id}>
                  {t.name} {t.is_default ? '(Default)' : ''}
                </option>
              ))}
            </select>
          </div>

          <PromptListEditor
            title="Reading Prompts"
            description="These prompts will override the selected template for this re-read run."
            prompts={customReadingPrompts}
            onChange={setCustomReadingPrompts}
          />
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
          >
            {loading ? 'Processing...' : 'Start Re-read'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ReReadModal;
