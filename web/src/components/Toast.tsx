import { useEffect, useState, useCallback } from 'react';
import { CheckCircle, AlertCircle, Info, X } from 'lucide-react';
import clsx from 'clsx';

type ToastType = 'success' | 'error' | 'info';

interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
  leaving?: boolean;
}

let addToastFn: ((message: string, type: ToastType) => void) | null = null;

export function toast(message: string, type: ToastType = 'info') {
  addToastFn?.(message, type);
}

let nextId = 0;

export default function Toast() {
  const [items, setItems] = useState<ToastItem[]>([]);

  const addToast = useCallback((message: string, type: ToastType) => {
    const id = nextId++;
    setItems((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setItems((prev) => prev.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
      setTimeout(() => {
        setItems((prev) => prev.filter((t) => t.id !== id));
      }, 300);
    }, 3000);
  }, []);

  useEffect(() => {
    addToastFn = addToast;
    return () => {
      addToastFn = null;
    };
  }, [addToast]);

  const removeToast = (id: number) => {
    setItems((prev) => prev.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
    setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id));
    }, 300);
  };

  const icons = {
    success: <CheckCircle size={16} className="text-emerald-600" />,
    error: <AlertCircle size={16} className="text-red-600" />,
    info: <Info size={16} className="text-[var(--color-accent)]" />,
  };

  return (
    <div className="fixed top-4 right-4 z-[200] flex flex-col gap-2 pointer-events-none">
      {items.map((item) => (
        <div
          key={item.id}
          className={clsx(
            'pointer-events-auto flex items-center gap-2.5 px-4 py-3 rounded-lg shadow-lg border bg-white min-w-[280px] max-w-[400px]',
            item.type === 'success' && 'border-emerald-200',
            item.type === 'error' && 'border-red-200',
            item.type === 'info' && 'border-blue-200',
          )}
          style={{
            animation: item.leaving ? 'toast-out 0.3s ease forwards' : 'toast-in 0.3s ease',
          }}
        >
          {icons[item.type]}
          <span className="flex-1 text-sm text-gray-700">{item.message}</span>
          <button
            onClick={() => removeToast(item.id)}
            className="text-gray-400 hover:text-gray-600 shrink-0"
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
