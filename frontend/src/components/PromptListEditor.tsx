import React from 'react';
import { Plus, Trash2 } from 'lucide-react';

interface PromptListEditorProps {
  title: string;
  description?: string;
  prompts: string[];
  onChange: (prompts: string[]) => void;
}

const PromptListEditor: React.FC<PromptListEditorProps> = ({
  title,
  description,
  prompts,
  onChange,
}) => {
  const safePrompts = prompts.length > 0 ? prompts : [''];

  const handlePromptChange = (index: number, value: string) => {
    const next = [...safePrompts];
    next[index] = value;
    onChange(next);
  };

  const handleAddPrompt = () => {
    onChange([...safePrompts, '']);
  };

  const handleRemovePrompt = (index: number) => {
    const next = safePrompts.filter((_, itemIndex) => itemIndex !== index);
    onChange(next.length > 0 ? next : ['']);
  };

  return (
    <div className="border border-gray-200 rounded-2xl p-4 space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
        {description && <p className="text-xs text-gray-500 mt-1">{description}</p>}
      </div>
      <div className="space-y-3">
        {safePrompts.map((prompt, index) => (
          <div key={index} className="flex gap-2 items-start">
            <textarea
              value={prompt}
              onChange={(event) => handlePromptChange(index, event.target.value)}
              rows={3}
              className="flex-1 px-3 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-y text-sm"
              placeholder={`Prompt ${index + 1}`}
            />
            <button
              type="button"
              onClick={() => handleRemovePrompt(index)}
              className="mt-1 p-2 text-gray-400 hover:text-red-500 transition-colors"
              title="Remove prompt"
            >
              <Trash2 size={18} />
            </button>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={handleAddPrompt}
        className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700 font-medium"
      >
        <Plus size={16} /> Add Prompt
      </button>
    </div>
  );
};

export default PromptListEditor;
