import React, { useState, useCallback, useMemo } from 'react';

const SUGGESTIONS_MAP = {
  '行情': [
    { label: '📈 大盘走势', msg: '今天大盘走势如何' },
    { label: '🔥 热门板块', msg: '哪些板块今天表现最好' },
    { label: '📉 跌幅榜', msg: '今天跌幅最大的股票有哪些' },
  ],
  '分析': [
    { label: '🔍 个股分析', msg: '帮我详细分析一下最近值得关注的股票' },
    { label: '📋 基本面', msg: '这只股票基本面怎么样' },
    { label: '📊 技术面', msg: '从技术面看现在是买入时机吗' },
  ],
  '操作': [
    { label: '💰 查余额', msg: '__broker_balance__' },
    { label: '📦 查持仓', msg: '帮我看看持仓情况' },
    { label: '🔀 切模式', msg: '__broker_switch__' },
  ],
  '复盘': [
    { label: '📝 今日复盘', msg: '帮我做一下今天的交易复盘' },
    { label: '📒 本周总结', msg: '这周交易表现怎么样' },
    { label: '🎯 明日策略', msg: '明天有什么操作建议' },
  ],
};

export default function QuickReplyChips({ onSend, lastMessageType }) {
  const [expanded, setExpanded] = useState(null);

  const categories = useMemo(() => {
    if (lastMessageType === 'trade') return ['操作', '复盘'];
    if (lastMessageType === 'system') return ['行情'];
    return ['行情', '分析', '操作', '复盘'];
  }, [lastMessageType]);

  const handleClick = useCallback((msg) => {
    if (msg.startsWith('__')) {
      onSend(msg);
    } else {
      onSend(msg);
    }
    setExpanded(null);
  }, [onSend]);

  const visibleChips = useMemo(() => {
    if (expanded) return SUGGESTIONS_MAP[expanded] || [];
    return categories.map(cat => {
      const items = SUGGESTIONS_MAP[cat];
      return items ? items[0] : null;
    }).filter(Boolean);
  }, [expanded, categories]);

  if (!visibleChips.length) return null;

  return (
    <div style={{
      display: 'flex', flexWrap: 'wrap', gap: 6, padding: '4px 12px 8px',
      maxHeight: expanded ? 120 : 40, overflow: 'hidden', transition: 'max-height 0.2s',
    }}>
      {!expanded && categories.map(cat => (
        <button key={cat} onClick={() => setExpanded(cat)} style={{
          fontSize: 11, padding: '3px 8px', borderRadius: 12,
          border: '1px solid var(--border)', background: 'var(--bg-card)',
          color: 'var(--text-muted)', cursor: 'pointer', transition: 'all 0.15s',
        }}>
          {cat} ▾
        </button>
      ))}
      {visibleChips.map((chip, i) => (
        <button key={chip.label + i} onClick={() => handleClick(chip.msg)} style={{
          fontSize: 12, padding: '4px 10px', borderRadius: 14,
          border: 'none', background: 'var(--accent)', opacity: 0.85,
          color: expanded ? '#1a1a2e' : 'var(--text-primary)', cursor: 'pointer',
          fontWeight: 500, transition: 'all 0.15s',
        }}>
          {chip.label}
        </button>
      ))}
      {expanded && (
        <button onClick={() => setExpanded(null)} style={{
          fontSize: 11, padding: '3px 8px', borderRadius: 12,
          border: '1px solid var(--border)', background: 'transparent',
          color: 'var(--text-muted)', cursor: 'pointer',
        }}>
          ✕ 收起
        </button>
      )}
    </div>
  );
}