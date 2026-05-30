import React, { useState, useCallback } from 'react';

const PRESETS = [
  { id: 'conservative', label: '🛡️ 稳健', desc: '止损5%/止盈8%/最多2只', stopLoss: 5, takeProfit: 8, maxPositions: 2 },
  { id: 'balanced', label: '⚖️ 均衡', desc: '止损5%/止盈10%/最多3只', stopLoss: 5, takeProfit: 10, maxPositions: 3 },
  { id: 'aggressive', label: '🔥 激进', desc: '止损8%/止盈20%/最多5只', stopLoss: 8, takeProfit: 20, maxPositions: 5 },
];

const CUSTOM_INDICATORS = [
  { id: 'ma', label: '均线', desc: 'MA5/10/20交叉信号' },
  { id: 'macd', label: 'MACD', desc: '金叉死叉信号' },
  { id: 'rsi', label: 'RSI', desc: '超买超卖信号' },
  { id: 'kdj', label: 'KDJ', desc: '随机指标信号' },
  { id: 'boll', label: '布林', desc: '布林带突破信号' },
  { id: 'vol', label: '量能', desc: '放量缩量信号' },
];

export default function StrategyEditor({ riskConfig = {}, onApply, lang = 'zh' }) {
  const [mode, setMode] = useState(riskConfig.mode || 'balanced');
  const [stopLoss, setStopLoss] = useState(riskConfig.stopLoss || 5);
  const [takeProfit, setTakeProfit] = useState(riskConfig.takeProfit || 10);
  const [maxPositions, setMaxPositions] = useState(riskConfig.maxPositions || 3);
  const [indicators, setIndicators] = useState(['ma', 'vol']);
  const [tradingHours, setTradingHours] = useState({ start: '09:30', end: '15:00' });

  const labels = lang === 'zh'
    ? { title: '🎯 策略编辑器', preset: '预设策略', custom: '自定义', stopLoss: '止损%', takeProfit: '止盈%', maxPos: '最多持仓', indicators: '分析指标', hours: '交易时段', apply: '应用策略', reset: '重置' }
    : { title: '🎯 Strategy Editor', preset: 'Presets', custom: 'Custom', stopLoss: 'Stop%', takeProfit: 'Profit%', maxPos: 'Max Pos', indicators: 'Indicators', hours: 'Hours', apply: 'Apply', reset: 'Reset' };

  const handlePreset = useCallback((preset) => {
    setMode(preset.id);
    setStopLoss(preset.stopLoss);
    setTakeProfit(preset.takeProfit);
    setMaxPositions(preset.maxPositions);
  }, []);

  const handleApply = useCallback(() => {
    onApply?.({ mode, stopLoss, takeProfit, maxPositions, indicators, tradingHours });
  }, [mode, stopLoss, takeProfit, maxPositions, indicators, tradingHours, onApply]);

  const toggleIndicator = useCallback((id) => {
    setIndicators(prev => prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]);
  }, []);

  return (
    <div style={{ padding: 12 }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 15, color: 'var(--text-primary)' }}>
        {labels.title}
      </h3>

      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>{labels.preset}</div>
        <div style={{ display: 'flex', gap: 6 }}>
          {PRESETS.map(p => (
            <button key={p.id} onClick={() => handlePreset(p)} style={{
              flex: 1, padding: '8px 4px', borderRadius: 8, border: mode === p.id ? '2px solid var(--accent)' : '1px solid var(--border)',
              background: mode === p.id ? 'rgba(105,240,174,0.12)' : 'var(--bg-card)',
              color: mode === p.id ? 'var(--accent)' : 'var(--text-secondary)', cursor: 'pointer', textAlign: 'center',
            }}>
              <div style={{ fontSize: 14 }}>{p.label}</div>
              <div style={{ fontSize: 10, marginTop: 2, opacity: 0.7 }}>{p.desc}</div>
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 12 }}>
        <div style={{ background: 'var(--bg-card)', borderRadius: 8, padding: '6px 10px' }}>
          <label style={{ fontSize: 10, color: 'var(--text-muted)' }}>{labels.stopLoss}</label>
          <input type="number" value={stopLoss} onChange={e => setStopLoss(Number(e.target.value))} min={1} max={20} step={0.5} style={{
            width: '100%', background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 4,
            padding: '4px 6px', color: '#ff5252', fontSize: 14, fontWeight: 700, textAlign: 'center',
          }} />
        </div>
        <div style={{ background: 'var(--bg-card)', borderRadius: 8, padding: '6px 10px' }}>
          <label style={{ fontSize: 10, color: 'var(--text-muted)' }}>{labels.takeProfit}</label>
          <input type="number" value={takeProfit} onChange={e => setTakeProfit(Number(e.target.value))} min={1} max={50} step={1} style={{
            width: '100%', background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 4,
            padding: '4px 6px', color: '#69f0ae', fontSize: 14, fontWeight: 700, textAlign: 'center',
          }} />
        </div>
        <div style={{ background: 'var(--bg-card)', borderRadius: 8, padding: '6px 10px' }}>
          <label style={{ fontSize: 10, color: 'var(--text-muted)' }}>{labels.maxPos}</label>
          <input type="number" value={maxPositions} onChange={e => setMaxPositions(Number(e.target.value))} min={1} max={10} step={1} style={{
            width: '100%', background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 4,
            padding: '4px 6px', color: 'var(--text-primary)', fontSize: 14, fontWeight: 700, textAlign: 'center',
          }} />
        </div>
      </div>

      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>{labels.indicators}</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {CUSTOM_INDICATORS.map(ind => (
            <button key={ind.id} onClick={() => toggleIndicator(ind.id)} title={ind.desc} style={{
              padding: '4px 10px', borderRadius: 12, fontSize: 12, cursor: 'pointer',
              border: indicators.includes(ind.id) ? '1px solid var(--accent)' : '1px solid var(--border)',
              background: indicators.includes(ind.id) ? 'rgba(105,240,174,0.15)' : 'var(--bg-card)',
              color: indicators.includes(ind.id) ? 'var(--accent)' : 'var(--text-muted)',
            }}>
              {ind.label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{labels.hours}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input type="time" value={tradingHours.start} onChange={e => setTradingHours(h => ({ ...h, start: e.target.value }))} style={{
            background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 4,
            padding: '3px 6px', color: 'var(--text-primary)', fontSize: 12,
          }} />
          <span style={{ color: 'var(--text-muted)' }}>—</span>
          <input type="time" value={tradingHours.end} onChange={e => setTradingHours(h => ({ ...h, end: e.target.value }))} style={{
            background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 4,
            padding: '3px 6px', color: 'var(--text-primary)', fontSize: 12,
          }} />
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={handleApply} style={{
          flex: 1, padding: '10px', borderRadius: 10, border: 'none', cursor: 'pointer',
          background: 'var(--accent)', color: '#1a1a2e', fontWeight: 700, fontSize: 14,
        }}>
          ✅ {labels.apply}
        </button>
        <button onClick={() => handlePreset(PRESETS[1])} style={{
          padding: '10px 16px', borderRadius: 10, border: '1px solid var(--border)', cursor: 'pointer',
          background: 'transparent', color: 'var(--text-muted)', fontSize: 12,
        }}>
          {labels.reset}
        </button>
      </div>
    </div>
  );
}