import { createElement, type ReactNode } from 'react';
import { BookOpen, Captions, Check, Download, Mic, Sparkles } from 'lucide-react';

export interface ProgressStep {
  key: string;
  label: string;
  icon: ReactNode;
}

export const DEFAULT_STEPS: ProgressStep[] = [
  { key: 'download', label: '下载', icon: createElement(Download, { size: 16 }) },
  { key: 'transcribe', label: '转录', icon: createElement(Mic, { size: 16 }) },
  { key: 'optimize', label: '优化', icon: createElement(Sparkles, { size: 16 }) },
  { key: 'summarize', label: '总结', icon: createElement(BookOpen, { size: 16 }) },
  { key: 'complete', label: '完成', icon: createElement(Check, { size: 16 }) },
];

export const SUBTITLE_STEPS: ProgressStep[] = [
  { key: 'download', label: '字幕', icon: createElement(Captions, { size: 16 }) },
  { key: 'transcribe', label: '提取', icon: createElement(Mic, { size: 16 }) },
  { key: 'optimize', label: '优化', icon: createElement(Sparkles, { size: 16 }) },
  { key: 'summarize', label: '总结', icon: createElement(BookOpen, { size: 16 }) },
  { key: 'complete', label: '完成', icon: createElement(Check, { size: 16 }) },
];
