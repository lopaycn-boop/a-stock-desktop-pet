import React, { useState, useRef, useEffect } from 'react';

export default function VoiceInput({ onAudioCaptured, onRecordStart, disabled }) {
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);

  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop());
      }
    };
  }, []);

  const startRecording = async () => {
    if (disabled || isRecording) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      if (onRecordStart) onRecordStart();
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        if (blob.size > 0) onAudioCaptured(blob);
        stream.getTracks().forEach(t => t.stop());
        streamRef.current = null;
        setIsRecording(false);
      };
      recorder.start();
      setIsRecording(true);
    } catch (err) {
      console.warn('麦克风不可用:', err.message);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
    }
  };

  const handleClick = () => {
    if (isRecording) stopRecording();
    else startRecording();
  };

  return (
    <button
      className={`icon-button ${isRecording ? 'recording' : ''}`}
      onClick={handleClick}
      disabled={disabled}
      title={isRecording ? '点击停止' : '点击说话'}
      style={{
        backgroundColor: isRecording ? '#ff4d4f' : 'transparent',
        color: isRecording ? 'white' : 'inherit',
        border: isRecording ? 'none' : '1px solid rgba(255,255,255,0.3)',
        transition: 'all 0.2s',
        minWidth: '36px',
        cursor: disabled ? 'not-allowed' : 'pointer',
        borderRadius: '50%',
        fontSize: '16px',
      }}
    >
      {isRecording ? '⏹' : '🎤'}
    </button>
  );
}