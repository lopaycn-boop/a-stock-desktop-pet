import React, { useState, useCallback } from 'react';

export default function MessageActions({ message, onCopy, onRetry, onDelete, onPin, isPinned, lang = 'zh' }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    if (onCopy) { onCopy(message); }
    else if (navigator.clipboard) {
      navigator.clipboard.writeText(message.content || '').catch(() => {});
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [message, onCopy]);

  const handleRetry = useCallback(() => {
    if (onRetry) onRetry(message);
  }, [message, onRetry]);

  const handleDelete = useCallback(() => {
    if (onDelete) onDelete(message);
  }, [message, onDelete]);

  const isUser = message.type === 'user';
  const isSystem = message.type === 'system';

  return (
    <div className="msg-actions" style={{
      display: 'flex', gap: 4, opacity: 0, transition: 'opacity 0.15s',
      position: 'absolute', top: 4, [isUser ? 'left' : 'right']: 4,
    }}>
      <button onClick={handleCopy} title={lang === 'zh' ? '复制' : 'Copy'} style={{
        background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer',
        fontSize: 11, padding: '2px 4px', borderRadius: 4,
      }}>
        {copied ? '✓' : '📋'}
      </button>
      {!isSystem && (
        <button onClick={handleRetry} title={lang === 'zh' ? '重试' : 'Retry'} style={{
          background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer',
          fontSize: 11, padding: '2px 4px', borderRadius: 4,
        }}>
          🔄
        </button>
      )}
      <button onClick={handleDelete} title={lang === 'zh' ? '删除' : 'Delete'} style={{
        background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer',
        fontSize: 11, padding: '2px 4px', borderRadius: 4,
      }}>
        ✕
      </button>
      {onPin && (
        <button onClick={() => onPin(message)} title={isPinned ? (lang === 'zh' ? '取消置顶' : 'Unpin') : (lang === 'zh' ? '置顶' : 'Pin')} style={{
          background: 'none', border: 'none', color: isPinned ? 'var(--accent)' : 'var(--text-muted)', cursor: 'pointer',
          fontSize: 11, padding: '2px 4px', borderRadius: 4,
        }}>
          📌
        </button>
      )}
    </div>
  );
}