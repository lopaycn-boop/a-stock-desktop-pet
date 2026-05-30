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

export default function SettingsPanel({ onClose, wakeListening, toggleWakeWord, alwaysOnTop, onToggleAlwaysOnTop }) {
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

          <div style={{ fontSize: 11, color: '#555', textAlign: 'center', marginTop: 12 }}>
            小土豆 AI操盘桌宠 v1.4.0 · 设置自动保存
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