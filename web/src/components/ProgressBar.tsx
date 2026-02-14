import clsx from 'clsx';

interface Props {
  progress: number;
  className?: string;
}

export default function ProgressBar({ progress, className }: Props) {
  const clamped = Math.min(100, Math.max(0, progress));
  return (
    <div className={clsx('w-full bg-gray-100 rounded-full h-1.5', className)}>
      <div
        className="bg-[var(--color-accent)] h-1.5 rounded-full transition-all duration-300"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
