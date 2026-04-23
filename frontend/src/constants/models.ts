export type ModelOption = {
  value: string;
  label: string;
};

export const TEXT_MODEL_OPTIONS: ModelOption[] = [
  { value: 'gemini-3-flash-preview', label: 'Gemini 3 Flash (Faster/Cheaper)' },
  { value: 'gemini-3-pro-preview', label: 'Gemini 3 Pro (Higher Quality)' },
  { value: 'qwen-flash', label: 'Qwen Flash' },
  { value: 'qwen-plus', label: 'Qwen Plus' },
  { value: 'qwen-max', label: 'Qwen Max' },
];

export const DIRECT_PDF_MODEL_OPTIONS: ModelOption[] = [
  { value: 'qwen-long', label: 'Qwen Long (Direct PDF)' },
  { value: 'qwen-doc-turbo', label: 'Qwen Doc Turbo (Direct PDF)' },
];

export const MODEL_OPTIONS: ModelOption[] = [
  ...TEXT_MODEL_OPTIONS,
  ...DIRECT_PDF_MODEL_OPTIONS,
];

export const REPORT_MODEL_OPTIONS: ModelOption[] = [...TEXT_MODEL_OPTIONS];

export const ALLOWED_MODEL_NAMES = new Set(MODEL_OPTIONS.map((item) => item.value));

export const formatModelLabel = (modelName: string | null | undefined): string => {
  const matched = MODEL_OPTIONS.find((item) => item.value === modelName);
  return matched?.label || (modelName || 'Unknown Model');
};
