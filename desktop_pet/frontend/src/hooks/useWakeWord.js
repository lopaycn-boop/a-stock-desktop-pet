import { useRef, useEffect, useCallback, useState } from 'react';

const WAKE_WORDS = ['土豆', '小土豆', 'tudou', 'xiaotudou'];

export function useWakeWord({ onWake, enabled = true } = {}) {
  const recognitionRef = useRef(null);
  const enabledRef = useRef(enabled);
  const activeRef = useRef(false);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState('');
  const restartTimerRef = useRef(null);
  const streamRef = useRef(null);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const restartingRef = useRef(false);

  useEffect(() => { enabledRef.current = enabled; }, [enabled]);

  const stopWakeListener = useCallback(() => {
    activeRef.current = false;
    restartingRef.current = false;
    setListening(false);
    if (restartTimerRef.current) {
      clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
    try { recognitionRef.current?.stop(); } catch (_) {}
    recognitionRef.current = null;
  }, []);

  const startWakeListener = useCallback(() => {
    if (!enabledRef.current) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn('[wake] 浏览器不支持语音识别，语音唤醒不可用');
      setError('不支持语音识别');
      return;
    }

    stopWakeListener();

    try {
      const recognition = new SpeechRecognition();
      recognition.lang = 'zh-CN';
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 3;

      recognition.onstart = () => {
        activeRef.current = true;
        restartingRef.current = false;
        setListening(true);
        setError('');
        console.log('[wake] 语音监听已启动');
      };

      recognition.onresult = (event) => {
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i];
          for (let j = 0; j < result.length; j++) {
            const transcript = result[j].transcript.toLowerCase().trim();
            if (!transcript) continue;

            const hit = WAKE_WORDS.some(w => transcript.includes(w));
            if (hit) {
              console.log('[wake] 唤醒词命中:', transcript);
              recognition.stop();
              activeRef.current = false;
              setListening(false);
              if (onWake) onWake(transcript);
              return;
            }
          }
        }
      };

      recognition.onerror = (e) => {
        console.warn('[wake] 语音识别错误:', e.error);
        if (e.error === 'not-allowed') {
          setError('麦克风权限被拒绝');
          activeRef.current = false;
          setListening(false);
          return;
        }
        if (e.error === 'no-speech') {
          // 正常，没有检测到语音
        }
        // 其他错误（aborted, network 等）自动重启
      };

      recognition.onend = () => {
        activeRef.current = false;
        setListening(false);
        if (enabledRef.current && !restartingRef.current) {
          restartingRef.current = true;
          restartTimerRef.current = setTimeout(() => {
            restartingRef.current = false;
            if (enabledRef.current) {
              startWakeListener();
            }
          }, 500);
        }
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (e) {
      console.warn('[wake] 启动失败:', e);
      setError('启动失败');
    }
  }, [onWake, stopWakeListener]);

  const startWakeRecording = useCallback((sendPacket) => {
    return new Promise(async (resolve) => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        streamRef.current = stream;
        chunksRef.current = [];

        const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        recorderRef.current = recorder;

        const chunks = [];
        recorder.ondataavailable = (e) => {
          if (e.data.size > 0) chunks.push(e.data);
        };

        recorder.onstop = () => {
          const blob = new Blob(chunks, { type: 'audio/webm' });
          if (blob.size > 0) {
            const reader = new FileReader();
            reader.onload = () => {
              const base64 = reader.result.split(',')[1];
              sendPacket({ type: 'audio_input', payload: { audio_base64: base64, format: 'audio/webm' } });
            };
            reader.readAsDataURL(blob);
          }
          stream.getTracks().forEach(t => t.stop());
          streamRef.current = null;
          recorderRef.current = null;
          resolve();
        };

        recorder.start();
        setTimeout(() => {
          if (recorderRef.current === recorder && recorder.state === 'recording') {
            recorder.stop();
          }
        }, 5000);
      } catch (e) {
        console.warn('[wake] 录音失败:', e);
        resolve();
      }
    });
  }, []);

  const stopWakeRecording = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state === 'recording') {
      recorderRef.current.stop();
    }
  }, []);

  useEffect(() => {
    return () => {
      stopWakeListener();
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop());
      }
    };
  }, [stopWakeListener]);

  return {
    listening,
    error,
    startWakeListener,
    stopWakeListener,
    startWakeRecording,
    stopWakeRecording,
  };
}