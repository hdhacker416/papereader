export type ModelOption = {
  value: string;
  label: string;
};

export const MODEL_OPTIONS: ModelOption[] = [
  { value: 'gemini-3-flash-preview', label: 'Gemini 3 Flash (Faster/Cheaper)' },
  { value: 'gemini-3-pro-preview', label: 'Gemini 3 Pro (Higher Quality)' },
  { value: 'qwen-flash', label: 'Qwen Flash' },
  { value: 'qwen-plus', label: 'Qwen Plus' },
  { value: 'qwen-max', label: 'Qwen Max' },
];

export const ALLOWED_MODEL_NAMES = new Set(MODEL_OPTIONS.map((item) => item.value));

export const formatModelLabel = (modelName: string | null | undefined): string => {
  const matched = MODEL_OPTIONS.find((item) => item.value === modelName);
  return matched?.label || (modelName || 'Unknown Model');
};
