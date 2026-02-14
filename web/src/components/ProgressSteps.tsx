import { Check, Loader2, Download, Mic, Sparkles, BookOpen, CircleDot } from 'lucide-react';
import clsx from 'clsx';

export interface Step {
  key: string;
  label: string;
  icon: React.ReactNode;
}

const DEFAULT_STEPS: Step[] = [
  { key: 'download', label: '下载', icon: <Download size={16} /> },
  { key: 'transcribe', label: '转录', icon: <Mic size={16} /> },
  { key: 'optimize', label: '优化', icon: <Sparkles size={16} /> },
  { key: 'summarize', label: '总结', icon: <BookOpen size={16} /> },
  { key: 'complete', label: '完成', icon: <Check size={16} /> },
];

interface Props {
  currentStep: string;
  completedSteps: string[];
  steps?: Step[];
}

export default function ProgressSteps({
  currentStep,
  completedSteps,
  steps = DEFAULT_STEPS,
}: Props) {
  return (
    <div className="flex items-start gap-0 overflow-x-auto py-2">
      {steps.map((step, i) => {
        const isCompleted = completedSteps.includes(step.key);
        const isActive = step.key === currentStep;
        const isPending = !isCompleted && !isActive;

        return (
          <div key={step.key} className="flex items-center flex-1 min-w-0">
            <div className="flex flex-col items-center gap-1.5 flex-1">
              <div
                className={clsx(
                  'w-8 h-8 rounded-full flex items-center justify-center border-2 transition-all duration-300',
                  isCompleted && 'bg-emerald-50 border-emerald-400 text-emerald-600',
                  isActive && 'bg-[var(--color-accent-light)] border-[var(--color-accent)] text-[var(--color-accent)]',
                  isPending && 'bg-gray-50 border-gray-200 text-gray-400',
                )}
              >
                {isCompleted ? (
                  <Check size={14} strokeWidth={2.5} />
                ) : isActive ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <CircleDot size={14} />
                )}
              </div>
              <span
                className={clsx(
                  'text-[11px] font-medium text-center transition-colors',
                  isCompleted && 'text-emerald-600',
                  isActive && 'text-[var(--color-accent)]',
                  isPending && 'text-gray-400',
                )}
              >
                {step.label}
              </span>
            </div>

            {i < steps.length - 1 && (
              <div className="flex-shrink-0 w-8 h-0.5 mt-4 mx-0.5">
                <div
                  className={clsx(
                    'h-full rounded-full transition-all duration-500',
                    isCompleted ? 'bg-emerald-300' : 'bg-gray-200',
                  )}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
