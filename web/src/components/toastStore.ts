export type ToastType = 'success' | 'error' | 'info';

type ToastHandler = (message: string, type: ToastType) => void;

let toastHandler: ToastHandler | null = null;

export function toast(message: string, type: ToastType = 'info') {
  toastHandler?.(message, type);
}

export function setToastHandler(handler: ToastHandler | null) {
  toastHandler = handler;
}
