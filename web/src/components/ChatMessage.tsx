import MarkdownRenderer from './MarkdownRenderer';
import { User, Bot } from 'lucide-react';

interface Props {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: Date;
  isStreaming?: boolean;
  children?: React.ReactNode;
}

export default function ChatMessage({ role, content, timestamp, isStreaming, children }: Props) {
  const isUser = role === 'user';

  if (isUser) {
    return (
      <div className="flex gap-3 flex-row-reverse">
        <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 bg-[var(--color-accent-light)] text-[var(--color-accent)]">
          <User size={15} />
        </div>
        <div className="max-w-[75%] min-w-0 flex flex-col items-end">
          <div className="px-4 py-2.5 rounded-2xl text-sm leading-relaxed bg-[var(--color-accent)] text-white rounded-br-md">
            <span className="whitespace-pre-wrap">{content}</span>
          </div>
          {timestamp && (
            <span className="text-[10px] text-[var(--color-text-muted)] mt-1 px-1">
              {timestamp.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3 items-start">
      <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 bg-[var(--color-accent-light)]/30 text-[var(--color-accent)]">
        <Bot size={15} />
      </div>
      <div className="min-w-0 flex-1">
        {content ? (
          <div className="text-sm leading-relaxed text-[var(--color-text)]">
            <MarkdownRenderer content={content} />
          </div>
        ) : isStreaming ? (
          <div className="py-2">
            <span className="inline-flex gap-1.5 items-center">
              <span className="w-2 h-2 rounded-full bg-[var(--color-accent)]/60 animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-2 h-2 rounded-full bg-[var(--color-accent)]/60 animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-2 h-2 rounded-full bg-[var(--color-accent)]/60 animate-bounce" style={{ animationDelay: '300ms' }} />
            </span>
          </div>
        ) : null}

        {children}

        {timestamp && (
          <span className="text-[10px] text-[var(--color-text-muted)] mt-2 block">
            {timestamp.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
          </span>
        )}
      </div>
    </div>
  );
}
