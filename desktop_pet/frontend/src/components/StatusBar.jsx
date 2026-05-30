import React, { useState, useEffect, useCallback } from 'react';

export default function StatusBar({ systemStatus, connected, currentModel, lang = 'zh' }) {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const l = lang === 'zh'
    ? { connected: '已连接', disconnected: '断开', demo: '演示', keys: '密钥', memory: '记忆', uptime: '运行' }
    : { connected: 'Connected', disconnected: 'Offline', demo: 'Demo', keys: 'Keys', memory: 'Memory', uptime: 'Uptime' };

  const uptime = systemStatus?.uptime_seconds
    ? `${Math.floor(systemStatus.uptime_seconds / 3600)}h${Math.floor((systemStatus.uptime_seconds % 3600) / 60)}m`
    : '--';

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8, padding: '3px 10px',
      background: 'var(--bg-card)', borderRadius: 8, fontSize: 10,
      color: 'var(--text-muted)', flexShrink: 0,
    }}>
      <span style={{
        display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
        background: connected ? '#69f0ae' : '#ff5252',
        boxShadow: connected ? '0 0 4px #69f0ae' : '0 0 4px #ff5252',
      }} />
      <span>{connected ? l.connected : l.disconnected}</span>
      {systemStatus?.data_sources && (
        <>
          <span style={{ color: 'var(--border)' }}>|</span>
          <span>{systemStatus.data_sources.demo_mode ? '📋' + l.demo : `🟢${systemStatus.data_sources.active_providers || 0}${l.keys}`}</span>
        </>
      )}
      {currentModel && (
        <>
          <span style={{ color: 'var(--border)' }}>|</span>
          <span>{currentModel.split('-')[0]}</span>
        </>
      )}
      <span style={{ color: 'var(--border)' }}>|</span>
      <span>{l.uptime}: {uptime}</span>
      <span style={{ color: 'var(--border)' }}>|</span>
      <span>{time.toLocaleTimeString(lang === 'zh' ? 'zh-CN' : 'en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
    </div>
  );
}