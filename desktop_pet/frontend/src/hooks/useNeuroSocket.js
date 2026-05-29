import { useRef, useEffect, useCallback, useState } from 'react';

const WS_TOKEN = '';  // Set to match PET_WS_TOKEN env var if authentication is enabled

function buildWsUrl(baseUrl) {
  const url = new URL(baseUrl);
  if (WS_TOKEN) {
    url.searchParams.set('token', WS_TOKEN);
  }
  return url.toString();
}

export function useNeuroSocket(url, onMessage) {
  const wsRef = useRef(null);
  const onMessageRef = useRef(onMessage);
  const retryRef = useRef(0);
  const timerRef = useRef(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const connect = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }

    const ws = new WebSocket(WS_TOKEN ? buildWsUrl(url) : url);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("✅ Neuro Link Connected");
      retryRef.current = 0;
      setConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const packet = JSON.parse(event.data);
        if (onMessageRef.current) {
          onMessageRef.current(packet);
        }
      } catch (e) {
        console.error("WS Parse Error:", e);
      }
    };

    ws.onerror = (e) => console.error("WS Error:", e);

    ws.onclose = () => {
      console.log("❌ 连接断开，自动重连...");
      setConnected(false);
      const delay = Math.min(1000 * Math.pow(2, retryRef.current), 30000);
      retryRef.current += 1;
      timerRef.current = setTimeout(connect, delay);
    };
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.close();
    };
  }, [connect]);

  const sendPacket = useCallback((packet) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(packet));
    }
  }, []);

  return { sendPacket, connected };
}
