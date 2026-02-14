import { proxyImageUrl } from '../api/client';
import type { AgentVideo } from '../types';
import { Clock, User, FileText } from 'lucide-react';

interface Props {
  video: AgentVideo;
  onGenerateNotes?: (url: string, title: string) => void;
  generating?: boolean;
  generated?: boolean;
}

export default function VideoCard({ video, onGenerateNotes, generating, generated }: Props) {
  const thumbUrl = proxyImageUrl(video.cover || video.thumbnail || '');

  return (
    <div className="flex-shrink-0 w-56 bg-white border border-gray-200 rounded-lg overflow-hidden hover:border-gray-300 transition-colors">
      <div className="relative aspect-video bg-gray-100">
        <img
          src={thumbUrl}
          alt={video.title}
          className="w-full h-full object-cover"
          loading="lazy"
          onError={(e) => {
            (e.target as HTMLImageElement).src = '/product-logo.png';
          }}
        />
        {video.duration && (
          <span className="absolute bottom-1.5 right-1.5 px-1.5 py-0.5 text-[10px] font-medium bg-black/70 text-white rounded">
            {video.duration}
          </span>
        )}
      </div>
      <div className="p-2.5">
        <h4 className="text-xs font-medium text-gray-900 line-clamp-2 leading-snug mb-1.5">
          {video.title || '未命名视频'}
        </h4>
        <div className="flex items-center gap-2 text-[11px] text-gray-500 mb-2">
          {video.author && (
            <span className="flex items-center gap-0.5 truncate">
              <User size={10} />
              {video.author}
            </span>
          )}
          {video.duration && (
            <span className="flex items-center gap-0.5">
              <Clock size={10} />
              {video.duration}
            </span>
          )}
        </div>
        {onGenerateNotes && (
          <button
            onClick={() => onGenerateNotes(video.url, video.title)}
            disabled={generating}
            className={`w-full flex items-center justify-center gap-1 px-2 py-1.5 text-[11px] font-medium rounded-md transition-colors ${
              generated
                ? 'bg-emerald-50 text-emerald-600 border border-emerald-200'
                : generating
                  ? 'bg-gray-50 text-gray-400 border border-gray-200 cursor-wait'
                  : 'bg-[var(--color-accent-light)] text-[var(--color-accent)] border border-[var(--color-accent)]/20 hover:bg-[var(--color-accent)] hover:text-white'
            }`}
          >
            <FileText size={11} />
            {generated ? '已生成' : generating ? '生成中...' : '生成笔记'}
          </button>
        )}
      </div>
    </div>
  );
}
