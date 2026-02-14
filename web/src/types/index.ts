// ============================================================
// Type definitions for ViNote frontend
// ============================================================

export interface TaskStatus {
  status: 'processing' | 'completed' | 'error' | 'cancelled';
  progress: number;
  message: string;
  type?: string;
  video_title?: string;
  script?: string;
  summary?: string;
  raw_script?: string;
  mindmap?: string;
  error?: string;
  transcript?: string;
  script_path?: string;
  summary_path?: string;
  short_id?: string;
  safe_title?: string;
  detected_language?: string;
  summary_language?: string;
  raw_script_filename?: string;
  mindmap_filename?: string;
  translation?: string;
  translation_path?: string;
  translation_filename?: string;
}

export interface VideoInfo {
  title: string;
  duration: number;
  thumbnail?: string;
  description?: string;
  uploader?: string;
  embed_url?: string;
  formats?: { height: number; quality: string; filesize_string: string }[];
}

export interface DownloadStatus {
  status: 'downloading' | 'completed' | 'error' | 'cancelled';
  progress?: number;
  filename?: string;
  error?: string;
}

// Search Agent types
export type AgentMessageType =
  | 'text_chunk'
  | 'thinking'
  | 'video_list'
  | 'progress'
  | 'notes_complete'
  | 'generate_notes_command'
  | 'generation_id'
  | 'error'
  | 'cancelled'
  | 'done';

export interface AgentSSEData {
  type: AgentMessageType;
  content?: string;
  data?: AgentVideoListData | AgentNotesData | AgentGenerateCommand;
  progress?: number;
  message?: string;
  generation_id?: string;
}

export interface AgentVideo {
  title: string;
  url: string;
  cover?: string;
  thumbnail?: string;
  duration?: string;
  author?: string;
  platform?: string;
}

export interface AgentVideoListData {
  videos: AgentVideo[];
}

export interface AgentNotesData {
  video_title?: string;
  title?: string;
  summary?: string;
  transcript?: string;
  mindmap?: string;
  translation?: string;
  files?: {
    transcript_filename?: string;
    transcript?: string;
    summary_filename?: string;
    summary?: string;
    raw_transcript_filename?: string;
    raw?: string;
    mindmap_filename?: string;
    translation_filename?: string;
  };
}

export interface AgentGenerateCommand {
  video_index: number;
  video_url: string;
  video_title: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  videos?: AgentVideo[];
  videosByPlatform?: Record<string, AgentVideo[]>;
  thinking?: string[];
  progress?: { percent: number; message: string };
  notesResult?: AgentNotesData;
  generationId?: string;
  isStreaming?: boolean;
}

export interface DevToolsSSEData {
  content?: string;
  done?: boolean;
}

export interface QAStreamData {
  content?: string;
  done?: boolean;
}
