import React, { useState, useEffect, useCallback } from 'react';

const THEMES = {
  dark: {
    '--bg-primary': '#0f0c29',
    '--bg-secondary': '#1a1a2e',
    '--bg-tertiary': '#16213e',
    '--bg-card': 'rgba(255,255,255,0.05)',
    '--bg-card-hover': 'rgba(255,255,255,0.08)',
    '--bg-input': 'rgba(255,255,255,0.06)',
    '--text-primary': '#f0f0f0',
    '--text-secondary': 'rgba(255,255,255,0.7)',
    '--text-muted': 'rgba(255,255,255,0.4)',
    '--accent': '#69f0ae',
    '--accent-secondary': '#4fc3f7',
    '--border': 'rgba(255,255,255,0.1)',
    '--shadow': 'rgba(0,0,0,0.3)',
    '--msg-user': 'rgba(105,240,174,0.12)',
    '--msg-assistant': 'rgba(79,195,247,0.08)',
    '--msg-system': 'rgba(255,255,255,0.04)',
    '--msg-error': 'rgba(255,82,82,0.15)',
    '--msg-success': 'rgba(105,240,174,0.15)',
    '--msg-warning': 'rgba(255,193,7,0.15)',
    '--msg-trade': 'rgba(79,195,247,0.15)',
  },
  light: {
    '--bg-primary': '#f5f5f9',
    '--bg-secondary': '#ffffff',
    '--bg-tertiary': '#eef0f5',
    '--bg-card': 'rgba(0,0,0,0.03)',
    '--bg-card-hover': 'rgba(0,0,0,0.06)',
    '--bg-input': 'rgba(0,0,0,0.04)',
    '--text-primary': '#1a1a2e',
    '--text-secondary': 'rgba(0,0,0,0.65)',
    '--text-muted': 'rgba(0,0,0,0.38)',
    '--accent': '#00c853',
    '--accent-secondary': '#0091ea',
    '--border': 'rgba(0,0,0,0.1)',
    '--shadow': 'rgba(0,0,0,0.08)',
    '--msg-user': 'rgba(0,200,83,0.1)',
    '--msg-assistant': 'rgba(0,145,234,0.07)',
    '--msg-system': 'rgba(0,0,0,0.03)',
    '--msg-error': 'rgba(255,23,68,0.1)',
    '--msg-success': 'rgba(0,200,83,0.1)',
    '--msg-warning': 'rgba(255,160,0,0.1)',
    '--msg-trade': 'rgba(0,145,234,0.1)',
  },
};

function getSystemTheme() {
  try {
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  } catch { return 'dark'; }
}

export default function useTheme(defaultTheme = 'dark') {
  const [theme, setThemeState] = useState(() => {
    try {
      const saved = localStorage.getItem('potato_theme');
      if (saved === 'dark' || saved === 'light' || saved === 'auto') return saved;
    } catch {}
    return defaultTheme;
  });

  useEffect(() => {
    try { localStorage.setItem('potato_theme', theme); } catch {}
    const effective = theme === 'auto' ? getSystemTheme() : theme;
    const vars = THEMES[effective] || THEMES.dark;
    const root = document.documentElement;
    for (const [k, v] of Object.entries(vars)) {
      root.style.setProperty(k, v);
    }
    root.setAttribute('data-theme', effective);
  }, [theme]);

  useEffect(() => {
    if (theme !== 'auto') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = () => setThemeState('auto');
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [theme]);

  const setTheme = useCallback((t) => {
    setThemeState(t);
  }, []);

  const effectiveTheme = theme === 'auto' ? getSystemTheme() : theme;
  const cycleTheme = useCallback(() => {
    const order = ['dark', 'light', 'auto'];
    setThemeState(order[(order.indexOf(theme) + 1) % order.length]);
  }, [theme]);

  return { theme, effectiveTheme, setTheme, cycleTheme, themes: Object.keys(THEMES) };
}