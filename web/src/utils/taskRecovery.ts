import type { TaskStatus } from '../types';

type IdStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
export type ArtifactTab = 'script' | 'summary' | 'mindmap' | 'raw' | 'translation';

/** Read a task ID without requiring browser storage to be available. */
export function readStoredId(key: string, storage?: IdStorage): string | null {
  try {
    const value = (storage ?? window.localStorage).getItem(key);
    return value && /^[a-zA-Z0-9-]{1,64}$/.test(value) ? value : null;
  } catch {
    return null;
  }
}

/** Persist only an opaque ID; never retain input URLs or generated content. */
export function writeStoredId(key: string, value: string | null, storage?: IdStorage): void {
  try {
    const target = storage ?? window.localStorage;
    if (value && /^[a-zA-Z0-9-]{1,64}$/.test(value)) target.setItem(key, value);
    else target.removeItem(key);
  } catch {
    // Private browsing or a full storage quota must not prevent task execution.
  }
}

/** Resolve current API filenames and older task responses to a download basename. */
export function getArtifactFilename(task: Partial<TaskStatus> | null, tab: ArtifactTab): string {
  if (!task) return '';
  const explicit = {
    script: task.transcript_filename,
    summary: task.summary_filename,
    mindmap: task.mindmap_filename,
    raw: task.raw_script_filename,
    translation: task.translation_filename,
  }[tab];
  if (explicit) return /^[^/\\]+\.md$/.test(explicit) && !explicit.includes('..') ? explicit : '';
  const legacyPath = { script: task.script_path, summary: task.summary_path, translation: task.translation_path };
  const path = tab in legacyPath ? legacyPath[tab as keyof typeof legacyPath] : undefined;
  if (path) {
    const basename = path.split(/[/\\]/).pop() || '';
    if (basename.endsWith('.md') && !basename.includes('..')) return basename;
  }
  if (!task.short_id || !task.safe_title) return '';
  const prefix = { script: 'transcript', summary: 'summary', mindmap: 'mindmap', raw: 'raw', translation: 'translation' }[tab];
  const basename = `${prefix}_${task.safe_title}_${task.short_id}.md`;
  return !/[/\\]/.test(basename) && !basename.includes('..') ? basename : '';
}
