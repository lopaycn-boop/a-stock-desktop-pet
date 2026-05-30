export function renderMessageContent(content) {
  if (!content || typeof content !== 'string') return content;

  // First extract code blocks
  const codeBlockRegex = /```(\w*)\n?([\s\S]*?)```/g;
  const segments = [];
  let lastIndex = 0;
  let match;
  let key = 0;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: 'text', content: content.slice(lastIndex, match.index), key: key++ });
    }
    segments.push({ type: 'code', lang: match[1], content: match[2].trim(), key: key++ });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < content.length) {
    segments.push({ type: 'text', content: content.slice(lastIndex), key: key++ });
  }

  return segments.map(seg => {
    if (seg.type === 'code') {
      return (
        <div key={seg.key} style={{
          background: 'rgba(0,0,0,0.3)', borderRadius: 8, margin: '6px 0',
          overflow: 'hidden', border: '1px solid var(--border)',
        }}>
          {seg.lang && <div style={{
            fontSize: 10, color: 'var(--text-muted)', padding: '3px 10px',
            borderBottom: '1px solid var(--border)', background: 'rgba(0,0,0,0.2)',
          }}>{seg.lang}</div>}
          <pre style={{
            margin: 0, padding: '8px 12px', fontSize: 12, lineHeight: 1.5,
            overflowX: 'auto', color: 'var(--text-primary)', fontFamily: 'Consolas, Monaco, monospace',
          }}>
            <code>{seg.content}</code>
          </pre>
        </div>
      );
    }
    return <div key={seg.key}>{renderTextBlock(seg.content)}</div>;
  });
}

function renderTextBlock(content) {
  if (!content || typeof content !== 'string') return content;

  const lines = content.split('\n');
  const elements = [];
  let key = 0;

  for (const line of lines) {
    if (!line.trim()) {
      elements.push(<br key={key++} />);
      continue;
    }

    // Inline code: `code`
    let rendered = line;
    const inlineCodeRegex = /`([^`]+)`/g;
    if (inlineCodeRegex.test(rendered)) {
      const parts = [];
      let lastIdx = 0;
      inlineCodeRegex.lastIndex = 0;
      let m;
      while ((m = inlineCodeRegex.exec(rendered)) !== null) {
        if (m.index > lastIdx) parts.push(rendered.slice(lastIdx, m.index));
        parts.push(<code key={key++} style={{
          background: 'rgba(0,0,0,0.3)', padding: '1px 4px', borderRadius: 3,
          fontSize: '0.85em', fontFamily: 'Consolas, Monaco, monospace',
        }}>{m[1]}</code>);
        lastIdx = m.index + m[0].length;
      }
      if (lastIdx < rendered.length) parts.push(rendered.slice(lastIdx));
      elements.push(<div key={key++} style={{ lineHeight: 1.5 }}>{parts}</div>);
      continue;
    }

    // Bold: **text**
    const boldMatch = line.match(/\*\*(.+?)\*\*/g);
    if (boldMatch) {
      let remaining = line;
      const parts = [];
      for (const match of boldMatch) {
        const idx = remaining.indexOf(match);
        if (idx > 0) parts.push(remaining.slice(0, idx));
        parts.push(<strong key={key++}>{match.slice(2, -2)}</strong>);
        remaining = remaining.slice(idx + match.length);
      }
      if (remaining) parts.push(remaining);
      elements.push(<div key={key++} style={{ marginBottom: 2 }}>{parts}</div>);
      continue;
    }

    // Numbered list: 1. 2. etc
    if (/^\d+\.\s/.test(line.trim())) {
      elements.push(<div key={key++} style={{ paddingLeft: 12, marginBottom: 2, lineHeight: 1.5 }}>{line}</div>);
      continue;
    }

    // Bullet: · or - or •
    if (/^[·•]\s/.test(line.trim()) || /^-\s/.test(line.trim())) {
      elements.push(<div key={key++} style={{ paddingLeft: 12, marginBottom: 2, lineHeight: 1.5 }}>{line}</div>);
      continue;
    }

    // Emoji header lines
    if (/^[📌🟢🔴🟡👀📊🔬✅🛑⚠️🛡️💰💹📈📉🔥📅🔗🧠🔑💳🔄💽📋🥔]/.test(line.trim())) {
      elements.push(<div key={key++} style={{ fontWeight: 600, marginBottom: 4, lineHeight: 1.5 }}>{line}</div>);
      continue;
    }

    elements.push(<div key={key++} style={{ lineHeight: 1.5 }}>{line}</div>);
  }

  return elements;
}