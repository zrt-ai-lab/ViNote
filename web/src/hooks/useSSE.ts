import { useEffect, useRef, useCallback, useState } from 'react';
import { createSSE } from '../api/client';

interface UseSSEOptions {
  onMessage: (data: unknown) => void;
  onError?: () => void;
}

export function useSSE() {
  const esRef = useRef<EventSource | null>(null);
  const [connected, setConnected] = useState(false);

  const connect = useCallback((path: string, opts: UseSSEOptions) => {
    esRef.current?.close();
    const es = createSSE(
      path,
      opts.onMessage,
      () => {
        setConnected(false);
        opts.onError?.();
        esRef.current = null;
      },
      () => setConnected(true),
    );
    esRef.current = es;
  }, []);

  const disconnect = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    setConnected(false);
  }, []);

  useEffect(() => disconnect, [disconnect]);

  return { connect, disconnect, connected };
}
