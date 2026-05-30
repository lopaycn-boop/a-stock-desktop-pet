import { useState, useCallback, useRef, useEffect } from 'react';

const MIN_WIDTH = 280;
const MAX_WIDTH = 600;
const STORAGE_KEY = 'potato_chat_width';

export default function useChatResize(defaultWidth = 380) {
  const [width, setWidth] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const w = parseInt(saved, 10);
        if (w >= MIN_WIDTH && w <= MAX_WIDTH) return w;
      }
    } catch {}
    return defaultWidth;
  });

  const dragging = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(0);

  const onMouseDown = useCallback((e) => {
    e.preventDefault();
    dragging.current = true;
    startX.current = e.clientX;
    startWidth.current = width;
    document.body.style.cursor = 'ew-resize';
    document.body.style.userSelect = 'none';
  }, [width]);

  useEffect(() => {
    const onMouseMove = (e) => {
      if (!dragging.current) return;
      const delta = startX.current - e.clientX;
      const newWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth.current + delta));
      setWidth(newWidth);
    };
    const onMouseUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      try { localStorage.setItem(STORAGE_KEY, String(width)); } catch {}
    };
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [width]);

  return { width, resizeHandleProps: { onMouseDown }, isDragging: dragging };
}