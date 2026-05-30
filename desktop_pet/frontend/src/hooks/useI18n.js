import { useState, useCallback } from 'react';
import { t as translate } from '../i18n/locales';

export default function useI18n(defaultLang = 'zh') {
  const [lang, setLang] = useState(() => {
    try {
      const saved = localStorage.getItem('potato_lang');
      if (saved === 'zh' || saved === 'en') return saved;
    } catch {}
    return defaultLang;
  });

  const switchLang = useCallback((newLang) => {
    setLang(newLang);
    try { localStorage.setItem('potato_lang', newLang); } catch {}
  }, []);

  const t = useCallback((key) => translate(key, lang), [lang]);

  return { lang, switchLang, t, isZh: lang === 'zh', isEn: lang === 'en' };
}