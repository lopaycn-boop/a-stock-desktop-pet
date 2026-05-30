import { useState, useEffect, useCallback } from 'react';

const STORAGE_KEY = 'potato_chat_history';
const MAX_MESSAGES = 200;

function loadMessages() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.slice(-MAX_MESSAGES);
  } catch (e) {
    return [];
  }
}

function saveMessages(msgs) {
  try {
    const toSave = msgs.slice(-MAX_MESSAGES);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
  } catch (e) {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e2) {}
  }
}

export function usePersistentMessages() {
  const [messages, setMessagesInternal] = useState(loadMessages);

  const setMessages = useCallback((updater) => {
    setMessagesInternal((prev) => {
      const next = typeof updater === 'function' ? updater(prev) : updater;
      saveMessages(next);
      return next;
    });
  }, []);

  const clearMessages = useCallback(() => {
    setMessagesInternal([]);
    try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
  }, []);

  return { messages, setMessages, clearMessages };
}