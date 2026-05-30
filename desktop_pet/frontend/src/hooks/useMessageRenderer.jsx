export function renderMessageContent(content) {
  if (!content || typeof content !== 'string') return content;

  const lines = content.split('\n');
  const elements = [];
  let key = 0;

  for (const line of lines) {
    if (!line.trim()) {
      elements.push(<br key={key++} />);
      continue;
    }

    // Bold: **text**
    const boldMatch = line.match(/\*\*(.+?)\*\*/g);
    if (boldMatch) {
      let rendered = line;
      const parts = [];
      let remaining = rendered;
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