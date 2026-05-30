import React, { useState, useEffect, useRef, useCallback } from 'react';

const CHART_COLORS = {
  up: '#69f0ae',
  down: '#ff5252',
  ma5: '#ffd740',
  ma10: '#4fc3f7',
  ma20: '#e040fb',
  grid: 'rgba(255,255,255,0.06)',
  crosshair: 'rgba(255,255,255,0.3)',
  volume: 'rgba(79,195,247,0.3)',
};

function drawCandle(ctx, x, open, close, high, low, w) {
  const isUp = close >= open;
  const color = isUp ? CHART_COLORS.up : CHART_COLORS.down;
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  const bodyTop = Math.min(open, close);
  const bodyH = Math.max(Math.abs(close - open), 1);
  ctx.fillRect(x - w / 2, bodyTop, w, bodyH);
  ctx.beginPath();
  ctx.moveTo(x, high);
  ctx.lineTo(x, bodyTop);
  ctx.moveTo(x, bodyTop + bodyH);
  ctx.lineTo(x, low);
  ctx.stroke();
}

export default function StockChart({ data = [], symbol = '上证指数', width = 360, height = 220 }) {
  const canvasRef = useRef(null);
  const [hoverIdx, setHoverIdx] = useState(null);
  const [chartType, setChartType] = useState('candle');

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data.length) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    const padding = { top: 20, right: 50, bottom: 30, left: 10 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;
    const visibleData = data.slice(-60);
    if (!visibleData.length) return;

    const prices = visibleData.flatMap(d => [d.high, d.low, d.open, d.close]).filter(Boolean);
    const minP = Math.min(...prices);
    const maxP = Math.max(...prices);
    const range = maxP - minP || 1;
    const scaleY = (v) => padding.top + chartH - ((v - minP) / range) * chartH;
    const barW = chartW / visibleData.length;

    // Grid
    ctx.strokeStyle = CHART_COLORS.grid;
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();
      const price = maxP - (range / 4) * i;
      ctx.fillStyle = 'rgba(255,255,255,0.4)';
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText(price.toFixed(2), width - 4, y + 4);
    }

    if (chartType === 'candle') {
      visibleData.forEach((d, i) => {
        const x = padding.left + barW * i + barW / 2;
        drawCandle(ctx, x, scaleY(d.open), scaleY(d.close), scaleY(d.high), scaleY(d.low), Math.max(barW * 0.6, 2));
      });
    } else {
      ctx.strokeStyle = CHART_COLORS.up;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      visibleData.forEach((d, i) => {
        const x = padding.left + barW * i + barW / 2;
        const y = scaleY(d.close);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    // Volume bars
    const maxVol = Math.max(...visibleData.map(d => d.volume || 0), 1);
    const volH = 25;
    visibleData.forEach((d, i) => {
      if (!d.volume) return;
      const x = padding.left + barW * i;
      const h = (d.volume / maxVol) * volH;
      ctx.fillStyle = d.close >= d.open ? 'rgba(105,240,174,0.2)' : 'rgba(255,82,82,0.2)';
      ctx.fillRect(x, height - padding.bottom - h, Math.max(barW - 1, 1), h);
    });

    // Hover crosshair
    if (hoverIdx !== null && hoverIdx >= 0 && hoverIdx < visibleData.length) {
      const d = visibleData[hoverIdx];
      const x = padding.left + barW * hoverIdx + barW / 2;
      ctx.strokeStyle = CHART_COLORS.crosshair;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(x, padding.top);
      ctx.lineTo(x, height - padding.bottom);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }, [data, width, height, chartType, hoverIdx]);

  const handleMouseMove = useCallback((e) => {
    const canvas = canvasRef.current;
    if (!canvas || !data.length) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const padding = { left: 10, right: 50 };
    const chartW = width - padding.left - padding.right;
    const visibleData = data.slice(-60);
    const barW = chartW / visibleData.length;
    const idx = Math.floor((x - padding.left) / barW);
    setHoverIdx(idx >= 0 && idx < visibleData.length ? idx : null);
  }, [data, width]);

  const handleMouseLeave = useCallback(() => setHoverIdx(null), []);

  const visibleData = data.slice(-60);
  const hoverData = hoverIdx !== null && hoverIdx < visibleData.length ? visibleData[hoverIdx] : null;
  const lastData = visibleData[visibleData.length - 1];
  const change = lastData ? ((lastData.close - lastData.open) / lastData.open * 100).toFixed(2) : '0.00';
  const isUp = lastData ? lastData.close >= lastData.open : true;

  return (
    <div style={{ background: 'var(--bg-card)', borderRadius: 12, padding: 12, border: '1px solid var(--border)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <div>
          <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>{symbol}</span>
          {lastData && (
            <span style={{ fontSize: 14, fontWeight: 700, marginLeft: 8, color: isUp ? CHART_COLORS.up : CHART_COLORS.down }}>
              {lastData.close?.toFixed(2)}
              <span style={{ fontSize: 12, marginLeft: 4 }}>{isUp ? '+' : ''}{change}%</span>
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {['candle', 'line'].map(t => (
            <button key={t} onClick={() => setChartType(t)} style={{
              fontSize: 11, padding: '2px 8px', borderRadius: 6, border: 'none', cursor: 'pointer',
              background: chartType === t ? 'var(--accent)' : 'var(--bg-card-hover)',
              color: chartType === t ? '#1a1a2e' : 'var(--text-muted)',
            }}>
              {t === 'candle' ? '📊K线' : '📈走势'}
            </button>
          ))}
        </div>
      </div>
      {hoverData && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
          开{hoverData.open?.toFixed(2)} 高{hoverData.high?.toFixed(2)} 低{hoverData.low?.toFixed(2)} 收{hoverData.close?.toFixed(2)} 量{(hoverData.volume || 0) > 10000 ? ((hoverData.volume / 10000).toFixed(1) + '万') : hoverData.volume}
        </div>
      )}
      <canvas
        ref={canvasRef}
        style={{ width, height, cursor: 'crosshair', display: 'block' }}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      />
    </div>
  );
}