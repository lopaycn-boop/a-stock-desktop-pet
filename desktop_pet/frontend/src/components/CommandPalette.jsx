import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';

const COMMANDS = [
  { id: 'market', icon: '📈', label: '查看行情', labelEn: 'Market Overview', msg: '帮我看看今天A股行情' },
  { id: 'hot', icon: '🔥', label: '热门板块', labelEn: 'Hot Sectors', msg: '今天有什么热点板块' },
  { id: 'analyze', icon: '🔬', label: '个股分析', labelEn: 'Stock Analysis', msg: '帮我分析最近值得关注的股票' },
  { id: 'balance', icon: '💰', label: '查余额', labelEn: 'Check Balance', msg: '__broker_balance__' },
  { id: 'positions', icon: '📦', label: '查持仓', labelEn: 'Positions', msg: '帮我看看持仓情况' },
  { id: 'switch_mode', icon: '🔀', label: '切换模式', labelEn: 'Switch Mode', msg: '__broker_switch__' },
  { id: 'review', icon: '📝', label: '今日复盘', labelEn: 'Daily Review', msg: '帮我做一下今天的交易复盘' },
  { id: 'pick', icon: '🎯', label: '智能选股', labelEn: 'Smart Pick', msg: '__iwencai_pick__' },
  { id: 'sentiment', icon: '📡', label: '舆情分析', labelEn: 'Sentiment', msg: '__trendradar__' },
  { id: 'keys', icon: '🔑', label: '管理密钥', labelEn: 'Manage Keys', msg: '__vault__' },
  { id: 'billing', icon: '💳', label: '计费面板', labelEn: 'Billing', msg: '__billing_dashboard__' },
  { id: 'settings', icon: '⚙️', label: '设置', labelEn: 'Settings', msg: '__settings__' },
  { id: 'history', icon: '📊', label: '交易记录', labelEn: 'Trade History', msg: '__trade_history__' },
  { id: 'update', icon: '🆙', label: '检查更新', labelEn: 'Check Update', msg: '__check_updates__' },
  { id: 'export', icon: '💾', label: '导出聊天', labelEn: 'Export Chat', action: 'export' },
  { id: 'clear', icon: '🗑️', label: '清空聊天', labelEn: 'Clear Chat', action: 'clear' },
  { id: 'theme', icon: '🎨', label: '切换主题', labelEn: 'Toggle Theme', action: 'theme' },
  { id: 'lang', icon: '🌐', label: '切换语言', labelEn: 'Toggle Language', action: 'lang' },
];

export default function CommandPalette({ onSend, onAction, lang = 'zh' }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const inputRef = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setOpen(o => !o);
        setQuery('');
        setSelected(0);
      }
      if (e.key === 'Escape' && open) {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open]);

  useEffect(() => {
    if (open && inputRef.current) inputRef.current.focus();
  }, [open]);

  const filtered = useMemo(() => {
    if (!query.trim()) return COMMANDS;
    const q = query.toLowerCase();
    return COMMANDS.filter(c =>
      c.label.toLowerCase().includes(q) ||
      c.labelEn.toLowerCase().includes(q) ||
      c.id.includes(q)
    );
  }, [query]);

  useEffect(() => { setSelected(0); }, [query]);

  const handleSelect = useCallback((cmd) => {
    if (cmd.action) {
      onAction(cmd.action);
    } else {
      onSend(cmd.msg);
    }
    setOpen(false);
    setQuery('');
  }, [onSend, onAction]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelected(s => Math.min(s + 1, filtered.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSelected(s => Math.max(s - 1, 0)); }
    else if (e.key === 'Enter' && filtered[selected]) { handleSelect(filtered[selected]); }
  }, [filtered, selected, handleSelect]);

  if (!open) return null;

  return (
    <div
      role="dialog" aria-label={lang === 'zh' ? '命令面板' : 'Command Palette'}
      style={{
        position: 'fixed', inset: 0, zIndex: 999999,
        background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: '20vh',
      }}
      onClick={() => { setOpen(false); }}
    >
      <div
        style={{
          width: 420, maxHeight: 400, background: 'var(--bg-secondary)',
          borderRadius: 16, border: '1px solid var(--border)',
          boxShadow: '0 20px 60px var(--shadow)', overflow: 'hidden',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
          <span style={{ fontSize: 16, marginRight: 8 }}>⌘</span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={lang === 'zh' ? '输入命令或搜索...' : 'Type a command or search...'}
            style={{
              flex: 1, background: 'transparent', border: 'none',
              color: 'var(--text-primary)', fontSize: 15, outline: 'none',
            }}
          />
          <span style={{ fontSize: 11, color: 'var(--text-muted)', background: 'var(--bg-card)', padding: '2px 6px', borderRadius: 4 }}>ESC</span>
        </div>
        <div style={{ maxHeight: 300, overflowY: 'auto', padding: '4px 0' }}>
          {filtered.length === 0 && (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              {lang === 'zh' ? '没有匹配的命令' : 'No matching commands'}
            </div>
          )}
          {filtered.map((cmd, i) => (
            <button
              key={cmd.id}
              onClick={() => handleSelect(cmd)}
              onMouseEnter={() => setSelected(i)}
              style={{
                display: 'flex', alignItems: 'center', gap: 10, width: '100%',
                padding: '8px 16px', background: i === selected ? 'var(--bg-card-hover)' : 'transparent',
                border: 'none', color: 'var(--text-primary)', cursor: 'pointer',
                fontSize: 14, textAlign: 'left',
              }}
            >
              <span style={{ fontSize: 18, width: 24, textAlign: 'center' }}>{cmd.icon}</span>
              <span style={{ flex: 1 }}>{lang === 'zh' ? cmd.label : cmd.labelEn}</span>
              {i === selected && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>↵</span>}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}