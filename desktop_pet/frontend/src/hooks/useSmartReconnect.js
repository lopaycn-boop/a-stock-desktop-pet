import { useRef, useCallback } from 'react';

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30000;
const RECONNECT_MULTIPLIER = 2;

export default function useSmartReconnect({ connectFn, maxRetries = 20 } = {}) {
  const attemptRef = useRef(0);
  const timerRef = useRef(null);
  const connectedRef = useRef(false);

  const scheduleReconnect = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const delay = Math.min(
      RECONNECT_BASE_MS * Math.pow(RECONNECT_MULTIPLIER, attemptRef.current),
      RECONNECT_MAX_MS
    );
    const jitter = Math.random() * 500;
    const totalDelay = delay + jitter;
    console.log(`[smart-reconnect] Attempt ${attemptRef.current + 1}/${maxRetries} in ${Math.round(totalDelay)}ms`);
    timerRef.current = setTimeout(() => {
      attemptRef.current++;
      if (attemptRef.current <= maxRetries) {
        connectFn?.();
      } else {
        console.error('[smart-reconnect] Max retries reached, giving up.');
      }
    }, totalDelay);
  }, [connectFn, maxRetries]);

  const onConnected = useCallback(() => {
    attemptRef.current = 0;
    connectedRef.current = true;
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const onDisconnected = useCallback(() => {
    connectedRef.current = false;
    scheduleReconnect();
  }, [scheduleReconnect]);

  const reset = useCallback(() => {
    attemptRef.current = 0;
    connectedRef.current = false;
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const getAttempt = useCallback(() => attemptRef.current, []);

  return { onConnected, onDisconnected, reset, getAttempt, isConnected: () => connectedRef.current };
}