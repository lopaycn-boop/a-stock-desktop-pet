import React from 'react';

export default function BillingPanel({ data, onClose, onRenew, onTopup, onConfirmPayment }) {
  if (!data) return null;

  const { providers = [], wallet = {}, summary_text = '', needs_payment_count = 0 } = data;
  const activeProviders = providers.filter(p => p.key_configured);
  const inactiveProviders = providers.filter(p => !p.key_configured);
  const balance = wallet.remaining_cny ?? wallet.balance_cny ?? 0;

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.6)', zIndex: 10000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={onClose}>
      <div style={{
        background: '#1a1a2e', borderRadius: '16px', padding: '24px',
        maxWidth: '420px', width: '90%', maxHeight: '80vh', overflowY: 'auto',
        color: '#e0e0e0', fontFamily: 'system-ui, -apple-system, sans-serif',
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h3 style={{ margin: 0, color: '#ffd700', fontSize: '18px' }}>💳 服务总览</h3>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: '#888', fontSize: '20px',
            cursor: 'pointer', lineHeight: 1,
          }}>✕</button>
        </div>

        <div style={{
          background: '#16213e', borderRadius: '12px', padding: '16px',
          marginBottom: '16px', textAlign: 'center',
        }}>
          <div style={{ fontSize: '13px', color: '#888', marginBottom: '4px' }}>账户余额</div>
          <div style={{ fontSize: '32px', fontWeight: 'bold', color: '#ffd700' }}>
            ¥{typeof balance === 'number' ? balance.toFixed(2) : balance}
          </div>
        </div>

        {activeProviders.length > 0 && (
          <div style={{ marginBottom: '16px' }}>
            <div style={{ fontSize: '13px', color: '#4CAF50', marginBottom: '8px', fontWeight: 'bold' }}>
              ✅ 已激活服务
            </div>
            {activeProviders.map(p => (
              <div key={p.provider} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '8px 12px', background: '#16213e', borderRadius: '8px', marginBottom: '4px',
              }}>
                <span style={{ fontSize: '13px' }}>{p.name}</span>
                <span style={{ fontSize: '13px', color: '#aaa' }}>
                  ¥{typeof p.total_cost_cny === 'number' ? p.total_cost_cny.toFixed(2) : p.total_cost_cny}/月
                </span>
              </div>
            ))}
          </div>
        )}

        {inactiveProviders.length > 0 && (
          <div style={{ marginBottom: '16px' }}>
            <div style={{ fontSize: '13px', color: '#ff9800', marginBottom: '8px', fontWeight: 'bold' }}>
              ⚠️ 待续费
            </div>
            {inactiveProviders.map(p => (
              <div key={p.provider} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '8px 12px', background: '#16213e', borderRadius: '8px', marginBottom: '4px',
              }}>
                <span style={{ fontSize: '13px' }}>{p.name}</span>
                <span style={{ fontSize: '13px', color: '#ff9800', fontWeight: 'bold' }}>
                  ¥{typeof p.cost_with_margin === 'number' ? p.cost_with_margin.toFixed(0) : p.cost_with_margin}/月
                </span>
              </div>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
          <button onClick={onRenew} style={{
            flex: 1, padding: '10px', borderRadius: '10px', fontSize: '14px', fontWeight: 'bold',
            background: needs_payment_count > 0 ? '#ff9800' : '#4CAF50', color: '#fff',
            border: 'none', cursor: 'pointer',
          }}>
            {needs_payment_count > 0 ? '🔄 续费' : '✅ 查看续费'}
          </button>
          <button onClick={() => onTopup(50)} style={{
            flex: 1, padding: '10px', borderRadius: '10px', fontSize: '14px',
            background: '#2196F3', color: '#fff', border: 'none', cursor: 'pointer',
          }}>
            💴 充值¥50
          </button>
          <button onClick={() => onTopup(100)} style={{
            flex: 1, padding: '10px', borderRadius: '10px', fontSize: '14px',
            background: '#1565C0', color: '#fff', border: 'none', cursor: 'pointer',
          }}>
            💴 充值¥100
          </button>
        </div>
      </div>
    </div>
  );
}