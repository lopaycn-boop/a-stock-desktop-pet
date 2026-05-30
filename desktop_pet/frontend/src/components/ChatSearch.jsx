import React, { useState, useCallback, useMemo } from 'react';

export default function ChatSearch({ messages, onJumpTo, onClose, lang = 'zh' }) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);

  const results = useMemo(() => {
    if (!query.trim()) return [];
    const q = query.toLowerCase();
    return messages
      .map((m, i) => ({ ...m, idx: i }))
      .filter(m => m.content && m.content.toLowerCase().includes(q));
  }, [messages, query]);

  const handlePrev = useCallback(() => {
    setSelectedIndex(i => (i - 1 + results.length) % results.length);
  }, [results.length]);

  const handleNext = useCallback(() => {
    setSelectedIndex(i => (i + 1) % results.length);
  }, [results.length]);

  const handleJump = useCallback(() => {
    if (results[selectedIndex]) {
      onJumpTo(results[selectedIndex].idx);
    }
  }, [results, selectedIndex, onJumpTo]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter') { handleJump(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); handlePrev(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); handleNext(); }
    else if (e.key === 'Escape') { onClose(); }
  }, [handleJump, handlePrev, handleNext, onClose]);

  const labels = lang === 'zh'
    ? { placeholder: '搜索聊天记录...', count: '结果', close: '关闭' }
    : { placeholder: 'Search messages...', count: 'results', close: 'Close' };

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px',
      background: 'var(--bg-card)', borderBottom: '1px solid var(--border)',
    }}>
      <span style={{ fontSize: 14 }}>🔍</span>
      <input
        type="text"
        value={query}
        onChange={e => { setQuery(e.target.value); setSelectedIndex(0); }}
        onKeyDown={handleKeyDown}
        placeholder={labels.placeholder}
        autoFocus
        style={{
          flex: 1, background: 'var(--bg-input)', border: '1px solid var(--border)',
          borderRadius: 8, padding: '4px 8px', fontSize: 13, color: 'var(--text-primary)',
          outline: 'none',
        }}
      />
      {results.length > 0 && (
        <span style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
          {selectedIndex + 1}/{results.length} {labels.count}
        </span>
      )}
      {results.length > 1 && (
        <>
          <button onClick={handlePrev} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 12 }}>↑</button>
          <button onClick={handleNext} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 12 }}>↓</button>
        </>
      )}
      <button onClick={handleJump} disabled={results.length === 0} style={{
        background: results.length ? 'var(--accent)' : 'var(--bg-card)',
        border: 'none', borderRadius: 6, padding: '3px 10px', fontSize: 12,
        color: results.length ? '#1a1a2e' : 'var(--text-muted)', cursor: results.length ? 'pointer' : 'default',
      }}>
        ↵
      </button>
      <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 14 }}>✕</button>
    </div>
  );
}