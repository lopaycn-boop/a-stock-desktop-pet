import React, { useState, useEffect, useCallback, useRef } from 'react';

export default function ContextMenu({ x, y, items, onClose, lang = 'zh' }) {
  const ref = useRef(null);
  const [selected, setSelected] = useState(-1);

  useEffect(() => {
    const handleClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    };
    const handleKey = (e) => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowDown') { e.preventDefault(); setSelected(s => Math.min(s + 1, items.length - 1)); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); setSelected(s => Math.max(s - 1, 0)); }
      else if (e.key === 'Enter' && selected >= 0 && items[selected]?.action) { items[selected].action(); onClose(); }
    };
    document.addEventListener('click', handleClick);
    document.addEventListener('keydown', handleKey);
    return () => { document.removeEventListener('click', handleClick); document.removeEventListener('keydown', handleKey); };
  }, [items, selected, onClose]);

  const menuW = 180;
  const menuH = items.length * 36 + 8;
  const adjustedX = Math.min(x, window.innerWidth - menuW - 10);
  const adjustedY = Math.min(y, window.innerHeight - menuH - 10);

  return (
    <div
      ref={ref}
      role="menu" aria-label={lang === 'zh' ? '右键菜单' : 'Context menu'}
      style={{
        position: 'fixed', left: adjustedX, top: adjustedY, zIndex: 999999,
        background: 'var(--bg-secondary)', border: '1px solid var(--border)',
        borderRadius: 10, boxShadow: '0 8px 32px var(--shadow)',
        padding: '4px 0', minWidth: menuW, maxWidth: 220,
        animation: 'ctxIn 0.12s ease-out',
      }}
    >
      {items.map((item, i) => item.sep ? (
        <div key={i} style={{ height: 1, background: 'var(--border)', margin: '4px 8px' }} />
      ) : (
        <div
          key={i}
          role="menuitem"
          onClick={() => { item.action?.(); onClose(); }}
          onMouseEnter={() => setSelected(i)}
          style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px',
            cursor: 'pointer', fontSize: 13,
            background: i === selected ? 'var(--bg-card-hover)' : 'transparent',
            color: item.danger ? '#ff8a80' : 'var(--text-primary)',
            transition: 'background 0.1s',
          }}
        >
          <span style={{ width: 20, textAlign: 'center', fontSize: 14 }}>{item.icon}</span>
          <span style={{ flex: 1 }}>{item.label}</span>
          {item.shortcut && <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace' }}>{item.shortcut}</span>}
        </div>
      ))}
      <style>{`
        @keyframes ctxIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
      `}</style>
    </div>
  );
}