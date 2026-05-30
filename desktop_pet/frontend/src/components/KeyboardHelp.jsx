import React from 'react';

const SHORTCUTS = [
  { keys: ['Ctrl', 'K'], desc: '命令面板', descEn: 'Command Palette' },
  { keys: ['Ctrl', 'Enter'], desc: '发送消息', descEn: 'Send message' },
  { keys: ['Esc'], desc: '关闭聊天/面板', descEn: 'Close chat/panel' },
  { keys: ['Ctrl', '1-9'], desc: '快捷操作', descEn: 'Quick actions' },
  { keys: ['?'], desc: '快捷键帮助', descEn: 'Keyboard help' },
  { keys: ['Ctrl', 'L'], desc: '切换语言', descEn: 'Toggle language' },
  { keys: ['Ctrl', 'D'], desc: '切换主题', descEn: 'Toggle theme' },
  { keys: ['Ctrl', 'F'], desc: '搜索聊天', descEn: 'Search chat' },
  { keys: ['Ctrl', 'E'], desc: '导出聊天', descEn: 'Export chat' },
  { keys: ['Shift', 'Enter'], desc: '换行', descEn: 'New line' },
];

export default function KeyboardHelp({ lang = 'zh', onClose }) {
  return (
    <div
      role="dialog" aria-label={lang === 'zh' ? '快捷键' : 'Keyboard Shortcuts'}
      style={{
        position: 'fixed', inset: 0, zIndex: 999999,
        background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: 380, maxHeight: '80vh', background: 'var(--bg-secondary)',
          borderRadius: 16, border: '1px solid var(--border)',
          boxShadow: '0 20px 60px var(--shadow)', overflow: 'auto', padding: '24px',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0, color: 'var(--text-primary)', fontSize: 18 }}>
            ⌨️ {lang === 'zh' ? '快捷键' : 'Shortcuts'}
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 18, cursor: 'pointer' }}>✕</button>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {SHORTCUTS.map((s, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
              <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
                {lang === 'zh' ? s.desc : s.descEn}
              </span>
              <div style={{ display: 'flex', gap: 4 }}>
                {s.keys.map((k, ki) => (
                  <span key={ki} style={{
                    background: 'var(--bg-card)', border: '1px solid var(--border)',
                    borderRadius: 4, padding: '2px 8px', fontSize: 12, color: 'var(--accent)',
                    fontFamily: 'monospace',
                  }}>
                    {k}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}