import React, { useState, useCallback } from 'react';

const EXPORT_KEYS = [
  'potato_settings', 'potato_theme', 'potato_lang', 'potato_onboarding_done',
  'potato_chat_history', 'potato_pinned', 'potato_lang',
];

export default function SettingsBackup({ onImport, lang = 'zh' }) {
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [message, setMessage] = useState('');

  const l = lang === 'zh'
    ? { title: '💾 设置备份与恢复', export: '导出设置', import: '导入设置', success: '成功！', error: '失败', noFile: '请选择文件', desc: '导出所有设置、聊天记录和置顶消息到文件，或从文件恢复。' }
    : { title: '💾 Settings Backup', export: 'Export Settings', import: 'Import Settings', success: 'Done!', error: 'Failed', noFile: 'Select a file', desc: 'Export all settings, chat history and pinned messages to a file, or restore from file.' };

  const handleExport = useCallback(() => {
    setExporting(true);
    setMessage('');
    try {
      const data = {};
      EXPORT_KEYS.forEach(key => {
        try {
          const val = localStorage.getItem(key);
          if (val) data[key] = JSON.parse(val);
        } catch { data[key] = localStorage.getItem(key); }
      });
      data._version = '1.17.0';
      data._exportTime = new Date().toISOString();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `potato-backup-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setMessage(`✅ ${l.export} ${l.success}`);
    } catch (e) {
      setMessage(`❌ ${l.export} ${l.error}: ${e.message}`);
    } finally {
      setExporting(false);
    }
  }, [l]);

  const handleImport = useCallback((e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setMessage('');
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target.result);
        let count = 0;
        Object.entries(data).forEach(([key, value]) => {
          if (key.startsWith('_')) return;
          try {
            localStorage.setItem(key, typeof value === 'object' ? JSON.stringify(value) : String(value));
            count++;
          } catch {}
        });
        setMessage(`✅ ${l.import} ${l.success} (${count} keys)`);
        onImport?.();
      } catch (err) {
        setMessage(`❌ ${l.import} ${l.error}: ${err.message}`);
      } finally {
        setImporting(false);
        e.target.value = '';
      }
    };
    reader.readAsText(file);
  }, [l, onImport]);

  return (
    <div style={{ padding: 16 }}>
      <h3 style={{ margin: '0 0 8px', fontSize: 15, color: 'var(--text-primary)' }}>{l.title}</h3>
      <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '0 0 16px' }}>{l.desc}</p>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <button onClick={handleExport} disabled={exporting} style={{
          flex: 1, padding: '10px', borderRadius: 10, border: 'none', cursor: exporting ? 'wait' : 'pointer',
          background: 'var(--accent)', color: '#1a1a2e', fontWeight: 600, fontSize: 13,
        }}>
          {exporting ? '⏳...' : `📤 ${l.export}`}
        </button>
        <label style={{
          flex: 1, padding: 10, borderRadius: 10, border: '1px solid var(--border)',
          cursor: importing ? 'wait' : 'pointer', textAlign: 'center', fontSize: 13,
          background: 'var(--bg-card)', color: 'var(--text-primary)', fontWeight: 600,
        }}>
          📥 {l.import}
          <input type="file" accept=".json" onChange={handleImport} disabled={importing} style={{ display: 'none' }} />
        </label>
      </div>
      {message && <div style={{ fontSize: 12, color: message.startsWith('✅') ? '#69f0ae' : '#ff5252' }}>{message}</div>}
    </div>
  );
}