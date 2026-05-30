import React from 'react';
import usePerformanceMonitor from '../hooks/usePerformanceMonitor';

export default function PerfMonitor({ lang = 'zh' }) {
  const { fps, memory } = usePerformanceMonitor(2000);

  const fpsColor = fps > 50 ? '#69f0ae' : fps > 30 ? '#ffd740' : '#ff5252';

  if (process.env.NODE_ENV === 'production' && !window.__POTATO_DEBUG__) return null;

  return (
    <div style={{
      position: 'fixed', bottom: 4, right: 4, zIndex: 999998,
      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
      borderRadius: 6, padding: '2px 6px', fontSize: 10, fontFamily: 'monospace',
      color: fpsColor, display: 'flex', gap: 6, pointerEvents: 'none',
    }}>
      <span>{fps} FPS</span>
      {memory > 0 && <span style={{ color: 'rgba(255,255,255,0.5)' }}>{memory}MB</span>}
    </div>
  );
}