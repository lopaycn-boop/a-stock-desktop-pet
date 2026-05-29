import { useState, useRef, useCallback } from 'react';

export function useAudioQueue(live2dRef) {
  const [subtitle, setSubtitle] = useState("");
  const [isPlaying, setIsPlaying] = useState(false);
  const audioQueueRef = useRef([]);
  const isPlayingRef = useRef(false);
  const currentAudioRef = useRef(null);

  const playAudioBlob = (base64Data) => {
    return new Promise((resolve, reject) => {
      try {
        const byteCharacters = atob(base64Data);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
          byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        const blob = new Blob([byteArray], { type: 'audio/mpeg' });
        const url = URL.createObjectURL(blob);

        const audio = new Audio(url);
        currentAudioRef.current = audio;

        audio.onended = () => {
          URL.revokeObjectURL(url);
          currentAudioRef.current = null;
          resolve();
        };

        audio.onerror = (e) => {
          URL.revokeObjectURL(url);
          reject(e);
        };

        audio.play().catch(resolve);
      } catch (e) {
        reject(e);
      }
    });
  };

  const processQueue = useCallback(async () => {
    if (isPlayingRef.current || audioQueueRef.current.length === 0) return;

    isPlayingRef.current = true;
    setIsPlaying(true);
    const item = audioQueueRef.current.shift();

    try {
      if (item.expression && live2dRef.current) {
        live2dRef.current.showExpression(item.expression);
      }
      setSubtitle(item.text);

      if (item.audio_base64) {
        await playAudioBlob(item.audio_base64);
      } else {
        await new Promise(r => setTimeout(r, 1000 + item.text.length * 100));
      }
    } catch (err) {
      console.error("播放错误:", err);
    } finally {
      isPlayingRef.current = false;
      setIsPlaying(false);
      if (audioQueueRef.current.length > 0) {
        processQueue();
      } else {
        setSubtitle("");
        if (live2dRef.current) live2dRef.current.resetExpression();
      }
    }
  }, [live2dRef]);

  const queueAudioChunk = useCallback((chunk) => {
    audioQueueRef.current.push(chunk);
    processQueue();
  }, [processQueue]);

  const stopAudio = useCallback(() => {
    audioQueueRef.current = [];
    isPlayingRef.current = false;
    setIsPlaying(false);
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }
    setSubtitle("");
    if (live2dRef.current) live2dRef.current.resetExpression();
  }, [live2dRef]);

  return {
    subtitle,
    isPlaying,
    queueAudioChunk,
    stopAudio
  };
}