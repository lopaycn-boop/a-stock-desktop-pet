import React, { useState, useEffect } from 'react';

const STORAGE_KEY = 'potato_settings';

const DEFAULTS = {
  soundVolume: 0.5,
  soundEnabled: true,
  notificationsEnabled: true,
  ttsMuted: false,
  wakeWordEnabled: false,
  alwaysOnTop: true,
  opacity: 1.0,
  autoStart: true,
  riskStopLossPct: 5,
  riskTakeProfitPct: 10,
  riskMaxPositions: 3,
  riskMode: 'conservative',
};

function loadSettings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch (e) {}
  return { ...DEFAULTS };
}

function saveSettings(s) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(s)); } catch (e) {}
}

export default function SettingsPanel({ onClose, wakeListening, toggleWakeWord, alwaysOnTop, onToggleAlwaysOnTop, messages, sendPacket }) {
  const [s, setS] = useState(loadSettings);

  const update = (key, val) => {
    const next = { ...s, [key]: val };
    setS(next);
    saveSettings(next);
    applySetting(key, val);
  };

  const applySetting = (key, val) => {
    if (key === 'alwaysOnTop' && window.potatoAPI?.setAlwaysOnTop) {
      window.potatoAPI.setAlwaysOnTop(val);
    }
    if (key === 'autoStart' && window.potatoAPI?.setAutoStart) {
      window.potatoAPI.setAutoStart(val);
    }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 9999, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: '#1a1a2e', borderRadius: 18, width: 360, maxHeight: '80vh', overflow: 'auto', padding: 0, boxShadow: '0 8px 32px rgba(0,0,0,0.5)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 18px', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
          <span style={{ fontSize: 16, fontWeight: 700, color: '#69f0ae' }}>⚙️ 设置</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#888', fontSize: 20, cursor: 'pointer', padding: '0 4px' }}>✕</button>
        </div>

        <div style={{ padding: '12px 18px' }}>
          <Section title="🔊 音效">
            <Toggle label="启用音效" value={s.soundEnabled} onChange={v => update('soundEnabled', v)} />
            {s.soundEnabled && (
              <Row label="音量">
                <input type="range" min="0" max="100" value={s.soundVolume * 100}
                  onChange={e => update('soundVolume', parseInt(e.target.value) / 100)}
                  style={{ width: '100%', accentColor: '#69f0ae' }} />
                <span style={{ fontSize: 12, color: '#aaa', marginLeft: 8 }}>{Math.round(s.soundVolume * 100)}%</span>
              </Row>
            )}
            <Toggle label="静音TTS语音" value={s.ttsMuted} onChange={v => update('ttsMuted', v)} />
          </Section>

          <Section title="🔔 通知">
            <Toggle label="桌面通知" value={s.notificationsEnabled} onChange={v => {
              update('notificationsEnabled', v);
              if (v && 'Notification' in window && Notification.permission === 'default') {
                Notification.requestPermission();
              }
            }} />
          </Section>

          <Section title="🎤 语音唤醒">
            <Toggle label={'语音唤醒（喊"小土豆"）'} value={wakeListening} onChange={() => toggleWakeWord()} />
            <div style={{ fontSize: 11, color: '#666', marginTop: 4 }}>
              {wakeListening ? '🟢 正在监听唤醒词' : '🔴 未启用'}
            </div>
          </Section>

          <Section title="🖥️ 窗口">
            <Toggle label="始终置顶" value={alwaysOnTop} onChange={() => {
              onToggleAlwaysOnTop();
              update('alwaysOnTop', !alwaysOnTop);
            }} />
            <Row label="透明度">
              <input type="range" min="20" max="100" value={s.opacity * 100}
                onChange={e => {
                  const v = parseInt(e.target.value) / 100;
                  update('opacity', v);
                  if (window.potatoAPI?.setOpacity) window.potatoAPI.setOpacity(v);
                }}
                style={{ width: '100%', accentColor: '#69f0ae' }} />
              <span style={{ fontSize: 12, color: '#aaa', marginLeft: 8 }}>{Math.round(s.opacity * 100)}%</span>
            </Row>
            <Toggle label="开机自启" value={s.autoStart} onChange={v => update('autoStart', v)} />
          </Section>

          <Section title="🛡️ 风控">
            <Row label="止损">
              <select value={s.riskStopLossPct} onChange={e => { const v = parseInt(e.target.value); update('riskStopLossPct', v); if (sendPacket) sendPacket({ type: 'update_risk', payload: { stop_loss_pct: v } }); }}
                style={{ background: '#222', color: '#ccc', border: '1px solid #444', borderRadius: 6, padding: '4px 8px', fontSize: 13 }}>
                <option value={3}>3%</option><option value={5}>5%</option><option value={8}>8%</option><option value={10}>10%</option>
              </select>
            </Row>
            <Row label="止盈">
              <select value={s.riskTakeProfitPct} onChange={e => { const v = parseInt(e.target.value); update('riskTakeProfitPct', v); if (sendPacket) sendPacket({ type: 'update_risk', payload: { take_profit_pct: v } }); }}
                style={{ background: '#222', color: '#ccc', border: '1px solid #444', borderRadius: 6, padding: '4px 8px', fontSize: 13 }}>
                <option value={5}>5%</option><option value={8}>8%</option><option value={10}>10%</option><option value={15}>15%</option><option value={20}>20%</option>
              </select>
            </Row>
            <Row label="最多持仓">
              <select value={s.riskMaxPositions} onChange={e => { const v = parseInt(e.target.value); update('riskMaxPositions', v); if (sendPacket) sendPacket({ type: 'update_risk', payload: { max_positions: v } }); }}
                style={{ background: '#222', color: '#ccc', border: '1px solid #444', borderRadius: 6, padding: '4px 8px', fontSize: 13 }}>
                <option value={1}>1只</option><option value={2}>2只</option><option value={3}>3只</option><option value={5}>5只</option>
              </select>
            </Row>
            <Row label="模式">
              <select value={s.riskMode} onChange={e => { update('riskMode', e.target.value); if (sendPacket) sendPacket({ type: 'update_risk', payload: { risk_mode: e.target.value } }); }}
                style={{ background: '#222', color: '#ccc', border: '1px solid #444', borderRadius: 6, padding: '4px 8px', fontSize: 13 }}>
                <option value="conservative">稳健</option><option value="moderate">均衡</option><option value="aggressive">激进</option>
              </select>
            </Row>
          </Section>

          <Section title="💾 数据">
            <button onClick={() => {
              if (!messages || messages.length === 0) return;
              const lines = messages.map(m => {
                const ts = m.ts ? new Date(m.ts).toLocaleString() : '';
                const prefix = { user: '你', assistant: '土豆', system: '系统', image: '图片' }[m.type] || m.type;
                return `[${ts}] ${prefix}: ${typeof m.content === 'string' ? m.content : ''}`;
              });
              const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `potato-chat-${new Date().toISOString().slice(0, 10)}.txt`;
              a.click();
              URL.revokeObjectURL(url);
            }} style={{
              width: '100%', padding: '8px', borderRadius: 8, border: '1px solid rgba(105,240,174,0.3)',
              background: 'rgba(105,240,174,0.08)', color: '#69f0ae', cursor: 'pointer', fontSize: 13,
            }}>
              📥 导出聊天记录 ({messages ? messages.length : 0}条)
            </button>
          </Section>

          <div style={{ fontSize: 11, color: '#555', textAlign: 'center', marginTop: 12 }}>
            小土豆 AI操盘桌宠 v1.5.0 · 设置自动保存
          </div>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#e0e0e0', marginBottom: 6 }}>{title}</div>
      {children}
    </div>
  );
}

function Toggle({ label, value, onChange }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0' }}>
      <span style={{ fontSize: 13, color: '#ccc' }}>{label}</span>
      <button onClick={() => onChange(!value)}
        style={{
          width: 44, height: 24, borderRadius: 12, border: 'none', cursor: 'pointer',
          background: value ? '#69f0ae' : '#444', position: 'relative', transition: 'background 0.2s',
        }}>
        <div style={{
          width: 18, height: 18, borderRadius: '50%', background: '#fff', position: 'absolute',
          top: 3, left: value ? 23 : 3, transition: 'left 0.2s',
        }} />
      </button>
    </div>
  );
}

function Row({ label, children }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
      <span style={{ fontSize: 13, color: '#ccc', minWidth: 50 }}>{label}</span>
      {children}
    </div>
  );
}

export { loadSettings, saveSettings, DEFAULTS };