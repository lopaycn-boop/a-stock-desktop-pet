import React, { useState, useCallback, useEffect } from 'react';

export default function DropOverlay({ onDrop, lang = 'zh' }) {
  const [dragging, setDragging] = useState(false);
  const [dragCount, setDragCount] = useState(0);

  useEffect(() => {
    const handleDragEnter = (e) => {
      e.preventDefault();
      setDragCount(c => {
        const n = c + 1;
        if (n > 0) setDragging(true);
        return n;
      });
    };
    const handleDragLeave = (e) => {
      e.preventDefault();
      setDragCount(c => {
        const n = c - 1;
        if (n <= 0) { setDragging(false); return 0; }
        return n;
      });
    };
    const handleDragOver = (e) => e.preventDefault();
    const handleDrop = (e) => {
      e.preventDefault();
      setDragCount(0);
      setDragging(false);
      if (onDrop && e.dataTransfer) {
        const text = e.dataTransfer.getData('text/plain');
        if (text) { onDrop(text); return; }
        if (e.dataTransfer.files.length > 0) {
          const file = e.dataTransfer.files[0];
          if (file.type === 'text/plain' || file.name.endsWith('.txt') || file.name.endsWith('.env') || file.name.endsWith('.key')) {
            const reader = new FileReader();
            reader.onload = (ev) => onDrop(ev.target.result);
            reader.readAsText(file);
          }
        }
      }
    };
    window.addEventListener('dragenter', handleDragEnter);
    window.addEventListener('dragleave', handleDragLeave);
    window.addEventListener('dragover', handleDragOver);
    window.addEventListener('drop', handleDrop);
    return () => {
      window.removeEventListener('dragenter', handleDragEnter);
      window.removeEventListener('dragleave', handleDragLeave);
      window.removeEventListener('dragover', handleDragOver);
      window.removeEventListener('drop', handleDrop);
    };
  }, [onDrop]);

  if (!dragging) return null;

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 999997,
      background: 'rgba(105,240,174,0.08)', backdropFilter: 'blur(4px)',
      border: '3px dashed var(--accent)', borderRadius: 16,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      pointerEvents: 'none',
    }}>
      <div style={{
        background: 'var(--bg-secondary)', borderRadius: 20, padding: '32px 48px',
        border: '2px solid var(--accent)', textAlign: 'center',
        boxShadow: '0 0 40px rgba(105,240,174,0.2)',
      }}>
        <div style={{ fontSize: 48, marginBottom: 12 }}>🔓</div>
        <div style={{ fontSize: 18, color: 'var(--accent)', fontWeight: 600 }}>
          {lang === 'zh' ? '拖放 API 密钥到这里' : 'Drop API key here'}
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 8 }}>
          {lang === 'zh' ? '支持文本、.txt、.env、.key 文件' : 'Supports text, .txt, .env, .key files'}
        </div>
      </div>
    </div>
  );
}