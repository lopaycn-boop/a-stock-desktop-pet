import React, { useState, useMemo } from 'react';

const POSITIONS = [
  { symbol: '000001', name: '平安银行', shares: 500, cost: 12.50 },
  { symbol: '600519', name: '贵州茅台', shares: 10, cost: 1680.00 },
  { symbol: '300750', name: '宁德时代', shares: 100, cost: 185.30 },
  { symbol: '002594', name: '比亚迪', shares: 50, cost: 265.80 },
  { symbol: '601318', name: '中国平安', shares: 200, cost: 45.20 },
];

const MOCK_PRICES = { '000001': 13.20, '600519': 1720.50, '300750': 190.10, '002594': 275.60, '601318': 46.80 };

export default function PortfolioDashboard({ positions: externalPositions, prices: externalPrices, lang = 'zh' }) {
  const positions = externalPositions || POSITIONS;
  const prices = externalPrices || MOCK_PRICES;

  const totalCost = useMemo(() => positions.reduce((s, p) => s + p.shares * p.cost, 0), [positions]);
  const totalValue = useMemo(() => positions.reduce((s, p) => s + p.shares * (prices[p.symbol] || p.cost), 0), [positions]);
  const totalPnl = totalValue - totalCost;
  const totalPnlPct = totalCost > 0 ? (totalPnl / totalCost * 100) : 0;

  const sortedPositions = useMemo(() =>
    positions.map(p => {
      const curPrice = prices[p.symbol] || p.cost;
      const pnl = (curPrice - p.cost) * p.shares;
      const pnlPct = ((curPrice - p.cost) / p.cost * 100);
      const weight = (p.shares * curPrice) / totalValue * 100;
      return { ...p, curPrice, pnl, pnlPct, weight, value: p.shares * curPrice };
    }).sort((a, b) => b.value - a.value)
  , [positions, prices, totalValue]);

  const labels = lang === 'zh'
    ? { title: '持仓仪表盘', totalCost: '总成本', totalValue: '总市值', pnl: '盈亏', positions: '持仓明细', symbol: '代码', name: '名称', shares: '数量', cost: '成本', price: '现价', profit: '盈亏', weight: '占比', weightShort: '占比' }
    : { title: 'Portfolio', totalCost: 'Total Cost', totalValue: 'Market Value', pnl: 'P&L', positions: 'Holdings', symbol: 'Code', name: 'Name', shares: 'Qty', cost: 'Cost', price: 'Price', profit: 'P&L', weight: 'Weight', weightShort: 'Wt' };

  return (
    <div style={{ padding: 12 }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 15, color: 'var(--text-primary)' }}>
        📊 {labels.title}
      </h3>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 12 }}>
        <div style={{ background: 'var(--bg-card)', borderRadius: 8, padding: '8px 10px', textAlign: 'center' }}>
          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{labels.totalCost}</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>¥{totalCost.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</div>
        </div>
        <div style={{ background: 'var(--bg-card)', borderRadius: 8, padding: '8px 10px', textAlign: 'center' }}>
          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{labels.totalValue}</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>¥{totalValue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</div>
        </div>
        <div style={{ background: 'var(--bg-card)', borderRadius: 8, padding: '8px 10px', textAlign: 'center' }}>
          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{labels.pnl}</div>
          <div style={{ fontSize: 13, fontWeight: 700, color: totalPnl >= 0 ? '#69f0ae' : '#ff5252' }}>
            {totalPnl >= 0 ? '+' : ''}¥{totalPnl.toLocaleString(undefined, { maximumFractionDigits: 0 })} ({totalPnlPct >= 0 ? '+' : ''}{totalPnlPct.toFixed(2)}%)
          </div>
        </div>
      </div>

      <div style={{ background: 'var(--bg-card)', borderRadius: 8, overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '4fr 3fr 2fr 2fr 3fr 2fr', padding: '6px 10px', fontSize: 10, color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>
          <span>{labels.symbol}</span>
          <span style={{ textAlign: 'right' }}>{labels.cost}</span>
          <span style={{ textAlign: 'right' }}>{labels.price}</span>
          <span style={{ textAlign: 'right' }}>{lang === 'zh' ? '盈亏' : 'P&L'}</span>
          <span style={{ textAlign: 'right' }}>{labels.weightShort}</span>
          <span></span>
        </div>
        {sortedPositions.map((p, i) => (
          <div key={p.symbol} style={{
            display: 'grid', gridTemplateColumns: '4fr 3fr 2fr 2fr 3fr 2fr',
            padding: '5px 10px', fontSize: 12,
            borderBottom: i < sortedPositions.length - 1 ? '1px solid var(--border)' : 'none',
            background: hoverIdx === i ? 'var(--bg-card-hover)' : 'transparent',
          }}>
            <span>
              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{p.symbol}</span>
              <span style={{ fontSize: 10, color: 'var(--text-muted)', marginLeft: 4 }}>{p.name}</span>
            </span>
            <span style={{ textAlign: 'right', color: 'var(--text-secondary)' }}>{p.cost.toFixed(2)}</span>
            <span style={{ textAlign: 'right', color: p.pnl >= 0 ? '#69f0ae' : '#ff5252', fontWeight: 600 }}>{p.curPrice.toFixed(2)}</span>
            <span style={{ textAlign: 'right', color: p.pnl >= 0 ? '#69f0ae' : '#ff5252', fontSize: 11 }}>
              {p.pnlPct >= 0 ? '+' : ''}{p.pnlPct.toFixed(1)}%
            </span>
            <span style={{ textAlign: 'right' }}>
              <div style={{ background: 'var(--bg-card-hover)', borderRadius: 2, height: 6, position: 'relative', overflow: 'hidden' }}>
                <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${Math.min(p.weight, 100)}%`, background: p.pnl >= 0 ? '#69f0ae' : '#ff5252', borderRadius: 2, opacity: 0.7 }} />
              </div>
              <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>{p.weight.toFixed(1)}%</span>
            </span>
            <span style={{ fontSize: 10, color: 'var(--text-muted)', textAlign: 'right' }}>{p.shares}股</span>
          </div>
        ))}
      </div>
    </div>
  );
}

let hoverIdx = -1;