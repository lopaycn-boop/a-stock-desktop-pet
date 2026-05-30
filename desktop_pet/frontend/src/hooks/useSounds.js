const TRADE_SIGNAL_FREQ = 880;
const RISK_ALERT_FREQ = 440;
const DURATION_MS = 150;

let audioCtx = null;
let soundSettings = null;

function getSettings() {
  if (soundSettings) return soundSettings;
  try {
    const raw = localStorage.getItem('potato_settings');
    if (raw) soundSettings = JSON.parse(raw);
  } catch (e) {}
  if (!soundSettings) soundSettings = { soundEnabled: true, soundVolume: 0.5 };
  return soundSettings;
}

function getAudioCtx() {
  if (!audioCtx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) audioCtx = new AC();
  }
  return audioCtx;
}

function isSoundMuted() {
  const s = getSettings();
  return !s.soundEnabled;
}

function getVolume() {
  const s = getSettings();
  return s.soundVolume ?? 0.5;
}

export function playTradeSignal() {
  if (isSoundMuted()) return;
  const vol = getVolume();
  const ctx = getAudioCtx();
  if (!ctx) return;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = 'sine';
  osc.frequency.setValueAtTime(TRADE_SIGNAL_FREQ, ctx.currentTime);
  gain.gain.setValueAtTime(vol * 0.3, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + DURATION_MS / 1000);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(ctx.currentTime);
  osc.stop(ctx.currentTime + DURATION_MS / 1000);
}

export function playRiskAlert() {
  if (isSoundMuted()) return;
  const vol = getVolume();
  const ctx = getAudioCtx();
  if (!ctx) return;
  for (let i = 0; i < 3; i++) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'square';
    osc.frequency.setValueAtTime(RISK_ALERT_FREQ, ctx.currentTime + i * 0.15);
    gain.gain.setValueAtTime(vol * 0.2, ctx.currentTime + i * 0.15);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + i * 0.15 + 0.12);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(ctx.currentTime + i * 0.15);
    osc.stop(ctx.currentTime + i * 0.15 + 0.12);
  }
}

export function playChatNotification() {
  if (isSoundMuted()) return;
  const vol = getVolume();
  const ctx = getAudioCtx();
  if (!ctx) return;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = 'sine';
  osc.frequency.setValueAtTime(660, ctx.currentTime);
  osc.frequency.setValueAtTime(880, ctx.currentTime + 0.06);
  gain.gain.setValueAtTime(vol * 0.2, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.2);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(ctx.currentTime);
  osc.stop(ctx.currentTime + 0.2);
}

export function isTtsMuted() {
  const s = getSettings();
  return s.ttsMuted ?? false;
}