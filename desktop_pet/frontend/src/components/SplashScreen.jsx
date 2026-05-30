import React, { useEffect, useState } from 'react';

const SPLASH_STAGES = [
  { id: 'init', label: '正在初始化...', icon: '🥔' },
  { id: 'backend', label: '连接后端...', icon: '🔗' },
  { id: 'ws', label: '建立通道...', icon: '📡' },
  { id: 'live2d', label: '加载模型...', icon: '🎭' },
  { id: 'ready', label: '就绪！', icon: '✨' },
];

export default function SplashScreen({ stage = 'init', progress = 0 }) {
  const [dots, setDots] = useState('');
  useEffect(() => {
    const t = setInterval(() => setDots(d => d.length >= 3 ? '' : d + '.'), 400);
    return () => clearInterval(t);
  }, []);

  const idx = SPLASH_STAGES.findIndex(s => s.id === stage);
  const current = SPLASH_STAGES[Math.min(idx >= 0 ? idx : 0, SPLASH_STAGES.length - 1)];

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 999999,
      background: 'linear-gradient(135deg, #0f0c29 0%, #1a1a2e 50%, #16213e 100%)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      color: '#fff', fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif',
    }}>
      <div style={{
        fontSize: 72, marginBottom: 24,
        animation: 'splashBounce 1.2s ease-in-out infinite',
      }}>
        {current.icon}
      </div>
      <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: 1 }}>
        小土豆 AI操盘桌宠
      </h1>
      <p style={{ margin: '8px 0 32px', fontSize: 14, color: 'rgba(255,255,255,0.6)' }}>
        {current.label}{dots}
      </p>
      <div style={{
        width: 200, height: 4, borderRadius: 2,
        background: 'rgba(255,255,255,0.1)', overflow: 'hidden',
      }}>
        <div style={{
          height: '100%', borderRadius: 2,
          background: 'linear-gradient(90deg, #69f0ae, #4fc3f7)',
          width: `${Math.min(progress, 100)}%`,
          transition: 'width 0.4s ease',
        }} />
      </div>
      <style>{`
        @keyframes splashBounce {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-12px); }
        }
      `}</style>
    </div>
  );
}