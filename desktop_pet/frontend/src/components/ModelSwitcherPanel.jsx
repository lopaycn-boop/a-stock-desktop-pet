import React, { useState, useCallback } from 'react';

const MODELS = [
  { id: 'deepseek-chat', name: 'DeepSeek', desc: '深度求索·灵敏度最高', tier: 1, color: '#69f0ae' },
  { id: 'liner', name: 'Liner', desc: 'Liner·英语能力强', tier: 2, color: '#4fc3f7' },
  { id: 'siliconflow', name: 'SiliconFlow', desc: '硅基流动·性价比高', tier: 3, color: '#ffd740' },
  { id: 'base44', name: 'Base44', desc: 'Base44·备用链路', tier: 3, color: '#ff9800' },
  { id: 'openai', name: 'OpenAI', desc: 'GPT·最强但最贵', tier: 4, color: '#e040fb' },
];

export default function ModelSwitcher({ currentModel, onSwitch, connected, lang = 'zh' }) {
  const [expanded, setExpanded] = useState(false);

  const labels = lang === 'zh'
    ? { title: '模型切换', tier: '优先级', active: '当前', offline: '离线', switchTo: '切换', latency: '延迟' }
    : { title: 'Model Switch', tier: 'Tier', active: 'Active', offline: 'Offline', switchTo: 'Switch', latency: 'Latency' };

  const handleSwitch = useCallback((model) => {
    onSwitch(model.id);
    setExpanded(false);
  }, [onSwitch]);

  const current = MODELS.find(m => m.id === currentModel) || MODELS[0];

  return (
    <div style={{ position: 'relative' }}>
      <button
        onClick={() => setExpanded(e => !e)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6, padding: '4px 10px',
          borderRadius: 14, border: `1px solid ${current.color}40`, background: `${current.color}15`,
          color: current.color, cursor: 'pointer', fontSize: 12,
        }}
      >
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: connected ? current.color : '#888', boxShadow: `0 0 6px ${current.color}` }} />
        {current.name}
        <span style={{ fontSize: 8 }}>▼</span>
      </button>

      {expanded && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, marginTop: 4,
          background: 'var(--bg-secondary)', border: '1px solid var(--border)',
          borderRadius: 12, boxShadow: '0 8px 32px var(--shadow)',
          minWidth: 240, zIndex: 1000, overflow: 'hidden',
        }}>
          <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)', fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
            {labels.title}
          </div>
          {MODELS.map(model => {
            const isActive = model.id === currentModel;
            return (
              <button
                key={model.id}
                onClick={() => handleSwitch(model)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                  padding: '8px 12px', border: 'none', cursor: 'pointer',
                  background: isActive ? `${model.color}15` : 'transparent',
                  borderBottom: '1px solid var(--border)',
                }}
                onMouseEnter={e => e.currentTarget.style.background = isActive ? `${model.color}20` : 'var(--bg-card-hover)'}
                onMouseLeave={e => e.currentTarget.style.background = isActive ? `${model.color}15` : 'transparent'}
              >
                <span style={{ width: 10, height: 10, borderRadius: '50%', background: model.color, flexShrink: 0, boxShadow: `0 0 4px ${model.color}60` }} />
                <div style={{ flex: 1, textAlign: 'left' }}>
                  <div style={{ fontSize: 13, fontWeight: isActive ? 600 : 400, color: 'var(--text-primary)' }}>
                    {model.name}
                    {isActive && <span style={{ marginLeft: 6, fontSize: 10, color: model.color, fontWeight: 600 }}>● {labels.active}</span>}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{model.desc}</div>
                </div>
                <span style={{
                  fontSize: 9, padding: '2px 6px', borderRadius: 4,
                  background: model.tier === 1 ? 'rgba(105,240,174,0.15)' : model.tier === 4 ? 'rgba(224,64,251,0.15)' : 'rgba(255,255,255,0.06)',
                  color: model.tier === 1 ? '#69f0ae' : model.tier === 4 ? '#e040fb' : 'var(--text-muted)',
                }}>
                  T{model.tier}
                </span>
              </button>
            );
          })}
          <div style={{ padding: '6px 12px', fontSize: 10, color: 'var(--text-muted)', textAlign: 'center' }}>
            {lang === 'zh' ? '5层自动故障转移 · T1最高优先' : '5-layer auto failover · T1 highest priority'}
          </div>
        </div>
      )}
    </div>
  );
}