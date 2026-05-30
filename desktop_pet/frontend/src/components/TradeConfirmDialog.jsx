import React, { useState } from 'react';

export default function TradeConfirmDialog({ trade, onConfirm, onCancel, lang = 'zh' }) {
  const [confirmed, setConfirmed] = useState(false);
  const [checkRead, setCheckRead] = useState(false);

  if (!trade) return null;

  const l = lang === 'zh' ? {
    title: '⚠️ 交易确认',
    action: trade.action === 'BUY' ? '买入' : trade.action === 'SELL' ? '卖出' : trade.action,
    stock: '股票',
    price: '价格',
    amount: '数量',
    confidence: '置信度',
    confirm: '确认执行',
    cancel: '取消',
    risk: '风险提示',
    riskText: '自动交易有风险，请确保您了解可能的损失。',
    check: '我已了解风险并确认执行此交易',
    mode: '模式',
    dryRun: '模拟(不实际交易)',
    live: '实盘(真实交易)',
  } : {
    title: '⚠️ Trade Confirmation',
 action: trade.action === 'BUY' ? 'Buy' : trade.action === 'SELL' ? 'Sell' : trade.action,
    stock: 'Stock',
    price: 'Price',
    amount: 'Amount',
    confidence: 'Confidence',
    confirm: 'Confirm',
    cancel: 'Cancel',
    risk: 'Risk Notice',
    riskText: 'Auto-trading involves risk. Make sure you understand potential losses.',
    check: 'I understand the risk and confirm this trade',
    mode: 'Mode',
    dryRun: 'Simulation (no real trade)',
    live: 'Live (real trade)',
  };

  const isLive = trade.mode !== 'dry_run';
  const actionColor = trade.action === 'BUY' ? '#69f0ae' : '#ff5252';

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 200000,
      background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center',
      backdropFilter: 'blur(4px)',
    }} onClick={onCancel}>
      <div style={{
        background: 'var(--bg-secondary)', borderRadius: 16, border: '1px solid var(--border)',
        maxWidth: 360, width: '90%', padding: 20,
      }} onClick={e => e.stopPropagation()}>
        <h3 style={{ margin: '0 0 12px', fontSize: 16, color: actionColor }}>{l.title}</h3>

        <div style={{ background: 'var(--bg-card)', borderRadius: 10, padding: 12, marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{l.action}</span>
            <span style={{ fontWeight: 700, color: actionColor }}>{l.action}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{l.stock}</span>
            <span style={{ fontWeight: 600 }}>{trade.name || trade.code || '-'}</span>
          </div>
          {trade.price && <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{l.price}</span>
            <span>{trade.price}</span>
          </div>}
          {trade.amount && <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{l.amount}</span>
            <span>{trade.amount}</span>
          </div>}
          {trade.confidence && <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{l.confidence}</span>
            <span>{(trade.confidence * 100).toFixed(0)}%</span>
          </div>}
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{l.mode}</span>
            <span style={{ color: isLive ? '#ff5252' : '#69f0ae', fontWeight: 600 }}>
              {isLive ? `🔴 ${l.live}` : `🟢 ${l.dryRun}`}
            </span>
          </div>
        </div>

        {isLive && <div style={{
          background: 'rgba(255,82,82,0.1)', border: '1px solid rgba(255,82,82,0.3)',
          borderRadius: 8, padding: 10, marginBottom: 12,
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#ff5252', marginBottom: 4 }}>⚠️ {l.risk}</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{l.riskText}</div>
        </div>}

        <label style={{
          display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, cursor: 'pointer',
          fontSize: 12, color: 'var(--text-muted)',
        }}>
          <input type="checkbox" checked={checkRead} onChange={e => setCheckRead(e.target.checked)}
            style={{ accentColor: 'var(--accent)' }} />
          {l.check}
        </label>

        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={onCancel} style={{
            flex: 1, padding: 10, borderRadius: 10, border: '1px solid var(--border)',
            background: 'transparent', color: 'var(--text-primary)', cursor: 'pointer', fontSize: 13,
          }}>{l.cancel}</button>
          <button
            onClick={() => { setConfirmed(true); onConfirm(trade); }}
            disabled={!checkRead || confirmed}
            style={{
              flex: 1, padding: 10, borderRadius: 10, border: 'none',
              background: checkRead && !confirmed ? actionColor : 'var(--bg-card)',
              color: checkRead && !confirmed ? '#1a1a2e' : 'var(--text-muted)',
              cursor: checkRead && !confirmed ? 'pointer' : 'not-allowed', fontSize: 13, fontWeight: 600,
            }}
          >{confirmed ? '✓' : l.confirm}</button>
        </div>
      </div>
    </div>
  );
}