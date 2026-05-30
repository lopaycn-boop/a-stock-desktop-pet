import React, { useState, useCallback, useEffect, useRef } from 'react';

let toastId = 0;
const TOAST_ICONS = {
  success: '✅',
  error: '❌',
  warning: '⚠️',
  info: 'ℹ️',
  trade: '📊',
};

export default function ToastContainer() {
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    const handler = (e) => {
      const { message, type = 'info', duration = 3000 } = e.detail || {};
      const id = ++toastId;
      setToasts(prev => [...prev, { id, message, type, duration }]);
      setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), duration);
    };
    window.addEventListener('potato-toast', handler);
    return () => window.removeEventListener('potato-toast', handler);
  }, []);

  const dismiss = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div style={{
      position: 'fixed', top: 12, right: 12, zIndex: 999998,
      display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 320,
      pointerEvents: 'none',
    }}>
      {toasts.map(t => (
        <div key={t.id} onClick={() => dismiss(t.id)} style={{
          pointerEvents: 'auto', cursor: 'pointer',
          background: 'var(--bg-card)', backdropFilter: 'blur(12px)',
          border: '1px solid var(--border)', borderRadius: 10,
          padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 8,
          fontSize: 13, color: 'var(--text-primary)',
          boxShadow: '0 4px 16px var(--shadow)',
          animation: 'toastIn 0.25s ease-out',
        }}>
          <span style={{ fontSize: 16 }}>{TOAST_ICONS[t.type] || TOAST_ICONS.info}</span>
          <span style={{ flex: 1, lineHeight: 1.4 }}>{t.message}</span>
        </div>
      ))}
      <style>{`
        @keyframes toastIn {
          from { opacity: 0; transform: translateX(20px); }
          to { opacity: 1; transform: translateX(0); }
        }
      `}</style>
    </div>
  );
}

export function showToast(message, type = 'info', duration = 3000) {
  window.dispatchEvent(new CustomEvent('potato-toast', { detail: { message, type, duration } }));
}