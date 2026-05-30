import { useState, useEffect, useRef } from 'react';

export default function usePerformanceMonitor(intervalMs = 2000) {
  const [fps, setFps] = useState(0);
  const [memory, setMemory] = useState(0);
  const framesRef = useRef(0);
  const lastTimeRef = useRef(performance.now());
  const rafRef = useRef(null);

  useEffect(() => {
    let active = true;
    const countFrame = () => {
      if (!active) return;
      framesRef.current++;
      rafRef.current = requestAnimationFrame(countFrame);
    };
    countFrame();
    const timer = setInterval(() => {
      if (!active) return;
      const now = performance.now();
      const elapsed = (now - lastTimeRef.current) / 1000;
      setFps(Math.round(framesRef.current / elapsed));
      framesRef.current = 0;
      lastTimeRef.current = now;
      try {
        if (performance.memory) {
          setMemory(Math.round(performance.memory.usedJSHeapSize / 1048576));
        }
      } catch {}
    }, intervalMs);

    return () => {
      active = false;
      clearInterval(timer);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [intervalMs]);

  return { fps, memory };
}