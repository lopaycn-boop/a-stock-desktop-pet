import React from 'react';
import useNotificationFilter from '../hooks/useNotificationFilter';

export default function NotifFilterPanel({ lang = 'zh' }) {
  const { filters, toggle, levels } = useNotificationFilter();

  const title = lang === 'zh' ? '🔔 通知过滤' : '🔔 Notification Filters';

  return (
    <div style={{ padding: 16 }}>
      <h3 style={{ margin: '0 0 10px', fontSize: 14, color: 'var(--text-primary)' }}>{title}</h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {Object.entries(levels).map(([key, level]) => (
          <label key={key} style={{
            display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer',
            padding: '6px 10px', borderRadius: 8, background: 'var(--bg-card)',
            border: '1px solid var(--border)', transition: 'opacity 0.2s',
            opacity: filters[key] ? 1 : 0.5,
          }}>
            <input
              type="checkbox"
              checked={filters[key]}
              onChange={() => toggle(key)}
              style={{ accentColor: level.color, width: 16, height: 16 }}
            />
            <span style={{ fontSize: 16 }}>{level.icon}</span>
            <span style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>
              {level.label[lang]}
            </span>
            <span style={{
              marginLeft: 'auto', fontSize: 10, padding: '2px 6px', borderRadius: 4,
              background: level.color + '22', color: level.color, fontWeight: 600,
            }}>
              {key.toUpperCase()}
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}