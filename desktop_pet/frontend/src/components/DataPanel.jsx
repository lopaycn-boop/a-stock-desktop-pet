import React, { useState } from 'react';
import '../App.css';

const DATA_SOURCES = [
  { id: 'deepseek', label: 'DeepSeek LLM', emoji: '🧠', desc: '5层AI路由主引擎' },
  { id: 'eastmoney', label: '东方财富', emoji: '📊', desc: '异动/龙虎榜/筹码/行情' },
  { id: 'iwencai', label: '问财选股', emoji: '🎯', desc: '自然语言选股/宏观/资讯' },
  { id: 'trendradar', label: '舆情热点', emoji: '🔥', desc: '15平台实时热搜+金融分析' },
  { id: 'sina', label: '新浪财经', emoji: '💹', desc: '实时行情行情' },
  { id: 'plan_execute', label: 'PlanExecute', emoji: '🔬', desc: '多步深度分析引擎' },
];

const TRENDAR_PLATFORMS = [
  { id: 'weibo', label: '微博' },
  { id: 'baidu', label: '百度' },
  { id: 'zhihu', label: '知乎' },
  { id: 'douyin', label: '抖音' },
  { id: 'toutiao', label: '头条' },
  { id: 'bilibili', label: 'B站' },
  { id: '36kr', label: '36氪' },
  { id: 'eastmoney', label: '东财' },
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
  const [trPlatforms, setTrPlatforms] = useState(['weibo', 'baidu', 'zhihu', 'eastmoney']);
  const [trKeyword, setTrKeyword] = useState('');
  const [trResults, setTrResults] = useState(null);
  const [trLoading, setTrLoading] = useState(false);
  const [trTab, setTrTab] = useState('trending');

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

  const handleTrendradar = () => {
    setTrLoading(true);
    setTrResults(null);
    const actionType = trTab === 'trending' ? 'trendradar_trending'
      : trTab === 'search' ? 'trendradar_search'
      : 'trendradar_sentiment';
    const payload = { platforms: trPlatforms, limit: 20 };
    if (trTab === 'search') payload.keyword = trKeyword.trim();

    const handler = (msg) => {
      if (msg.type === actionType) {
        setTrResults(msg.payload || msg);
        setTrLoading(false);
        return true;
      }
      if (msg.type === 'error' && trLoading) {
        setTrLoading(false);
        return true;
      }
      return false;
    };

    sendPacket({ type: actionType, payload });

    const timeout = setTimeout(() => {
      setTrLoading(false);
    }, 15000);

    const originalHandler = handler;
    const unsubscribe = () => { clearTimeout(timeout); };
    window._trHandler = originalHandler;
    window._trUnsubscribe = unsubscribe;
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

      <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: 16, marginBottom: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>🔥 舆情热点监控</div>
        <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginBottom: 8 }}>
          15平台实时热搜 · 关键词搜索 · 金融舆情分析
        </div>
        <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
          {['trending', 'search', 'sentiment'].map(tab => (
            <button key={tab} onClick={() => { setTrTab(tab); setTrResults(null); }} style={{
              padding: '5px 10px', borderRadius: 8, fontSize: 11,
              border: trTab === tab ? '1px solid #ff6b35' : '1px solid rgba(255,255,255,0.15)',
              background: trTab === tab ? 'rgba(255,107,53,0.2)' : 'transparent',
              color: trTab === tab ? 'white' : 'rgba(255,255,255,0.4)',
              cursor: 'pointer',
            }}>
              {{ trending: '🔥热搜', search: '🔍搜索', sentiment: '📊舆情' }[tab]}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8 }}>
          {TRENDAR_PLATFORMS.map(p => (
            <button key={p.id} onClick={() => {
              setTrPlatforms(prev => prev.includes(p.id) ? prev.filter(x => x !== p.id) : [...prev, p.id]);
            }} style={{
              padding: '3px 8px', borderRadius: 6, fontSize: 10,
              border: trPlatforms.includes(p.id) ? '1px solid #646cff' : '1px solid rgba(255,255,255,0.1)',
              background: trPlatforms.includes(p.id) ? 'rgba(100,108,255,0.15)' : 'transparent',
              color: trPlatforms.includes(p.id) ? 'white' : 'rgba(255,255,255,0.3)',
              cursor: 'pointer',
            }}>
              {p.label}
            </button>
          ))}
        </div>
        {trTab === 'search' && (
          <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
            <input value={trKeyword} onChange={e => setTrKeyword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && trKeyword.trim() && handleTrendradar()}
              placeholder="输入关键词..." style={{
                flex: 1, padding: '6px 10px', borderRadius: 8, fontSize: 12,
                border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.05)',
                color: 'white', outline: 'none',
              }} />
          </div>
        )}
        <button onClick={handleTrendradar} disabled={trTab === 'search' && !trKeyword.trim()} style={{
          width: '100%', padding: '10px', borderRadius: 10, border: 'none',
          background: trTab === 'search' && !trKeyword.trim() ? 'rgba(255,255,255,0.1)' : 'linear-gradient(135deg, #ff6b35, #ff8f5e)',
          color: trTab === 'search' && !trKeyword.trim() ? 'rgba(255,255,255,0.3)' : 'white',
          cursor: trTab === 'search' && !trKeyword.trim() ? 'not-allowed' : 'pointer',
          fontSize: 13, fontWeight: 700,
        }}>
          {trTab === 'trending' ? '🔥 获取热点' : trTab === 'search' ? '🔍 搜索热点' : '📊 舆情分析'}
        </button>
        {trLoading && <div style={{ textAlign: 'center', marginTop: 8, fontSize: 12, color: 'rgba(255,255,255,0.5)' }}>⏳ 加载中...</div>}
        {trResults && (
          <div style={{ marginTop: 10, padding: '8px', borderRadius: 8, background: 'rgba(255,255,255,0.05)', maxHeight: 200, overflowY: 'auto', fontSize: 11 }}>
            {trTab === 'sentiment' && trResults.platforms && trResults.platforms.map(p => (
              <div key={p.platform_id} style={{ marginBottom: 6, padding: '4px 6px', borderRadius: 6, background: 'rgba(255,255,255,0.03)' }}>
                <span style={{ fontWeight: 600 }}>{p.platform_name}</span>
                <span style={{ color: 'rgba(255,255,255,0.4)' }}> · {p.total_topics}条 · 金融{p.finance_related}条({p.finance_ratio}%)</span>
              </div>
            ))}
            {trTab !== 'sentiment' && trResults.items && trResults.items.slice(0, 15).map((item, i) => (
              <div key={i} style={{ padding: '3px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                <span style={{ color: '#ff6b35', fontWeight: 600, marginRight: 4 }}>{item.rank || i + 1}</span>
                <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: 10, marginRight: 4 }}>[{item.platform_name}]</span>
                <span>{item.title}</span>
                {item.relevance && <span style={{ fontSize: 9, marginLeft: 4, color: item.relevance === 'high' ? '#4caf50' : '#ff9800' }}>{item.relevance === 'high' ? '高相关' : '相关'}</span>}
              </div>
            ))}
            {!trResults.items?.length && trTab !== 'sentiment' && <div style={{ color: 'rgba(255,255,255,0.3)' }}>暂无数据</div>}
          </div>
        )}
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