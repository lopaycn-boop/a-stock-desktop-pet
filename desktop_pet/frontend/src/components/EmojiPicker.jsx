import { useState, useRef, useCallback } from 'react';

const EMOJI_CATEGORIES = {
  '😀': ['😀','😊','😂','🤣','😍','🥰','😎','🤔','😏','😇','🥳','😱','😢','😤','🤯','😴','🤮','🥶','🥵','😈'],
  '📊': ['📈','📉','💰','💹','🔥','⭐','💎','🏆','🎯','📊','📋','🔔','🛑','⚠️','✅','❌','💰','🏦','💵','💳'],
  '🥔': ['🥔','🥚','🐱','🐶','🦊','🐰','🐻','🐼','🐨','🦁','🐸','🐵','🐔','🐧','🐦','🦄','🐝','🐛','🦋','🐌'],
};

export default function EmojiPicker({ onSelect, lang = 'zh' }) {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState('😀');
  const ref = useRef(null);

  const handleSelect = useCallback((emoji) => {
    onSelect?.(emoji);
    setOpen(false);
  }, [onSelect]);

  const title = lang === 'zh' ? '选择表情' : 'Pick Emoji';

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        title={title}
        style={{
          background: 'none', border: 'none', cursor: 'pointer', fontSize: 18,
          padding: '2px 6px', borderRadius: 6, color: 'var(--text-muted)',
          transition: 'color 0.2s',
        }}
        onMouseEnter={e => e.target.style.color = 'var(--text-primary)'}
        onMouseLeave={e => e.target.style.color = 'var(--text-muted)'}
      >😀</button>
    );
  }

  return (
    <div ref={ref} style={{
      position: 'absolute', bottom: '100%', left: 0, zIndex: 100010,
      background: 'var(--bg-secondary)', border: '1px solid var(--border)',
      borderRadius: 12, padding: 10, minWidth: 260, maxWidth: 300,
      boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{title}</span>
        <button onClick={() => setOpen(false)} style={{
          background: 'none', border: 'none', color: 'var(--text-muted)',
          cursor: 'pointer', fontSize: 14, padding: '0 4px',
        }}>✕</button>
      </div>
      <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
        {Object.keys(EMOJI_CATEGORIES).map(cat => (
          <button key={cat} onClick={() => setCategory(cat)} style={{
            background: category === cat ? 'var(--accent)' : 'var(--bg-card)',
            border: '1px solid var(--border)', borderRadius: 6, padding: '4px 8px',
            cursor: 'pointer', fontSize: 14, transition: 'background 0.15s',
          }}>{cat}</button>
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 2 }}>
        {EMOJI_CATEGORIES[category].map(emoji => (
          <button key={emoji} onClick={() => handleSelect(emoji)} style={{
            background: 'none', border: 'none', cursor: 'pointer', fontSize: 20,
            padding: 4, borderRadius: 6, transition: 'background 0.15s',
          }}
          onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-card)'}
          onMouseLeave={e => e.currentTarget.style.background = 'none'}
          >{emoji}</button>
        ))}
      </div>
    </div>
  );
}