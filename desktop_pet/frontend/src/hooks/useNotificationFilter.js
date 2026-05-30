import { useState, useCallback } from 'react';

const PRIORITY_LEVELS = {
  trade: { label: { zh: '交易', en: 'Trade' }, icon: '💰', color: '#69f0ae' },
  risk: { label: { zh: '风险', en: 'Risk' }, icon: '🛑', color: '#ff5252' },
  info: { label: { zh: '信息', en: 'Info' }, icon: 'ℹ️', color: '#448aff' },
  system: { label: { zh: '系统', en: 'System' }, icon: '⚙️', color: '#ffd740' },
};

export default function useNotificationFilter({ storageKey = 'potato_notif_filters' } = {}) {
  const [filters, setFilters] = useState(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      return saved ? JSON.parse(saved) : { trade: true, risk: true, info: true, system: true };
    } catch {
      return { trade: true, risk: true, info: true, system: true };
    }
  });

  const toggle = useCallback((key) => {
    setFilters(prev => {
      const next = { ...prev, [key]: !prev[key] };
      localStorage.setItem(storageKey, JSON.stringify(next));
      return next;
    });
  }, [storageKey]);

  const shouldShow = useCallback((type) => {
    return filters[type] !== false;
  }, [filters]);

  const classify = useCallback((msg) => {
    if (!msg) return 'info';
    const text = (msg.content || msg.text || '').toLowerCase();
    if (/买入|卖出|止损|止盈|持仓|仓位|清仓|加仓|减仓|buy|sell|position/.test(text)) return 'trade';
    if (/风险|警示|警告|预警|risk|危险|暴跌|涨停/.test(text)) return 'risk';
    if (/系统|版本|更新|重启|连接|system|version|update/.test(text)) return 'system';
    return 'info';
  }, []);

  return { filters, toggle, shouldShow, classify, levels: PRIORITY_LEVELS };
}