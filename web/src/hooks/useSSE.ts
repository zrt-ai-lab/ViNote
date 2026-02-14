import { useEffect, useRef, useCallback, useState } from 'react';

interface UseSSEOptions {
  onMessage: (data: unknown) => void;
  onError?: () => void;
}

export function useSSE() {
  const esRef = useRef<EventSource | null>(null);
  const [connected, setConnected] = useState(false);

  const connect = useCallback((path: string, opts: UseSSEOptions) => {
    esRef.current?.close();
    const es = new EventSource(path);
    esRef.current = es;

    es.onopen = () => {
      setConnected(true);
    };

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === 'heartbeat') return;
        opts.onMessage(data);
      } catch {
        /* skip */
      }
    };

    es.onerror = () => {
      setConnected(false);
      opts.onError?.();
      es.close();
    };
  }, []);

  const disconnect = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    setConnected(false);
  }, []);

  useEffect(() => {
    return () => {
      esRef.current?.close();
    };
  }, []);

  return { connect, disconnect, connected };
}
