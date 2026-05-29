import React, { useState } from 'react';
import '../App.css';

const QUICK_KEYS = [
  { key: 'DEEPSEEK_API_KEY', label: 'DeepSeek Key', emoji: '🧠' },
  { key: 'EM_API_KEY', label: '东方财富 Key', emoji: '📊' },
  { key: 'IWENCAI_API_KEY', label: '问财 Key', emoji: '🎯' },
  { key: 'SILICON_API_KEY', label: 'SiliconFlow Key', emoji: '🔊' },
  { key: 'TELEGRAM_BOT_TOKEN', label: 'Telegram Bot', emoji: '✈️' },
];

const Sidebar = ({ isOpen, onClose, messages, sendPacket }) => {
  const [tab, setTab] = useState('chat');
  const [pasteValue, setPasteValue] = useState('');
  const [pasteMsg, setPasteMsg] = useState(null);

  const handlePasteStore = () => {
    const val = pasteValue.trim();
    if (!val) return;

    let keyName = '';
    if (/^sk-/.test(val)) keyName = 'DEEPSEEK_API_KEY';
    else if (val.length >= 20) keyName = 'MANUAL_KEY';

    if (!keyName) {
      setPasteMsg({ ok: false, text: '看起来不像密钥，直接粘贴就行~' });
      setTimeout(() => setPasteMsg(null), 2000);
      return;
    }

    sendPacket({ type: 'vault_store', payload: { key: keyName, value: val } });
    setPasteValue('');
    setPasteMsg({ ok: true, text: `🔐 ${keyName} 存好了！` });
    setTimeout(() => setPasteMsg(null), 2500);
  };

  const handleQuickKey = (keyName) => {
    const val = prompt(`粘贴你的 ${keyName}：`);
    if (val && val.trim()) {
      sendPacket({ type: 'vault_store', payload: { key: keyName, value: val.trim() } });
      setPasteMsg({ ok: true, text: `🔐 ${keyName} 存好了！` });
      setTimeout(() => setPasteMsg(null), 2500);
    }
  };

  return (
    <>
      {isOpen && <div className="sidebar-overlay" onClick={onClose} />}
      <div className={`sidebar ${isOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <div style={{ display: 'flex', gap: 4 }}>
            <button onClick={() => setTab('chat')} style={{ background: tab === 'chat' ? 'rgba(100,108,255,0.3)' : 'transparent', border: 'none', color: 'white', padding: '4px 10px', borderRadius: 6, cursor: 'pointer', fontSize: 13 }}>💬</button>
            <button onClick={() => setTab('vault')} style={{ background: tab === 'vault' ? 'rgba(100,108,255,0.3)' : 'transparent', border: 'none', color: 'white', padding: '4px 10px', borderRadius: 6, cursor: 'pointer', fontSize: 13 }}>🔐</button>
          </div>
          <button className="sidebar-close-btn" onClick={onClose}>&#215;</button>
        </div>

        {tab === 'chat' && (
          <div className="sidebar-content">
            {messages.length === 0 && (
              <div style={{ color: 'rgba(255,255,255,0.3)', textAlign: 'center', marginTop: 40, fontSize: 12 }}>
                点角色或 💬 开始聊天
              </div>
            )}
            {messages.slice(-50).map((msg, i) => (
              <div key={i} className={`sidebar-message ${msg.type}`}>
                <strong>{msg.type === 'user' ? '你' : msg.type === 'system' ? '📌' : '🥔'}：</strong>
                <span>{msg.content}</span>
              </div>
            ))}
          </div>
        )}

        {tab === 'vault' && (
          <div className="sidebar-content">
            <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12, marginBottom: 16, lineHeight: 1.6 }}>
              🔐 粘贴密钥 → 自动存入保险箱<br />不会出现在聊天里
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
              {QUICK_KEYS.map(qk => (
                <button key={qk.key} onClick={() => handleQuickKey(qk.key)} style={{
                  background: 'rgba(100,108,255,0.12)', border: '1px solid rgba(100,108,255,0.25)',
                  borderRadius: 10, padding: '10px 14px', color: 'white', cursor: 'pointer', textAlign: 'left',
                }}>
                  <span style={{ fontSize: 16 }}>{qk.emoji}</span> <span style={{ fontSize: 13, fontWeight: 600 }}>{qk.label}</span>
                  <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginLeft: 6 }}>点击粘贴</span>
                </button>
              ))}
            </div>

            <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: 14 }}>
              <textarea
                placeholder="直接粘贴密钥到这里..."
                value={pasteValue}
                onChange={e => setPasteValue(e.target.value)}
                rows={3}
                style={{
                  width: '100%', padding: '10px 12px', borderRadius: 10, fontSize: 13,
                  border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.05)',
                  color: 'white', resize: 'none', boxSizing: 'border-box',
                }}
              />
              <button
                onClick={handlePasteStore}
                disabled={!pasteValue.trim()}
                style={{
                  width: '100%', marginTop: 8, padding: '10px', borderRadius: 10, border: 'none',
                  background: pasteValue.trim() ? '#646cff' : 'rgba(255,255,255,0.1)',
                  color: pasteValue.trim() ? 'white' : 'rgba(255,255,255,0.3)',
                  cursor: pasteValue.trim() ? 'pointer' : 'not-allowed',
                  fontSize: 14, fontWeight: 600,
                }}
              >🔐 存入保险箱</button>
            </div>

            {pasteMsg && (
              <div style={{
                marginTop: 10, padding: '8px 14px', borderRadius: 10, fontSize: 13, textAlign: 'center',
                background: pasteMsg.ok ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                color: pasteMsg.ok ? '#4ade80' : '#f87171',
              }}>{pasteMsg.text}</div>
            )}

            <button
              onClick={() => sendPacket({ type: 'vault_status', payload: {} })}
              style={{
                width: '100%', marginTop: 12, padding: '8px', borderRadius: 10,
                border: '1px solid rgba(255,255,255,0.15)', background: 'transparent',
                color: 'rgba(255,255,255,0.5)', cursor: 'pointer', fontSize: 12,
              }}
            >📋 查看保险箱状态</button>
          </div>
        )}
      </div>
    </>
  );
};

export default Sidebar;