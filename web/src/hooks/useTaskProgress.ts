import { useEffect, useState } from 'react';
import { createSSE, fetchJSON } from '../api/client';
import { monitorProgress } from '../api/progress';
import type { ProgressConnection } from '../api/progress';
import type { TaskStatus } from '../types';

/** Restore and follow a task without treating transport errors as task failures. */
export function useTaskProgress(
  taskId: string | null,
  onUpdate: (data: TaskStatus) => void,
  onUnavailable: (error: Error) => void,
) {
  const [connection, setConnection] = useState<ProgressConnection>('checking');
  useEffect(() => {
    if (!taskId) return;
    const id = encodeURIComponent(taskId);
    return monitorProgress<TaskStatus>({
      load: (signal) => fetchJSON(`/api/task-status/${id}`, { signal }),
      subscribe: (receive, onError, onOpen) => createSSE(`/api/task-stream/${id}`, (data) => receive(data as TaskStatus), onError, onOpen),
      isTerminal: (data) => ['completed', 'error', 'cancelled'].includes(data.status),
      onUpdate,
      onConnectionChange: setConnection,
      onUnavailable,
    });
  }, [taskId, onUpdate, onUnavailable]);
  return connection;
}
