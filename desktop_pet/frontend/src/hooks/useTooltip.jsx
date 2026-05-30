import { useState, useCallback, useRef, useEffect } from 'react';

const TOOLTIP_DELAY = 400;

export default function useTooltip() {
  const [tooltip, setTooltip] = useState(null);
  const timerRef = useRef(null);

  const show = useCallback((text, x, y) => {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setTooltip({ text, x, y });
    }, TOOLTIP_DELAY);
  }, []);

  const hide = useCallback(() => {
    clearTimeout(timerRef.current);
    setTooltip(null);
  }, []);

  useEffect(() => () => clearTimeout(timerRef.current), []);

  const TooltipOverlay = tooltip ? (
    <div
      role="tooltip"
      style={{
        position: 'fixed', left: Math.min(tooltip.x, window.innerWidth - 200), top: tooltip.y - 32,
        zIndex: 999998, background: 'var(--bg-tertiary)', color: 'var(--text-primary)',
        padding: '4px 10px', borderRadius: 6, fontSize: 12, pointerEvents: 'none',
        boxShadow: '0 4px 12px var(--shadow)', border: '1px solid var(--border)',
        whiteSpace: 'nowrap', animation: 'ttIn 0.15s ease-out',
      }}
    >
      {tooltip.text}
      <style>{`@keyframes ttIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }`}</style>
    </div>
  ) : null;

  return { show, hide, TooltipOverlay };
}