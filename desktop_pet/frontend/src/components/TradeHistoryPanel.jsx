import React, { useState } from 'react';

export default function TradeHistoryPanel({ onClose, sendPacket, messages }) {
  const [tab, setTab] = useState('recent');
  const recentTrades = messages
    .filter(m => m.type === 'system' && (
      m.content.includes('交易提交成功') ||
      m.content.includes('交易被拦截') ||
      m.content.includes('贸易信号') ||
      m.content.includes('复盘') ||
      m.content.includes('选股分析')
    ))
    .slice(-30);

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 9998, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: '#1a1a2e', borderRadius: 18, width: 400, maxHeight: '80vh', overflow: 'auto', padding: 0, boxShadow: '0 8px 32px rgba(0,0,0,0.5)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 18px', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
          <span style={{ fontSize: 16, fontWeight: 700, color: '#4fc3f7' }}>📊 交易记录</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#888', fontSize: 20, cursor: 'pointer' }}>✕</button>
        </div>

        <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid rgba(255,255,255,0.1)', padding: '0 14px' }}>
          {[
            { key: 'recent', label: '最近' },
            { key: 'review', label: '今日复盘' },
            { key: 'history', label: '历史' },
          ].map(t => (
            <button key={t.key} onClick={() => {
              setTab(t.key);
              if (t.key === 'review') sendPacket({ type: 'trade_review', payload: { date: 'today' } });
              if (t.key === 'history') sendPacket({ type: 'review_history', payload: {} });
            }} style={{
              padding: '8px 16px', border: 'none', cursor: 'pointer',
              background: tab === t.key ? 'rgba(79,195,247,0.15)' : 'transparent',
              color: tab === t.key ? '#4fc3f7' : '#888', fontSize: 13, fontWeight: 600,
              borderBottom: tab === t.key ? '2px solid #4fc3f7' : '2px solid transparent',
            }}>
              {t.label}
            </button>
          ))}
        </div>

        <div style={{ padding: '12px 18px' }}>
          {tab === 'recent' && (
            recentTrades.length === 0 ? (
              <div style={{ color: '#666', textAlign: 'center', padding: 20 }}>暂无交易记录</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {recentTrades.map((msg, i) => (
                  <div key={i} style={{
                    background: 'rgba(255,255,255,0.04)', borderRadius: 8, padding: '8px 12px',
                    borderLeft: msg.content.includes('成功') ? '3px solid #69f0ae' : msg.content.includes('拦截') ? '3px solid #ff8a80' : '3px solid #4fc3f7',
                  }}>
                    <div style={{ fontSize: 11, color: '#555' }}>{msg.ts ? new Date(msg.ts).toLocaleTimeString() : ''}</div>
                    <div style={{ fontSize: 13, color: '#ddd', marginTop: 2 }}>{msg.content.slice(0, 120)}</div>
                  </div>
                ))}
              </div>
            )
          )}

          {tab === 'review' && (
            <div style={{ textAlign: 'center', color: '#888', padding: 20 }}>
              <div style={{ fontSize: 40, marginBottom: 8 }}>📋</div>
              <div>正在获取今日复盘...</div>
              <div style={{ fontSize: 12, color: '#555', marginTop: 8 }}>复盘结果将显示在聊天中</div>
            </div>
          )}

          {tab === 'history' && (
            <div style={{ textAlign: 'center', color: '#888', padding: 20 }}>
              <div style={{ fontSize: 40, marginBottom: 8 }}>📜</div>
              <div>正在加载历史记录...</div>
              <div style={{ fontSize: 12, color: '#555', marginTop: 8 }}>结果将显示在聊天中</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}