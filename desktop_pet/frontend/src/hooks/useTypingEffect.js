import { useState, useRef, useCallback, useEffect } from 'react';

export default function useTypingEffect() {
  const [displayedText, setDisplayedText] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const fullTextRef = useRef('');
  const indexRef = useRef(0);
  const timerRef = useRef(null);

  const startTyping = useCallback((text, speed = 20) => {
    fullTextRef.current = text;
    indexRef.current = 0;
    setDisplayedText('');
    setIsTyping(true);

    clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      indexRef.current += 1;
      if (indexRef.current >= fullTextRef.current.length) {
        clearInterval(timerRef.current);
        setDisplayedText(fullTextRef.current);
        setIsTyping(false);
        return;
      }
      setDisplayedText(fullTextRef.current.slice(0, indexRef.current));
    }, speed);

    return () => clearInterval(timerRef.current);
  }, []);

  const skipToEnd = useCallback(() => {
    clearInterval(timerRef.current);
    setDisplayedText(fullTextRef.current);
    setIsTyping(false);
  }, []);

  useEffect(() => {
    return () => clearInterval(timerRef.current);
  }, []);

  return { displayedText, isTyping, startTyping, skipToEnd };
}