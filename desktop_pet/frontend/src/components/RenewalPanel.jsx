import React from 'react';

export default function RenewalPanel({ data, onClose, onConfirmPayment }) {
  if (!data) return null;

  const {
    wallet_address = '',
    wallet_label = 'USDT-TRC20',
    total_renewal_cny = 0,
    current_balance_cny = 0,
    balance_sufficient = false,
    items = [],
    qr_code = '',
    payment_note = '',
  } = data;

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.6)', zIndex: 10000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={onClose}>
      <div style={{
        background: '#1a1a2e', borderRadius: '16px', padding: '24px',
        maxWidth: '400px', width: '90%', maxHeight: '85vh', overflowY: 'auto',
        color: '#e0e0e0', fontFamily: 'system-ui, -apple-system, sans-serif',
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h3 style={{ margin: 0, color: balance_sufficient ? '#4CAF50' : '#ffd700', fontSize: '18px' }}>
            {balance_sufficient ? '✅ 续费成功' : '💳 续费支付'}
          </h3>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: '#888', fontSize: '20px',
            cursor: 'pointer', lineHeight: 1,
          }}>✕</button>
        </div>

        {balance_sufficient ? (
          <div style={{ textAlign: 'center', padding: '24px 0' }}>
            <div style={{ fontSize: '48px', marginBottom: '12px' }}>🎉</div>
            <div style={{ fontSize: '16px', color: '#4CAF50', marginBottom: '8px' }}>
              已自动从余额扣款
            </div>
            <div style={{ fontSize: '14px', color: '#888' }}>
              当前余额: ¥{typeof current_balance_cny === 'number' ? current_balance_cny.toFixed(2) : current_balance_cny}
            </div>
          </div>
        ) : (
          <>
            {qr_code && (
              <div style={{ textAlign: 'center', marginBottom: '16px' }}>
                <img src={qr_code} alt="USDT-TRC20 收款二维码"
                  style={{ width: '180px', height: '180px', borderRadius: '8px', border: '2px solid #333' }}
                  onClick={e => e.stopPropagation()} />
                <div style={{ fontSize: '11px', color: '#888', marginTop: '4px' }}>
                  扫描二维码支付 {wallet_label}
                </div>
              </div>
            )}

            <div style={{
              background: '#16213e', borderRadius: '10px', padding: '14px',
              marginBottom: '16px', wordBreak: 'break-all',
            }}>
              <div style={{ fontSize: '12px', color: '#888', marginBottom: '6px' }}>收款地址 ({wallet_label})</div>
              <div style={{
                fontSize: '12px', color: '#ffd700', fontFamily: 'monospace',
                background: '#0d1117', padding: '8px', borderRadius: '6px',
                userSelect: 'all',
              }}>
                {wallet_address}
              </div>
            </div>

            {items.length > 0 && (
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '13px', color: '#ff9800', marginBottom: '8px', fontWeight: 'bold' }}>
                  待续费服务
                </div>
                {items.map((item, i) => (
                  <div key={i} style={{
                    display: 'flex', justifyContent: 'space-between',
                    padding: '6px 10px', background: '#16213e', borderRadius: '6px', marginBottom: '3px',
                  }}>
                    <span style={{ fontSize: '13px' }}>{item.name}</span>
                    <span style={{ fontSize: '13px', color: '#ffd700' }}>
                      ¥{typeof item.price_cny === 'number' ? item.price_cny.toFixed(0) : item.price_cny}/月
                    </span>
                  </div>
                ))}
                <div style={{
                  display: 'flex', justifyContent: 'space-between',
                  padding: '8px 10px', marginTop: '6px',
                  background: '#1a2744', borderRadius: '6px', fontWeight: 'bold',
                }}>
                  <span style={{ fontSize: '14px' }}>合计</span>
                  <span style={{ fontSize: '14px', color: '#ffd700' }}>
                    ¥{typeof total_renewal_cny === 'number' ? total_renewal_cny.toFixed(2) : total_renewal_cny}
                  </span>
                </div>
              </div>
            )}

            <div style={{
              background: '#16213e', borderRadius: '10px', padding: '12px', marginBottom: '16px',
              textAlign: 'center',
            }}>
              <div style={{ fontSize: '12px', color: '#888' }}>当前余额</div>
              <div style={{ fontSize: '22px', fontWeight: 'bold', color: '#4CAF50' }}>
                ¥{typeof current_balance_cny === 'number' ? current_balance_cny.toFixed(2) : current_balance_cny}
              </div>
            </div>

            <button onClick={onConfirmPayment} style={{
              width: '100%', padding: '12px', borderRadius: '10px', fontSize: '15px',
              fontWeight: 'bold', background: '#4CAF50', color: '#fff',
              border: 'none', cursor: 'pointer', marginBottom: '8px',
            }}>
              ✅ 已付款，确认到账
            </button>
            <div style={{ fontSize: '11px', color: '#888', textAlign: 'center' }}>
              {payment_note || '付款后点击确认，系统将自动续费'}
            </div>
          </>
        )}
      </div>
    </div>
  );
}