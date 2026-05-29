import React, { useState } from 'react';
import '../App.css';

const DATA_SOURCES = [
  { id: 'deepseek', label: 'DeepSeek LLM', emoji: '🧠', desc: '5层AI路由主引擎' },
  { id: 'eastmoney', label: '东方财富', emoji: '📊', desc: '异动/龙虎榜/筹码/行情' },
  { id: 'iwencai', label: '问财选股', emoji: '🎯', desc: '自然语言选股/宏观/资讯' },
  { id: 'sina', label: '新浪财经', emoji: '💹', desc: '实时行情行情' },
  { id: 'plan_execute', label: 'PlanExecute', emoji: '🔬', desc: '多步深度分析引擎' },
];

const IWENCAI_QUICK_QUERIES = [
  '连续涨停3天的股票',
  '机构净买入前10',
  '放量突破的股票',
  '属于新能源板块的强势股',
  'MACD金叉的股票',
  'RSI超卖的股票',
];

const DataPanel = ({ sendPacket, messages }) => {
  const [queryInput, setQueryInput] = useState('');
  const [searchKeyword, setSearchKeyword] = useState('');
  const [searchChannel, setSearchChannel] = useState('news');

  const handleIwencaiQuery = () => {
    if (!queryInput.trim()) return;
    sendPacket({ type: 'text_input', payload: { text: queryInput.trim() } });
    setQueryInput('');
  };

  const handleQuickQuery = (q) => {
    sendPacket({ type: 'text_input', payload: { text: q } });
  };

  const handlePlanExecute = () => {
    sendPacket({ type: 'text_input', payload: { text: '深度分析自选股，多步分析' } });
  };

  const handleIwencaiSearch = () => {
    if (!searchKeyword.trim()) return;
    sendPacket({ type: 'text_input', payload: { text: `搜索${searchChannel === 'report' ? '研报' : searchChannel === 'investor' ? '投资者关系' : searchChannel === 'announcement' ? '公告' : '新闻'}：${searchKeyword}` } });
    setSearchKeyword('');
  };

  return (
    <div style={{ padding: 16, color: 'white', fontSize: 13, maxHeight: '80vh', overflowY: 'auto' }}>
      <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>📡 数据源面板</div>

      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)', marginBottom: 8 }}>已接入数据源</div>
        {DATA_SOURCES.map(ds => (
          <div key={ds.id} style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
            borderRadius: 10, background: 'rgba(255,255,255,0.05)', marginBottom: 4,
          }}>
            <span style={{ fontSize: 18 }}>{ds.emoji}</span>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{ds.label}</div>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>{ds.desc}</div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: 16, marginBottom: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>🎯 问财智能选股</div>
        <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginBottom: 8 }}>
          用自然语言筛选股票、查宏观、搜资讯
        </div>

        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
          {IWENCAI_QUICK_QUERIES.map(q => (
            <button key={q} onClick={() => handleQuickQuery(q)} style={{
              background: 'rgba(100,108,255,0.12)', border: '1px solid rgba(100,108,255,0.25)',
              borderRadius: 14, padding: '5px 10px', color: 'white', cursor: 'pointer', fontSize: 11,
            }}>
              {q}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
          <input
            value={queryInput}
            onChange={e => setQueryInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleIwencaiQuery()}
            placeholder="输入选股条件..."
            style={{
              flex: 1, padding: '8px 12px', borderRadius: 10, fontSize: 13,
              border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.05)',
              color: 'white', outline: 'none',
            }}
          />
          <button onClick={handleIwencaiQuery} disabled={!queryInput.trim()} style={{
            padding: '8px 14px', borderRadius: 10, border: 'none',
            background: queryInput.trim() ? '#646cff' : 'rgba(255,255,255,0.1)',
            color: queryInput.trim() ? 'white' : 'rgba(255,255,255,0.3)',
            cursor: queryInput.trim() ? 'pointer' : 'not-allowed', fontWeight: 600, fontSize: 13,
          }}>查询</button>
        </div>

        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'rgba(255,255,255,0.6)' }}>资讯搜索</div>
        <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
          {['news', 'report', 'investor', 'announcement'].map(ch => (
            <button key={ch} onClick={() => setSearchChannel(ch)} style={{
              padding: '4px 8px', borderRadius: 8, fontSize: 11,
              border: searchChannel === ch ? '1px solid #646cff' : '1px solid rgba(255,255,255,0.15)',
              background: searchChannel === ch ? 'rgba(100,108,255,0.2)' : 'transparent',
              color: searchChannel === ch ? 'white' : 'rgba(255,255,255,0.4)',
              cursor: 'pointer',
            }}>
              {{ news: '📰新闻', report: '📊研报', investor: '👥投资者', announcement: '📢公告' }[ch]}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <input
            value={searchKeyword}
            onChange={e => setSearchKeyword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleIwencaiSearch()}
            placeholder="搜索关键词..."
            style={{
              flex: 1, padding: '8px 12px', borderRadius: 10, fontSize: 13,
              border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.05)',
              color: 'white', outline: 'none',
            }}
          />
          <button onClick={handleIwencaiSearch} disabled={!searchKeyword.trim()} style={{
            padding: '8px 14px', borderRadius: 10, border: 'none',
            background: searchKeyword.trim() ? '#646cff' : 'rgba(255,255,255,0.1)',
            color: searchKeyword.trim() ? 'white' : 'rgba(255,255,255,0.3)',
            cursor: searchKeyword.trim() ? 'pointer' : 'not-allowed', fontWeight: 600, fontSize: 13,
          }}>搜索</button>
        </div>
      </div>

      <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>🔬 PlanExecute 深度分析</div>
        <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginBottom: 10 }}>
          计划→执行→综合 三段式深度分析，质量更高
        </div>
        <button onClick={handlePlanExecute} style={{
          width: '100%', padding: '12px', borderRadius: 10, border: 'none',
          background: 'linear-gradient(135deg, #646cff, #7c3aed)', color: 'white',
          cursor: 'pointer', fontSize: 14, fontWeight: 700,
          boxShadow: '0 4px 15px rgba(100,108,255,0.3)',
        }}>
          🔬 启动多步深度分析
        </button>
      </div>

      <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: 16, marginTop: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>📊 东方财富数据</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
          {[
            { label: '📈 异动监控', action: '异动股票有哪些' },
            { label: '🀄 龙虎榜', action: '今天龙虎榜数据' },
            { label: '💹 实时行情', action: '贵州茅台实时行情' },
            { label: '📊 情绪分析', action: '分析今天A股市场情绪' },
          ].map(btn => (
            <button key={btn.label} onClick={() => sendPacket({ type: 'text_input', payload: { text: btn.action } })} style={{
              padding: '8px 10px', borderRadius: 10, fontSize: 12, border: '1px solid rgba(255,255,255,0.12)',
              background: 'rgba(255,255,255,0.05)', color: 'white', cursor: 'pointer', textAlign: 'left',
            }}>
              {btn.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default DataPanel;