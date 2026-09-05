export type ProgressConnection = 'checking' | 'live' | 'polling' | 'retrying';

interface MonitorOptions<T> {
  load: (signal: AbortSignal) => Promise<T>;
  subscribe?: (onUpdate: (data: T) => void, onError: () => void, onOpen: () => void) => { close: () => void };
  isTerminal: (data: T) => boolean;
  onUpdate: (data: T) => void;
  onConnectionChange: (state: ProgressConnection) => void;
  onUnavailable: (error: Error) => void;
  intervalMs?: number;
  timeoutMs?: number;
}

/** Observe a server task, falling back to serial polling after a stream disconnect. */
export function monitorProgress<T>(options: MonitorOptions<T>): () => void {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let request: AbortController | undefined;
  let stream: { close: () => void } | undefined;
  let streamFailed = false;
  const interval = options.intervalMs ?? 3000;

  const stop = () => {
    stopped = true;
    clearTimeout(timer);
    request?.abort();
    stream?.close();
  };
  const receive = (data: T) => {
    if (stopped) return;
    options.onUpdate(data);
    if (options.isTerminal(data)) stop();
  };
  const schedule = () => {
    if (!stopped) timer = setTimeout(poll, interval);
  };
  const poll = async () => {
    if (stopped) return;
    request = new AbortController();
    const currentRequest = request;
    const timeout = setTimeout(() => currentRequest.abort(), options.timeoutMs ?? 10000);
    try {
      const data = await options.load(currentRequest.signal);
      if (stopped) return;
      receive(data);
      if (stopped) return;
      if (options.subscribe && !streamFailed) {
        stream = options.subscribe(receive, () => {
          if (stopped) return;
          stream?.close();
          stream = undefined;
          streamFailed = true;
          options.onConnectionChange('retrying');
          schedule();
        }, () => {
          if (!stopped) options.onConnectionChange('live');
        });
      } else {
        options.onConnectionChange('polling');
        schedule();
      }
    } catch (error) {
      if (stopped) return;
      const status = (error as { status?: number })?.status;
      if (status && status >= 400 && status < 500 && status !== 429) {
        stop();
        options.onUnavailable(error instanceof Error ? error : new Error('任务无法读取'));
      } else {
        options.onConnectionChange('retrying');
        schedule();
      }
    } finally {
      clearTimeout(timeout);
    }
  };
  void poll();
  return stop;
}
