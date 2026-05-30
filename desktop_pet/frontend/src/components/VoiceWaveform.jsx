import React, { useState, useRef, useEffect, useCallback } from 'react';

export default function VoiceWaveform({ isRecording, onStop }) {
  const canvasRef = useRef(null);
  const analyserRef = useRef(null);
  const streamRef = useRef(null);
  const animRef = useRef(null);
  const [volume, setVolume] = useState(0);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;

      const draw = () => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        const w = canvas.clientWidth;
        const h = canvas.clientHeight;
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        ctx.scale(dpr, dpr);

        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        analyser.getByteFrequencyData(dataArray);

        const avg = dataArray.reduce((a, b) => a + b, 0) / bufferLength;
        setVolume(Math.round(avg / 255 * 100));

        ctx.clearRect(0, 0, w, h);

        const barCount = 24;
        const barW = 3;
        const gap = (w - barCount * barW) / (barCount + 1);
        const centerY = h / 2;
        const t = Date.now() / 1000;

        for (let i = 0; i < barCount; i++) {
          const dataIdx = Math.floor(i / barCount * bufferLength);
          const amplitude = dataArray[dataIdx] / 255;
          const baseH = 3;
          const barH = baseH + amplitude * (h * 0.7);
          const idleWave = isRecording ? 0 : Math.sin(t * 3 + i * 0.5) * 4;
          const totalH = barH + idleWave;

          const x = gap + i * (barW + gap);
          const gradient = ctx.createLinearGradient(x, centerY - totalH / 2, x, centerY + totalH / 2);
          gradient.addColorStop(0, `rgba(105, 240, 174, ${0.4 + amplitude * 0.6})`);
          gradient.addColorStop(1, `rgba(79, 195, 247, ${0.3 + amplitude * 0.5})`);
          ctx.fillStyle = gradient;
          ctx.beginPath();
          ctx.roundRect(x, centerY - totalH / 2, barW, totalH, 1.5);
          ctx.fill();
        }

        if (isRecording) {
          animRef.current = requestAnimationFrame(draw);
        }
      };

      draw();
    } catch (err) {
      console.error('Mic error:', err);
    }
  }, [isRecording]);

  const stopRecording = useCallback(() => {
    if (animRef.current) cancelAnimationFrame(animRef.current);
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    if (analyserRef.current) analyserRef.current = null;
    setVolume(0);
    onStop?.();
  }, [onStop]);

  useEffect(() => {
    if (isRecording) startRecording();
    else stopRecording();
    return () => stopRecording();
  }, [isRecording, startRecording, stopRecording]);

  // Draw idle animation when not recording
  useEffect(() => {
    if (isRecording) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;

    const drawIdle = () => {
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, w, h);

      const barCount = 24;
      const barW = 3;
      const gap = (w - barCount * barW) / (barCount + 1);
      const centerY = h / 2;
      const t = Date.now() / 1000;

      for (let i = 0; i < barCount; i++) {
        const x = gap + i * (barW + gap);
        const barH = 3 + Math.sin(t * 2 + i * 0.4) * 3;
        ctx.fillStyle = 'rgba(255,255,255,0.15)';
        ctx.beginPath();
        ctx.roundRect(x, centerY - barH / 2, barW, barH, 1.5);
        ctx.fill();
      }
      animRef.current = requestAnimationFrame(drawIdle);
    };

    drawIdle();
    return () => cancelAnimationFrame(animRef.current);
  }, [isRecording]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, padding: '4px 0' }}>
      <canvas
        ref={canvasRef}
        style={{ width: 120, height: 28, borderRadius: 14, cursor: isRecording ? 'pointer' : 'default' }}
        onClick={isRecording ? stopRecording : undefined}
      />
      {isRecording && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10 }}>
          <div style={{ width: 40, height: 4, borderRadius: 2, background: 'var(--bg-card)', overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 2,
              background: volume > 80 ? '#ff5252' : volume > 40 ? '#ffd740' : '#69f0ae',
              width: `${volume}%`, transition: 'width 0.1s',
            }} />
          </div>
          <span style={{ color: 'var(--text-muted)' }}>🎤 {volume}%</span>
          <button onClick={stopRecording} style={{
            fontSize: 10, padding: '2px 8px', borderRadius: 10,
            background: '#ff5252', border: 'none', color: '#fff', cursor: 'pointer',
          }}>停止</button>
        </div>
      )}
    </div>
  );
}