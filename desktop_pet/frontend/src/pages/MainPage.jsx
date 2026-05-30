import React, { useState, useRef, useCallback, useEffect } from 'react';
import Live2DController from '../components/Live2D/Live2DController';
import LoadingDots from '../components/LoadingDots';
import ModelPicker from '../components/ModelPicker';
import BillingPanel from '../components/BillingPanel';
import RenewalPanel from '../components/RenewalPanel';
import DataPanel from '../components/DataPanel';
import SettingsPanel from '../components/SettingsPanel';
import TradeHistoryPanel from '../components/TradeHistoryPanel';
import OnboardingWizard from '../components/OnboardingWizard';
import '../App.css';

import { useAudioQueue } from '../hooks/useAudioQueue';
import { useNeuroSocket } from '../hooks/useNeuroSocket';
import { useClickThrough } from '../hooks/useClickThrough';
import { useDesktopNotification } from '../hooks/useDesktopNotification';
import { useWakeWord } from '../hooks/useWakeWord';
import { playTradeSignal, playRiskAlert, playChatNotification } from '../hooks/useSounds';
import { inferEmotionFromMessage, emotionToExpression, stateToExpression } from '../hooks/useEmotionEngine';
import { usePersistentMessages } from '../hooks/usePersistentMessages';
import { renderMessageContent } from '../hooks/useMessageRenderer.jsx';
import { getSavedModelId, saveModelId } from '../components/Live2D/modelRegistry';
import ErrorBoundary from '../components/ErrorBoundary';
import SplashScreen from '../components/SplashScreen';
import ToastContainer, { showToast } from '../components/ToastContainer';
import QuickReplyChips from '../components/QuickReplyChips';
import MessageActions from '../components/MessageActions';
import ChatSearch from '../components/ChatSearch';
import CommandPalette from '../components/CommandPalette';
import ChatMessage from '../components/ChatMessage';
import KeyboardHelp from '../components/KeyboardHelp';
import ContextMenu from '../components/ContextMenu';
import DropOverlay from '../components/DropOverlay';
import useI18n from '../hooks/useI18n';
import useTheme from '../hooks/useTheme';
import useChatResize from '../hooks/useChatResize';
import useTooltip from '../hooks/useTooltip.jsx';
import StockChart from '../components/StockChart';
import PortfolioDashboard from '../components/PortfolioDashboard';
import StrategyEditor from '../components/StrategyEditor';

function formatTs(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function copyToClipboard(text) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).catch(() => {});
  }
}

function KeyboardShortcuts({ chatOpen, setChatOpen, inputText, setInputText, handleSend, quickActions, handleQuickAction, setShowKeyboardHelp, setShowChatSearch, cycleTheme, switchLang, isZh, handleExportChat }) {
  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Escape' && chatOpen) { setChatOpen(false); return; }
      if (e.ctrlKey || e.metaKey) {
        const num = parseInt(e.key);
        if (num >= 1 && num <= 9 && num <= quickActions.length) {
          e.preventDefault();
          handleQuickAction(quickActions[num - 1]);
          return;
        }
        if (e.key === 'Enter') {
          e.preventDefault();
          if (inputText.trim()) handleSend();
          return;
        }
        if (e.key === 'l') { e.preventDefault(); switchLang(isZh ? 'en' : 'zh'); return; }
        if (e.key === 'd') { e.preventDefault(); cycleTheme(); return; }
        if (e.key === 'f') { e.preventDefault(); setShowChatSearch(s => !s); return; }
        if (e.key === 'e') { e.preventDefault(); handleExportChat(); return; }
      }
      if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const tag = e.target.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA') return;
        setShowKeyboardHelp(s => !s);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [chatOpen, setChatOpen, inputText, setInputText, handleSend, quickActions, handleQuickAction, setShowKeyboardHelp, setShowChatSearch, cycleTheme, switchLang, isZh, handleExportChat]);
  return null;
}

const SECRET_PATTERNS = [
  { re: /(sk-[a-zA-Z0-9]{8,})/gi, label: 'API_KEY' },
  { re: /(key[a-z_]*[=:]\s*)["']?([a-zA-Z0-9\-_]{16,})["']?/gi, label: 'KEY' },
  { re: /(token[a-z_]*[=:]\s*)["']?([a-zA-Z0-9\-_\.]{16,})["']?/gi, label: 'TOKEN' },
  { re: /(secret[a-z_]*[=:]\s*)["']?([a-zA-Z0-9\-_\.]{16,})["']?/gi, label: 'SECRET' },
  { re: /(password[a-z_]*[=:]\s*)["']?([^\s"']{6,})["']?/gi, label: 'PASSWORD' },
  { re: /(Bearer\s+)([a-zA-Z0-9\-_\.]{16,})/gi, label: 'BEARER' },
  { re: /([a-zA-Z0-9+\/]{48,}={1,2})(?=[\s\]|}]|$)/g, label: 'BASE64_SECRET' },
];

function maskSecrets(text) {
  if (!text || typeof text !== 'string') return text;
  let result = text;
  for (const { re, label } of SECRET_PATTERNS) {
    result = result.replace(re, (match, prefix, secret) => {
      if (secret) return `${prefix || ''}[${label} hidden]`;
      return `[${label} hidden]`;
    });
  }
  return result;
}

const KNOWN_KEYS_MAP = {
  'deepseek': 'DEEPSEEK_API_KEY',
  'sk-': 'DEEPSEEK_API_KEY',
  'silicon': 'SILICON_API_KEY',
  'liner': 'LINER_API_KEY',
  'telegram': 'TELEGRAM_BOT_TOKEN',
  'feishu_app_id': 'FEISHU_APP_ID',
  'feishu_app_secret': 'FEISHU_APP_SECRET',
  'feishu_webhook': 'FEISHU_WEBHOOK_URL',
  'dingtalk': 'DINGTALK_WEBHOOK_URL',
  'eastmoney': 'EASTMONEY_ACCOUNT',
  'tonghuashun': 'TONGHUASHUN_ACCOUNT',
  'xueqiu': 'XUEQIU_TOKEN',
  'bytebot': 'BYTEBOT_AGENT_URL',
  'anthropic': 'ANTHROPIC_API_KEY',
  'openai': 'OPENAI_API_KEY',
  'em_': 'EM_API_KEY',
  'iwencai': 'IWENCAI_API_KEY',
};

function detectKey(text) {
  const trimmed = text.trim();
  if (/^sk-[a-zA-Z0-9]{8,}$/.test(trimmed)) {
    return { key: 'DEEPSEEK_API_KEY', value: trimmed };
  }
  const kvMatch = trimmed.match(/^(DEEPSEEK_API_KEY|SILICON_API_KEY|LINER_API_KEY|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID|FEISHU_APP_ID|FEISHU_APP_SECRET|FEISHU_WEBHOOK_URL|DINGTALK_WEBHOOK_URL|EASTMONEY_ACCOUNT|EASTMONEY_PASSWORD|TONGHUASHUN_ACCOUNT|TONGHUASHUN_PASSWORD|XUEQIU_TOKEN|BYTEBOT_AGENT_URL|BYTEBOT_DESKTOP_URL|ANTHROPIC_API_KEY|OPENAI_API_KEY|EM_API_KEY|IWENCAI_API_KEY)[=:：\s]+(.+)$/i);
  if (kvMatch) {
    return { key: kvMatch[1].toUpperCase(), value: kvMatch[2].trim() };
  }
  for (const [pattern, keyName] of Object.entries(KNOWN_KEYS_MAP)) {
    if (pattern !== 'sk-' && trimmed.toLowerCase().includes(pattern) && trimmed.length > 20) {
      const val = trimmed.split(/[=:：]/).slice(1).join(':').trim() || trimmed;
      if (val.length >= 8) return { key: keyName, value: val };
    }
  }
  if (trimmed.length >= 20 && /^[a-zA-Z0-9\-_\.]+$/.test(trimmed)) {
    return { key: 'MANUAL_KEY', value: trimmed };
  }
  return null;
}

const QUICK_ACTIONS = [
  { label: '📈 行情', msg: '帮我看看今天A股行情' },
  { label: '🔥 热点', msg: '今天有什么热点板块' },
  { label: '📊 分析', msg: '帮我分析最近值得关注的股票' },
  { label: '💰 持仓', msg: '帮我看看持仓情况' },
  { label: '💹 余额', msg: '__broker_balance__' },
  { label: '🔀 模式', msg: '__broker_switch__' },
  { label: '📋 仪表盘', msg: '__dashboard__' },
  { label: '💳 计费', msg: '__billing_dashboard__' },
  { label: '🔄 续费', msg: '__billing_renewal_payment__' },
  { label: '🧠 记忆', msg: '__memory__' },
  { label: '🔑 密钥', msg: '__vault__' },
  { label: '📡 数据', msg: '__data_panel__' },
  { label: '🆙 更新', msg: '__check_updates__' },
  { label: '📊 记录', msg: '__trade_history__' },
  { label: '⚙️ 设置', msg: '__settings__' },
];

export default function MainPage() {
  const { messages, setMessages, clearMessages } = usePersistentMessages();
  const { t, lang, switchLang, isZh } = useI18n();
  const { theme, effectiveTheme, cycleTheme } = useTheme();
  const { width: chatWidth, resizeHandleProps, isDragging } = useChatResize(380);
  const { show: showTooltip, hide: hideTooltip, TooltipOverlay } = useTooltip();
  const [showChatSearch, setShowChatSearch] = useState(false);
  const [showKeyboardHelp, setShowKeyboardHelp] = useState(false);
  const [contextMenu, setContextMenu] = useState(null);
  const [neuroState, setNeuroState] = useState("idle");
  const [inputText, setInputText] = useState('');
  const [chatOpen, setChatOpen] = useState(false);
  const [pinnedMessages, setPinnedMessages] = useState(() => {
    try { return JSON.parse(localStorage.getItem('potato_pinned') || '[]'); } catch { return []; }
  });
  const [showPinned, setShowPinned] = useState(false);
  const [actionSteps, setActionSteps] = useState([]);
  const [vaultReady, setVaultReady] = useState(null);
  const [recording, setRecording] = useState(false);
  const [renewalProviders, setRenewalProviders] = useState([]);
  const [currentModel, setCurrentModel] = useState(getSavedModelId);
  const [bytebotTaskId, setBytebotTaskId] = useState(null);
  const [billingPanelData, setBillingPanelData] = useState(null);
  const [renewalPanelData, setRenewalPanelData] = useState(null);
  const [showBillingPanel, setShowBillingPanel] = useState(false);
  const [showRenewalPanel, setShowRenewalPanel] = useState(false);
  const [showDataPanel, setShowDataPanel] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showTradeHistory, setShowTradeHistory] = useState(false);
  const [dashboardTab, setDashboardTab] = useState('chart');
  const [showOnboarding, setShowOnboarding] = useState(() => {
    try { return !localStorage.getItem('potato_onboarding_done'); } catch(e) { return false; }
  });
  const [alwaysOnTop, setAlwaysOnTop] = useState(true);
  const [systemStatus, setSystemStatus] = useState(null);
  const [splashStage, setSplashStage] = useState('init');
  const messagesEndRef = useRef(null);
  const chatMessagesRef = useRef(null);
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const live2dRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const micTimerRef = useRef(null);

  const msg = useCallback((type, content, extra = {}) => ({ type, content, ts: Date.now(), ...extra }), []);

  useClickThrough();
  const { notify } = useDesktopNotification();
  const { listening: wakeListening, startWakeListener, stopWakeListener } = useWakeWord({
    onWake: useCallback(() => { setChatOpen(true); }, []),
  });

  const { subtitle, isPlaying, queueAudioChunk, stopAudio } = useAudioQueue(live2dRef);

  const handleServerPacket = useCallback((packet) => {
    const { type, payload } = packet;
    notify(packet);
    // Live2D emotion trigger
    const emotion = inferEmotionFromMessage({ type, content: payload?.text || payload?.message || payload?.info || '' });
    if (emotion && live2dRef.current) {
      const expr = emotionToExpression(emotion, currentModel);
      if (expr) { live2dRef.current.showExpression(expr, true); setTimeout(() => live2dRef.current?.resetExpression?.(), 4000); }
    }
    switch (type) {
      case 'state_update':
        setNeuroState(payload.state);
        break;
      case 'system_status':
        setMessages(prev => [...prev, { type: 'system', content: `📌 ${payload.message || JSON.stringify(payload)}` }]);
        if (payload.status === 'shutting_down') setNeuroState('idle');
        break;
      case 'audio_chunk':
        setNeuroState("idle");
        queueAudioChunk(payload);
        setMessages(prev => [...prev, { type: 'assistant', content: maskSecrets(payload.text) }]);
        setChatOpen(true);
        break;
      case 'chat':
        setMessages(prev => [...prev, { type: 'assistant', content: maskSecrets(payload.text || payload.reply || '') }]);
        setNeuroState('idle');
        break;
      case 'canceled':
        setNeuroState('idle');
        setMessages(prev => [...prev, { type: 'system', content: '⏹ 已取消' }]);
        break;
      case 'error':
        setMessages(prev => [...prev, { type: 'system', content: `❌ ${maskSecrets(payload.info)}` }]);
        setNeuroState('idle');
        setRecording(false);
        break;
      case 'vault_stored':
        setMessages(prev => [...prev, { type: 'system', content: `✅ ${payload.key} 已保存` }]);
        showToast(`${payload.key} 已保存`, 'success');
        sendPacket({ type: 'vault_status', payload: {} });
        break;
      case 'vault_deleted':
        setMessages(prev => [...prev, { type: 'system', content: `🗑️ ${payload.key || '密钥'} 已删除` }]);
        sendPacket({ type: 'vault_status', payload: {} });
        break;
      case 'action_error':
        setMessages(prev => [...prev, { type: 'system', content: `⚠️ ${maskSecrets(payload.error || payload.detail || payload.info || '操作失败')}` }]);
        break;
      case 'quota_exhausted': {
        const providers = payload.providers || [];
        setRenewalProviders(providers.map(p => ({
          key_env: p.key_env || p.provider,
          desc: p.key_desc || p.provider,
          url: p.renewal_url || p.dashboard_url || '#',
        })));
        const renewalLinks = providers.map(p => p.key_desc || p.provider);
        let quotaMsg = payload.message || 'API额度已用完';
        if (renewalLinks.length > 0) {
          quotaMsg += ' 点击下方按钮续费 ↓';
        }
        setMessages(prev => [...prev, { type: 'system', content: `⚠️ ${quotaMsg}` }]);
        setNeuroState('idle');
        break;
      }
      case 'renewal_opened': {
        setMessages(prev => [...prev, { type: 'system', content: `🔗 已打开续费页面: ${payload.key}` }]);
        setRenewalProviders([]);
        break;
      }
      case 'vault_status': {
        const total = payload.total_keys || 0;
        const missingArr = payload.missing_required || [];
        const missing = missingArr.map(m => m.desc || m.key).join('、');
        setVaultReady(missingArr.length === 0);
        const statusMsg = total > 0 && !missing
          ? '✅ 密钥已就绪，可以对话了'
          : total > 0 ? `已有 ${total} 个密钥，还缺：${missing} — 粘贴给我就行`
          : '🔐 还没有密钥，粘贴你的 API Key（sk-xxx）即可开始';
        setMessages(prev => {
          const last = prev[prev.length - 1];
          if (last && last.type === 'system' && last.content.includes('密钥')) {
            return [...prev.slice(0, -1), { type: 'system', content: statusMsg }];
          }
          return [...prev, { type: 'system', content: statusMsg }];
        });
        break;
      }
      case 'vault_keys': {
        const ks = (payload.keys || []).map(k => k.key || k).join('、');
        setMessages(prev => [...prev, { type: 'system', content: ks || '（暂无密钥）' }]);
        break;
      }
      case 'screenshot_captured': {
        const imgData = payload.screenshot_b64;
        if (imgData) {
          const src = imgData.startsWith('data:') ? imgData : `data:image/png;base64,${imgData}`;
          setMessages(prev => [...prev, { type: 'system', content: '📸 截图已捕获', image: src }]);
        } else {
          setMessages(prev => [...prev, { type: 'system', content: '📸 截图已捕获' }]);
        }
        break;
      }
      case 'app_launched': {
        const appName = payload.app_name || payload.platform_id || '应用';
        setMessages(prev => [...prev, { type: 'system', content: `🚀 已打开 ${appName}` }]);
        break;
      }
      case 'app_not_found': {
        const appName = payload.app_name || payload.platform_id || '应用';
        setMessages(prev => [...prev, { type: 'system', content: `⚠️ 未找到 ${appName}，正在尝试浏览器...` }]);
        break;
      }
      case 'app_launch_result': {
        const alr = payload || {};
        const alrMsg = alr.ok
          ? `🚀 已打开 ${alr.app_name || alr.platform_id || '应用'}`
          : `⚠️ 打开失败: ${alr.error || alr.app_name || '未知'}`;
        setMessages(prev => [...prev, { type: 'system', content: alrMsg }]);
        break;
      }
      case 'browser_opened': {
        const platform = payload.platform_id || '交易平台';
        setMessages(prev => [...prev, { type: 'system', content: `🌐 已打开 ${platform}` }]);
        break;
      }
      case 'detected_apps': {
        const apps = (payload.apps || []).map(a => a.name || a).join('、');
        setMessages(prev => [...prev, { type: 'system', content: `📱 检测到应用: ${apps || '无'}` }]);
        break;
      }
      case 'visual_task_result': {
        const result = payload.result || payload;
        const ok = result.ok !== false;
        const steps = result.steps || 0;
        const method = result.method || '';
        setMessages(prev => [...prev, { type: 'system', content: ok
          ? `✅ 操作完成 (${steps}步, ${method})`
          : `❌ 操作失败: ${result.error || '未知错误'}` }]);
        break;
      }
      case 'login_result': {
        const ok = payload.ok !== false;
        setMessages(prev => [...prev, { type: 'system', content: ok
          ? '✅ 登录成功'
          : `❌ 登录失败: ${payload.error || '请检查账号密码'}` }]);
        break;
      }
      case 'cycle_result': {
        const ok = payload.ok !== false;
        const summary = payload.summary || '';
        setMessages(prev => [...prev, { type: 'system', content: ok
          ? `📈 交易周期完成: ${summary}`
          : `❌ 交易失败: ${payload.error || ''}` }]);
        break;
      }
      case 'analysis_result': {
        const result = payload;
        const ok = result.ok !== false;
        setMessages(prev => [...prev, { type: 'system', content: ok
          ? `📊 分析完成`
          : `❌ 分析失败` }]);
        break;
      }
      case 'bytebot_task_created': {
        const tid = (payload.task_id || '').slice(0, 8);
        setBytebotTaskId(payload.task_id);
        setMessages(prev => [...prev, { type: 'system', content: `🤖 Bytebot 任务已创建 (${tid}...)` }]);
        break;
      }
      case 'bytebot_task_update': {
        const statusCn = payload.status_cn || payload.status || '';
        const elapsed = payload.elapsed ? ` (${payload.elapsed}s)` : '';
        const errMsg = payload.error ? ` - ${payload.error}` : '';
        if (payload.task_id) setBytebotTaskId(payload.task_id);
        setMessages(prev => [...prev, { type: 'system', content: `🤖 Bytebot: ${statusCn}${elapsed}${errMsg}` }]);
        break;
      }
      case 'bytebot_task_done': {
        const doneStatus = payload.status === 'COMPLETED' ? '✅ 完成' : payload.status === 'FAILED' ? '❌ 失败' : payload.status;
        const doneElapsed = payload.elapsed ? ` (${payload.elapsed}s)` : '';
        const doneErr = payload.error ? `: ${payload.error}` : '';
        setBytebotTaskId(null);
        setMessages(prev => [...prev, { type: 'system', content: `🤖 Bytebot 任务${doneStatus}${doneElapsed}${doneErr}` }]);
        break;
      }
      case 'bytebot_status': {
        const agent = payload.agent_available ? '✅' : '❌';
        const desktop = payload.desktop_available ? '✅' : '❌';
        const recentCount = (payload.recent_tasks || []).length;
        setMessages(prev => [...prev, { type: 'system', content: `🤖 Bytebot: Agent ${agent} | Desktop ${desktop} | ${recentCount} 近期任务` }]);
        break;
      }
      case 'bytebot_screenshot': {
        const bImg = payload.screenshot_b64;
        if (bImg) {
          const bSrc = bImg.startsWith('data:') ? bImg : `data:image/png;base64,${bImg}`;
          setMessages(prev => [...prev, { type: 'system', content: '🤖 Bytebot 截图已获取', image: bSrc }]);
        } else {
          setMessages(prev => [...prev, { type: 'system', content: '🤖 Bytebot 截图已获取' }]);
        }
        break;
      }
      case 'bytebot_desktop_result': {
        const bAction = payload.action || '';
        const bOk = payload.result?.ok !== false;
        const bImgData = payload.result?.image || payload.result?.screenshot_b64;
        const bSrc = bImgData ? (bImgData.startsWith('data:') ? bImgData : `data:image/png;base64,${bImgData}`) : null;
        const msgObj = { type: 'system', content: bOk
          ? `\u{1F916} ${bAction} 操作完成`
          : `\u{1F916} ${bAction} 操作失败: ${payload.result?.error || ''}` };
        if (bSrc) msgObj.image = bSrc;
        setMessages(prev => [...prev, msgObj]);
        break;
      }
      case 'bytebot_task_cancelled': {
        setBytebotTaskId(null);
        setMessages(prev => [...prev, { type: 'system', content: `🤖 任务已取消` }]);
        break;
      }
      case 'action_group_start': {
        const groupId = Date.now();
        setActionSteps([{ id: groupId, steps: payload.actions || [], current: 0, done: false }]);
        break;
      }
      case 'action_step': {
        setActionSteps(prev => {
          if (prev.length === 0) {
            return [{ id: Date.now(), steps: [{ action: payload.action, label: payload.label, status: payload.status, detail: payload.detail }], current: 1, done: false }];
          }
          const last = prev[prev.length - 1];
          const existingSteps = last.steps || [];
          const stepIdx = existingSteps.findIndex(s => s.action === payload.action);
          let newSteps;
          if (stepIdx >= 0) {
            newSteps = [...existingSteps];
            newSteps[stepIdx] = { ...newSteps[stepIdx], status: payload.status, detail: payload.detail };
          } else {
            newSteps = [...existingSteps, { action: payload.action, label: payload.label, status: payload.status, detail: payload.detail }];
          }
          const allDone = newSteps.every(s => s.status === 'done' || s.status === 'error' || s.status === 'blocked');
          return [...prev.slice(0, -1), { ...last, steps: newSteps, current: newSteps.length, done: allDone }];
        });
        break;
      }
      case 'action_group_done': {
        setActionSteps(prev => {
          if (prev.length === 0) return prev;
          const last = prev[prev.length - 1];
          return [...prev.slice(0, -1), { ...last, done: true }];
        });
        break;
      }
      case 'memory_overview': {
        const totalFacts = Object.keys(payload.facts || {}).length;
        const byCat = payload.facts_by_category || {};
        const catLines = Object.entries(byCat).map(([cat, items]) => {
          const catNames = { identity: '👤 身份', preference: '💡 偏好', trading: '📈 交易', personal: '🏠 个人', system: '⚙️ 系统', bytebot: '🤖 Bytebot', other: '📋 其他' };
          const count = Object.keys(items).length;
          return `  ${catNames[cat] || cat}: ${count}条`;
        }).join('\n');
        const hot = payload.hot_count || 0;
        const summaries = payload.summaries_count || 0;
        setMessages(prev => [...prev, { type: 'system', content: `🧠 记忆总览\n${catLines}\n  📝 近期事件: ${hot}条\n  📋 历史摘要: ${summaries}条\n  共 ${totalFacts} 条事实` }]);
        break;
      }
      case 'memory_search': {
        const results = payload.results || [];
        if (results.length === 0) {
          setMessages(prev => [...prev, { type: 'system', content: `🔍 没找到关于「${maskSecrets(payload.keyword)}」的记忆` }]);
        } else {
          const lines = results.slice(0, 5).map(r => {
            const cat = r.category_name || r.category || '';
            const date = r.date || '';
            const content = (r.content || r.value || '').slice(0, 80);
            return cat ? `[${cat}] ${content}` : content;
          }).join('\n');
          setMessages(prev => [...prev, { type: 'system', content: `🔍 「${maskSecrets(payload.keyword)}」的记忆:\n${lines}` }]);
        }
        break;
      }
      case 'memory_cleanup': {
        const deleted = payload.expired_deleted || 0;
        setMessages(prev => [...prev, { type: 'system', content: deleted > 0 ? `🧹 清理了 ${deleted} 条过期记忆` : '记忆都很新鲜，不需要清理' }]);
        break;
      }
      case 'cleanup_result': {
        const totalFreed = payload.total_freed_mb || 0;
        const totalFiles = payload.total_files || 0;
        const level = payload.level || 'quick';
        const levelLabel = { quick: '快速', deep: '深度', full: '完整' }[level] || level;
        const detailLines = (payload.details || []).map(d => `  ${d}`).join('\n');
        setMessages(prev => [...prev, { type: 'system', content: `🧹 ${levelLabel}清理完成！\n删除${totalFiles}个文件，释放${totalFreed}MB空间\n${detailLines}` }]);
        break;
      }
      case 'risk_updated': {
        const summary = payload.summary || '风控参数已更新';
        const prefs = payload.all_prefs || {};
        setMessages(prev => [...prev, { type: 'system', content: `🛡️ ${summary}` }]);
        break;
      }
      case 'trade_signal': {
        playTradeSignal();
        const actionEmoji = { BUY: '🟢', SELL: '🔴', HOLD: '🟡', WATCH: '👀' }[payload.action] || '⚪';
        const signalMsg = payload.message || `${actionEmoji} ${payload.name || ''}(${payload.symbol || ''}) ${payload.action || ''}`;
        setMessages(prev => [...prev, { type: 'system', content: signalMsg, ts: Date.now() }]);
        break;
      }
      case 'trade_analysis': {
        const analysis = payload.analysis || {};
        const picks = analysis.stock_picks || [];
        if (picks.length > 0) {
          const pickLines = picks.slice(0, 5).map((p, i) => {
            const ae = { BUY: '🟢买入', SELL: '🔴卖出', HOLD: '🟡持有', WATCH: '👀观察' }[p.action] || '⚪';
            const conf = (p.confidence * 100).toFixed(0);
            return `${i+1}. ${ae} ${p.name || ''}(${p.symbol || ''}) 置信度${conf}%\n   理由: ${(p.reasoning || '').slice(0, 120)}\n   入场: ${p.entry_price || '-'} → 目标: ${p.target_price || '-'} | 止损: ${p.stop_loss || '-'}`;
          }).join('\n');
          setMessages(prev => [...prev, { type: 'system', content: `📊 选股分析\n${pickLines}` }]);
        }
        break;
      }
      case 'plan_execute_analysis': {
        const pxa = payload.analysis || {};
        const pxPicks = pxa.stock_picks || [];
        const steps = payload.steps_completed || 0;
        const method = payload.method || 'plan_execute';
        if (pxPicks.length > 0) {
          const pxLines = pxPicks.slice(0, 5).map((p, i) => {
            const ae = { BUY: '🟢买入', SELL: '🔴卖出', HOLD: '🟡持有', WATCH: '👀观察' }[p.action] || '⚪';
            const conf = (p.confidence * 100).toFixed(0);
            return `${i+1}. ${ae} ${p.name || ''}(${p.symbol || ''}) 置信度${conf}%\n   理由: ${(p.reasoning || '').slice(0, 120)}`;
          }).join('\n');
          setMessages(prev => [...prev, { type: 'system', content: `🔬 多步深度分析 (${steps}步完成)\n${pxLines}` }]);
        }
        break;
      }
      case 'trade_result': {
        if (payload.ok) {
          playTradeSignal();
        } else {
          playRiskAlert();
        }
        if (payload.ok) {
          setMessages(prev => [...prev, { type: 'system', content: `✅ 交易提交成功: ${payload.action || ''} ${payload.name || payload.symbol || ''} ¥${payload.amount_cny || ''}`, ts: Date.now() }]);
        } else {
          setMessages(prev => [...prev, { type: 'system', content: `🛑 交易被拦截: ${payload.reason || '风控不通过'}`, ts: Date.now() }]);
        }
        break;
      }
      case 'trade_step': {
        setActionSteps(prev => {
          const step = { action: payload.step, label: payload.step, status: payload.status, detail: payload.detail || '' };
          if (prev.length === 0) {
            return [{ id: Date.now(), steps: [step], current: 1, done: false }];
          }
          const last = prev[prev.length - 1];
          const newSteps = [...last.steps, step];
          const allDone = newSteps.every(s => s.status === 'done' || s.status === 'error' || s.status === 'blocked');
          return [...prev.slice(0, -1), { ...last, steps: newSteps, current: newSteps.length, done: allDone }];
        });
        break;
      }
      case 'schedule_step': {
        const ss = payload || {};
        setMessages(prev => [...prev, { type: 'system', content: `📅 ${ss.step || ss.name || '调度步骤完成'}` }]);
        break;
      }
      case 'trade_review': {
        const r = payload || {};
        const reviewMsg = r.summary || (
          `📊 复盘: ${r.total_trades || 0}笔 ` +
          `胜率${r.win_rate || 0}% ` +
          `盈亏¥${r.total_pnl || 0} ` +
          `利润因子${r.profit_factor || 0} ` +
          `最大回撤${r.max_drawdown_pct || 0}%`
        );
        setMessages(prev => [...prev, { type: 'system', content: reviewMsg }]);
        break;
      }
      case 'position_status': {
        const ps = payload || {};
        setMessages(prev => [...prev, { type: 'system', content: ps.summary || `持仓${ps.count || 0}只` }]);
        break;
      }
      case 'close_position': {
        const cp = payload || {};
        const pnl = parseFloat(cp.realized_pnl || 0);
        const icon = pnl > 0 ? '✅赚' : pnl < 0 ? '❌亏' : '➖平';
        setMessages(prev => [...prev, { type: 'system', content: `${icon} 平仓 ${cp.name || ''}(${cp.symbol || ''}) ¥${cp.entry_price || ''}→¥${cp.exit_price || ''} P&L=¥${cp.realized_pnl || 0}(${cp.realized_pnl_pct || 0}%) 持仓${cp.hold_duration_minutes || 0}分钟` }]);
        break;
      }
      case 'review_history': {
        const rh = payload || {};
        setMessages(prev => [...prev, { type: 'system', content: rh.summary || '暂无交易记录' }]);
        break;
      }
      case 'trade_alert': {
        const ta = payload || {};
        setMessages(prev => [...prev, { type: 'system', content: ta.message || `⚠️ ${ta.symbol} ${ta.type}` }]);
        break;
      }
      case 'risk_confirm_prompt': {
        const rcp = payload || {};
        const riskSummary = rcp.summary || rcp.message || '请确认风控参数';
        setMessages(prev => [...prev, {
          type: 'system',
          content: riskSummary,
          actions: [
            { label: '确认参数', action: 'update_risk', payload: rcp.params || {} },
            { label: '使用默认', action: 'update_risk', payload: { risk_confirmed: true } },
          ]
        }]);
        break;
      }
      case 'mid_review_result': {
        const mr = payload || {};
        setMessages(prev => [...prev, { type: 'system', content: mr.summary || '午间复盘完成' }]);
        break;
      }
      case 'pre_close_result': {
        const pc = payload || {};
        setMessages(prev => [...prev, { type: 'system', content: pc.summary || '尾盘评估完成' }]);
        break;
      }
      case 'daily_summary': {
        const ds = payload || {};
        setMessages(prev => [...prev, { type: 'system', content: ds.summary || '盘后复盘完成' }]);
        break;
      }
      case 'trade_auto_status': {
        const tas = payload || {};
        setMessages(prev => [...prev, { type: 'system', content: tas.message || (tas.running ? '自动操盘已启动' : '自动操盘已停止') }]);
        break;
      }
      case 'broker_status': {
        const bs = payload || {};
        window.__brokerIsLive = bs.is_live || false;
        const modeLabel = bs.is_live ? '🔴 实盘' : '🟡 模拟';
        const connected = bs.health?.ok ? '✅' : '❌';
        setMessages(prev => [...prev, { type: 'system', content: `交易模式: ${modeLabel} | 连接${connected} | ${bs.health?.message || ''}` }]);
        break;
      }
      case 'broker_switch': {
        const bsw = payload || {};
        window.__brokerIsLive = bsw.is_live || false;
        setMessages(prev => [...prev, { type: 'system', content: bsw.message || '交易模式已切换' }]);
        break;
      }
      case 'broker_balance': {
        const bb = payload || {};
        setMessages(prev => [...prev, { type: 'system', content: bb.summary || '余额查询完成' }]);
        break;
      }
      case 'billing_dashboard': {
        const bd = payload || {};
        setBillingPanelData(bd);
        setShowBillingPanel(true);
        setMessages(prev => [...prev, { type: 'system', content: bd.summary_text || '计费面板已打开' }]);
        break;
      }
      case 'billing_topup': {
        const bt = payload || {};
        setMessages(prev => [...prev, { type: 'system', content: bt.message || '充值完成' }]);
        if (billingPanelData) {
          setBillingPanelData(prev => ({ ...prev, wallet: bt.wallet || prev.wallet }));
        }
        break;
      }
      case 'billing_usage': {
        const bu = payload || {};
        const buProvs = (bu.providers || []).map(p => `  ${p.provider}: ¥${p.total_cny}`).join('\n');
        setMessages(prev => [...prev, { type: 'system', content: `📊 近${bu.period_days || 30}天使用: 费用¥${bu.total_all_cny || 0}\n${buProvs}` }]);
        break;
      }
case 'billing_renewal_payment': {
        const rp = payload || {};
        const rpItems = (rp.items || []).map(i => `  ${i.name}: ¥${i.price_cny || i.cost_with_margin}/月`).join('\n');
        let rpMsg;
        if (rp.balance_sufficient) {
          rpMsg = `✅ 续费成功！已自动从余额扣款。\n当前余额: ¥${rp.current_balance_cny}`;
        } else if (rp.wallet_address) {
          rpMsg = `💳 续费支付\n收款: ${rp.wallet_address} (${rp.wallet_label || 'USDT-TRC20'})\n余额: ¥${rp.current_balance_cny}\n${rpItems ? '待续费:\n' + rpItems : ''}\n合计: ¥${rp.total_renewal_cny}`;
          if (rp.payment_note) rpMsg += `\n${rp.payment_note}`;
          if (rp.qr_code) rpMsg += '\n\n📱 请扫描二维码支付';
        } else {
          rpMsg = '续费信息加载中...';
        }
        setRenewalPanelData(rp);
        setShowRenewalPanel(true);
        setMessages(prev => [...prev, { type: 'system', content: rpMsg }]);
        break;
      }
      case 'billing_confirm_payment': {
        const cp = payload || {};
        const cpMsg = cp.auto_renewed
          ? `✅ 付款确认，自动续费成功！余额: ¥${cp.wallet?.remaining_cny || '0'}`
          : `💰 付款已记录！余额: ¥${cp.wallet?.remaining_cny || '0'}`;
        setMessages(prev => [...prev, { type: 'system', content: cpMsg }]);
        if (showRenewalPanel) {
          setShowRenewalPanel(false);
        }
        break;
      }
      case 'credential_granted':
      case 'credential_revoked':
      case 'credential_status': {
        const cs = payload || {};
        setMessages(prev => [...prev, { type: 'system', content: cs.message || cs.info || '凭证状态已更新' }]);
        break;
      }
      case 'platform_added': {
        const pa = payload || {};
        setMessages(prev => [...prev, { type: 'system', content: `平台 ${pa.platform_id || ''} 已添加` }]);
        break;
      }
      case 'watchlist_updated': {
        const wu = payload || {};
        setMessages(prev => [...prev, { type: 'system', content: `自选股已更新: ${(wu.symbols || []).join(', ')}` }]);
        break;
      }
      case 'platforms_list': {
        const pl = payload || {};
        const plIds = (pl.platforms || []).map(p => p.id || p).join(', ');
        setMessages(prev => [...prev, { type: 'system', content: plIds ? `已连接平台: ${plIds}` : '暂无已连接平台' }]);
        break;
      }
      case 'credential_schemas': {
        const csch = payload || {};
        setMessages(prev => [...prev, { type: 'system', content: csch.message || '凭证配置已更新' }]);
        break;
      }
      case 'trade_screenshot': {
        const imgData = payload?.image || '';
        if (imgData && (imgData.startsWith('data:image/') || imgData.startsWith('/9j/'))) {
          setMessages(prev => [...prev, { type: 'system', content: '📊 交易截图', image: imgData }]);
        }
        break;
      }
      case 'voice_call_started':
        setNeuroState('thinking');
        setMessages(prev => [...prev, { type: 'system', content: '🎤 语音通话已开始' }]);
        break;
      case 'voice_stt_result':
        if (payload?.text) {
          setMessages(prev => [...prev, { type: 'assistant', content: maskSecrets(payload.text) }]);
        }
        break;
      case 'voice_call_ended':
        setNeuroState('idle');
        setMessages(prev => [...prev, { type: 'system', content: '🔇 语音通话已结束' }]);
        break;
      case 'voice_changed':
        setMessages(prev => [...prev, { type: 'system', content: `🔊 语音已切换: ${payload?.voice || ''}` }]);
        break;
      case 'voice_list':
        setMessages(prev => [...prev, { type: 'system', content: `可用语音: ${(payload?.voices || []).join(', ')}` }]);
        break;
      case 'user_prefs': {
        if (payload && typeof payload === 'object') {
          const risky = payload.risk_tolerance || payload.risk_mode || '';
          const watchlist = (payload.watchlist || []).join(', ');
          if (risky || watchlist) {
            setMessages(prev => [...prev, { type: 'system', content: `⚙️ 偏好: ${risky ? `风控=${risky}` : ''}${watchlist ? ` 自选=${watchlist}` : ''}` }]);
          }
        }
        break;
      }
      case 'em_earnings_review':
      case 'em_industry_research':
      case 'em_tracking_report':
      case 'em_comparable_company': {
        const emContent = payload?.content || payload?.answer || '暂无数据';
        setMessages(prev => [...prev, { type: 'system', content: `📊 ${emContent}` }]);
        break;
      }
      case 'stock_changes': {
        const changes = payload?.changes || [];
        const changeCount = changes.length;
        setMessages(prev => [...prev, { type: 'system', content: `📈 异动监控: 发现${changeCount}只异动股票` }]);
        break;
      }
      case 'hot_tables': {
        const tables = payload?.data || [];
        setMessages(prev => [...prev, { type: 'system', content: `🀄 龙虎榜: ${tables.length > 0 ? `获取${tables.length}条数据` : '暂无数据'}` }]);
        break;
      }
      case 'chip_distribution': {
        const chipData = payload?.data || {};
        setMessages(prev => [...prev, { type: 'system', content: `📊 筹码分布: ${Object.keys(chipData).length > 0 ? '已获取' : '暂无数据'}` }]);
        break;
      }
      case 'sentiment_analysis': {
        const score = payload?.score || 0;
        const category = payload?.category || '中性';
        const emoji = category === '看涨' ? '🟢' : category === '看跌' ? '🔴' : '⚪';
        setMessages(prev => [...prev, { type: 'system', content: `${emoji} 情感分析: ${category} (得分: ${score})` }]);
        break;
      }
      case 'realtime_quote': {
        const q = payload || {};
        if (q.name) {
          setMessages(prev => [...prev, { type: 'system', content: `💹 ${q.name}(${q.code}): ¥${q.price} ${q.change_pct >= 0 ? '📈' : '📉'}${q.change_pct}%` }]);
        } else {
          setMessages(prev => [...prev, { type: 'system', content: '❌ 行情获取失败' }]);
        }
        break;
      }
      case 'em_financial_qa':
      case 'em_query': {
        const answer = payload?.content || payload?.answer || '暂无回答';
        setMessages(prev => [...prev, { type: 'system', content: `🤖 ${answer}` }]);
        break;
      }
      case 'em_hotspot_discovery':
      case 'em_hotspot': {
        const hotspotData = payload?.content || payload?.data || '暂无热点数据';
        setMessages(prev => [...prev, { type: 'system', content: `🔥 热点板块: ${typeof hotspotData === 'string' ? hotspotData.substring(0, 200) : '已获取'}` }]);
        break;
      }
      case 'iwencai_query':
      case 'iwencai_select': {
        const iwencaiText = payload?.text || payload?.result?.text || '暂无数据';
        setMessages(prev => [...prev, { type: 'system', content: `🔍 ${iwencaiText.substring(0, 300)}` }]);
        break;
      }
      case 'iwencai_search': {
        const searchResults = payload?.result?.data || [];
        const searchCount = searchResults.length;
        setMessages(prev => [...prev, { type: 'system', content: `📰 搜索结果: ${searchCount}条${searchCount > 0 ? '资讯' : ''}` }]);
        break;
      }
      case 'trendradar_trending': {
        const items = payload?.items || [];
        const tCount = payload?.count || items.length;
        const tPlatforms = payload?.platforms ? Object.values(payload.platforms).slice(0, 3).join('、') : '';
        setMessages(prev => [...prev, { type: 'system', content: `🔥 热点监控: ${tPlatforms}等${tCount}条热点` }]);
        if (window._trHandler) { window._trHandler({ type: 'trendradar_trending', payload }); }
        break;
      }
      case 'trendradar_search': {
        const sItems = payload?.items || [];
        const sCount = payload?.count || sItems.length;
        const sKw = payload?.keyword || '';
        setMessages(prev => [...prev, { type: 'system', content: `🔍 热点搜索「${sKw}」: ${sCount}条结果` }]);
        if (window._trHandler) { window._trHandler({ type: 'trendradar_search', payload }); }
        break;
      }
      case 'trendradar_sentiment': {
        const totalTopics = payload?.total_topics || 0;
        const financeCount = payload?.total_finance_related || 0;
        const financeRatio = payload?.finance_ratio || 0;
        setMessages(prev => [...prev, { type: 'system', content: `📊 舆情分析: ${totalTopics}条热点, 金融相关${financeCount}条(${financeRatio}%)` }]);
        if (window._trHandler) { window._trHandler({ type: 'trendradar_sentiment', payload }); }
        break;
      }
      default:
        break;
    }
  }, [queueAudioChunk]);

  const [backendPort, setBackendPort] = useState(() => {
    if (typeof window !== 'undefined' && window.__BACKEND_PORT__) return window.__BACKEND_PORT__;
    if (typeof window !== 'undefined' && window.location.port && !['5173','5174','3000'].includes(window.location.port)) return window.location.port;
    return 8000;
  });

  useEffect(() => {
    const onPortReady = (e) => setBackendPort(e.detail);
    window.addEventListener('backend-port-ready', onPortReady);
    return () => window.removeEventListener('backend-port-ready', onPortReady);
  }, []);

  const BACKEND_PORT = backendPort;
  const WS_URL = `://${window.location.hostname}:${BACKEND_PORT}/ws`;
  const wsProto = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const fullWsUrl = typeof window !== 'undefined' ? `${wsProto}${WS_URL}` : 'ws://127.0.0.1:8000/ws';
  const { sendPacket, connected } = useNeuroSocket(fullWsUrl, handleServerPacket);

  const prevConnectedRef = useRef(connected);
  useEffect(() => {
    if (connected) {
      if (prevConnectedRef.current === false) {
        setMessages(prev => [...prev, { type: 'system', content: '✅ 连接已恢复' }]);
        showToast('连接已恢复', 'success');
      }
      sendPacket({ type: 'vault_status', payload: {} });
      fetch(`http://${window.location.hostname}:${backendPort}/health`).then(r => r.json()).then(setSystemStatus).catch(() => {});
    } else {
      if (prevConnectedRef.current === true) {
        setMessages(prev => [...prev, { type: 'system', content: '⚠️ 与服务器断开连接，正在重连...' }]);
        showToast('连接断开', 'warning');
      }
    }
    prevConnectedRef.current = connected;
  }, [connected]);

  useEffect(() => {
    const timers = [
      setTimeout(() => setSplashStage('backend'), 300),
      setTimeout(() => setSplashStage('ws'), 800),
      setTimeout(() => setSplashStage('live2d'), 1400),
      setTimeout(() => setSplashStage(null), 2200),
    ];
    return () => timers.forEach(clearTimeout);
  }, []);

  useEffect(() => {
    const handler = (action) => {
      if (action === 'trade_analysis') {
        setChatOpen(true);
        sendPacket({ type: 'text_input', payload: { text: '帮我分析最近值得关注的股票' } });
      } else if (action === 'plan_execute_analysis') {
        setChatOpen(true);
        sendPacket({ type: 'text_input', payload: { text: '深度分析自选股，多步分析' } });
      } else if (action === 'trade_status') {
        setChatOpen(true);
        sendPacket({ type: 'trade_status', payload: {} });
      } else if (action === 'cleanup_pc') {
        setChatOpen(true);
        sendPacket({ type: 'cleanup_pc', payload: { level: 'quick' } });
      }
    };
    if (window.potatoAPI && window.potatoAPI.onTrayAction) {
      window.potatoAPI.onTrayAction(handler);
    }
    return () => {};
  }, [sendPacket]);

  useEffect(() => {
    if (!window.potatoAPI || !window.potatoAPI.onSystemEvent) return;
    const handler = (data) => {
      if (data.type === 'backend_crash') {
        setMessages(prev => [...prev, { type: 'system', content: '⚠️ 后端进程异常退出，正在自动重启...' }]);
        notify({ type: 'backend_crash', payload: data });
      } else if (data.type === 'agent_crash') {
        setMessages(prev => [...prev, { type: 'system', content: '⚠️ Bytebot Agent异常退出，正在自动重启...' }]);
        notify({ type: 'agent_crash', payload: data });
      } else if (data.type === 'backend_timeout') {
        setMessages(prev => [...prev, { type: 'system', content: '❌ 后端启动超时，请检查Python环境' }]);
      } else if (data.type === 'suspend') {
        setMessages(prev => [...prev, { type: 'system', content: '💻 系统即将休眠' }]);
      } else if (data.type === 'resume') {
        setMessages(prev => [...prev, { type: 'system', content: '💻 系统已恢复运行' }]);
      }
    };
    window.potatoAPI.onSystemEvent(handler);
    return () => {};
  }, [notify]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, actionSteps]);

  const handleChatScroll = useCallback(() => {
    const el = chatMessagesRef.current;
    if (!el) return;
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollBottom(distFromBottom > 80);
  }, []);

  const handleContextMenu = useCallback((e) => {
    e.preventDefault();
    const items = [
      { icon: '📋', label: '粘贴并发送', shortcut: 'Ctrl+V', action: () => { navigator.clipboard.readText().then(t => { if (t?.trim()) { sendPacket({ type: 'text_input', payload: { text: t.trim() } }); setChatOpen(true); } }); }},
      { icon: '🔍', label: '搜索聊天', shortcut: 'Ctrl+F', action: () => setShowChatSearch(true) },
      { icon: '💾', label: '导出聊天', shortcut: 'Ctrl+E', action: handleExportChat },
      { sep: true },
      { icon: '🌙', label: effectiveTheme === 'dark' ? '切换浅色' : '切换深色', shortcut: 'Ctrl+D', action: cycleTheme },
      { icon: '🌐', label: isZh ? 'Switch to English' : '切换到中文', shortcut: 'Ctrl+L', action: () => switchLang(isZh ? 'en' : 'zh') },
      { sep: true },
      { icon: '⌨️', label: '快捷键帮助', shortcut: '?', action: () => setShowKeyboardHelp(true) },
    ];
    setContextMenu({ x: e.clientX, y: e.clientY, items });
  }, [sendPacket, effectiveTheme, isZh, cycleTheme, switchLang, handleExportChat]);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    setShowScrollBottom(false);
  }, []);

  // ── 麦克风录音 ──
  const startRecording = useCallback(async () => {
    if (recording || neuroState === 'thinking') return;
    try {
      console.log('[mic] 请求麦克风权限...');
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      });
      console.log('[mic] 麦克风已获取', stream.getAudioTracks().map(t => t.label));
      streamRef.current = stream;
      chunksRef.current = [];
      const chunks = [];
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: 'audio/webm' });
        console.log('[mic] 录音结束, 大小:', blob.size);
        if (blob.size > 0) {
          const reader = new FileReader();
          reader.onload = () => {
            const base64 = reader.result.split(',')[1];
            console.log('[mic] 发送音频, base64长度:', base64.length);
            sendPacket({ type: 'audio_input', payload: { audio_base64: base64, format: 'audio/webm' } });
          };
          reader.readAsDataURL(blob);
        } else {
          setMessages(prev => [...prev, { type: 'system', content: '⚠️ 录音为空，请重试' }]);
          setNeuroState('idle');
        }
        stream.getTracks().forEach(t => t.stop());
        streamRef.current = null;
        mediaRecorderRef.current = null;
        setRecording(false);
        setNeuroState('thinking');
      };
      recorder.start();
      setRecording(true);
      setChatOpen(true);
      setMessages(prev => [...prev, { type: 'system', content: '🎤 录音中...再点🎤结束' }]);
      micTimerRef.current = setTimeout(() => {
        if (mediaRecorderRef.current === recorder && recorder.state === 'recording') {
          recorder.stop();
        }
      }, 15000);
    } catch (e) {
      console.warn('[mic] 录音失败:', e);
      let hint = e.message || '未知错误';
      if (e.name === 'NotAllowedError') hint = '麦克风权限被拒绝，请在系统设置中允许';
      if (e.name === 'NotFoundError') hint = '未找到麦克风设备';
      if (e.name === 'NotReadableError') hint = '麦克风被其他程序占用';
      setMessages(prev => [...prev, { type: 'system', content: `❌ 麦克风: ${hint}` }]);
      setRecording(false);
    }
  }, [recording, neuroState, sendPacket]);

  const stopRecording = useCallback(() => {
    if (micTimerRef.current) { clearTimeout(micTimerRef.current); micTimerRef.current = null; }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
  }, []);

  const handleMicClick = useCallback(() => {
    if (recording) {
      stopRecording();
    } else {
      if (!chatOpen) setChatOpen(true);
      startRecording();
    }
  }, [recording, chatOpen, startRecording, stopRecording]);

  const interruptNeuro = () => {
    stopAudio();
    sendPacket({ type: "interrupt" });
  };

  const handleSend = () => {
    const text = inputText.trim();
    if (!text) return;
    setInputText('');
    setActionSteps([]);
    if (neuroState === "speaking" || isPlaying) interruptNeuro();

    const detected = detectKey(text);
    if (detected) {
      if (detected.key === 'MANUAL_KEY') {
        setMessages(prev => [...prev, { type: 'system', content: '⚠️ 未能识别密钥类型，请用格式 key=value 粘贴（如 DEEPSEEK_API_KEY=sk-xxx）' }]);
        return;
      }
      sendPacket({ type: 'vault_store', payload: { key: detected.key, value: detected.value } });
      setMessages(prev => [...prev, { type: 'system', content: `🔐 正在保存 ${detected.key}...` }]);
      return;
    }

    setMessages(prev => [...prev, { type: 'user', content: maskSecrets(text) }]);
    sendPacket({ type: "text_input", payload: { text } });
  };

  const handleDeleteMessage = useCallback((msg) => {
    setMessages(prev => prev.filter(m => m.ts !== msg.ts));
    showToast('消息已删除', 'info', 1500);
  }, [setMessages]);

  const handleRetryMessage = useCallback((msg) => {
    if (msg.type === 'user' && msg.content) {
      const text = msg.content.replace(/^\[.*?hidden\]/g, '').trim();
      if (text) {
        sendPacket({ type: 'text_input', payload: { text } });
        showToast('已重试', 'info', 1500);
      }
    }
  }, [sendPacket]);

  const handleJumpToMessage = useCallback((idx) => {
    setShowChatSearch(false);
    setChatOpen(true);
    setTimeout(() => {
      if (chatMessagesRef.current) {
        const msgs = chatMessagesRef.current.querySelectorAll('.chat-msg');
        if (msgs[idx]) {
          msgs[idx].scrollIntoView({ behavior: 'smooth', block: 'center' });
          msgs[idx].style.outline = '2px solid var(--accent)';
          setTimeout(() => { msgs[idx].style.outline = ''; }, 2000);
        }
      }
    }, 100);
  }, []);

  const togglePin = useCallback((msg) => {
    setPinnedMessages(prev => {
      const exists = prev.find(p => p.ts === msg.ts);
      const next = exists ? prev.filter(p => p.ts !== msg.ts) : [...prev, { ts: msg.ts, content: msg.content, type: msg.type }];
      try { localStorage.setItem('potato_pinned', JSON.stringify(next)); } catch {}
      showToast(exists ? '已取消置顶' : '📌 已置顶', 'info', 1500);
      return next;
    });
  }, []);

  const handleExportChat = useCallback(() => {
    const text = messages.map(m => `[${formatTs(m.ts)}] ${m.type}: ${typeof m.content === 'string' ? m.content : ''}`).join('\n');
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `potato-chat-${new Date().toISOString().slice(0, 10)}.txt`;
    a.click(); URL.revokeObjectURL(url);
    showToast('聊天已导出', 'success');
  }, [messages]);

  const handleCommandAction = useCallback((action) => {
    if (action === 'export') { handleExportChat(); }
    else if (action === 'clear') { clearMessages(); showToast('聊天已清空', 'info'); }
    else if (action === 'theme') { cycleTheme(); }
    else if (action === 'lang') { switchLang(isZh ? 'en' : 'zh'); }
  }, [clearMessages, cycleTheme, switchLang, isZh]);

  const handleQuickAction = (action) => {
    if (action.msg === '__vault__') {
      sendPacket({ type: 'vault_status', payload: {} });
      setChatOpen(true);
      return;
    }
    if (action.msg === '__data_panel__') {
      setShowDataPanel(true);
      return;
    }
    if (action.msg === '__bytebot__') {
      sendPacket({ type: 'bytebot_status', payload: {} });
      setChatOpen(true);
      return;
    }
    if (action.msg === '__memory__') {
      sendPacket({ type: 'get_memory', payload: {} });
      setChatOpen(true);
      return;
    }
    if (action.msg === '__broker_balance__') {
      sendPacket({ type: 'broker_balance', payload: {} });
      setChatOpen(true);
      return;
    }
    if (action.msg === '__billing_dashboard__') {
      sendPacket({ type: 'billing_dashboard', payload: {} });
      setChatOpen(true);
      return;
    }
    if (action.msg === '__billing_renewal_payment__') {
      sendPacket({ type: 'billing_renewal_payment', payload: {} });
      setChatOpen(true);
      return;
    }
    if (action.msg === '__broker_switch__') {
      sendPacket({ type: 'broker_status', payload: {} });
      setChatOpen(true);
      setTimeout(() => {
        const isLive = window.__brokerIsLive || false;
        const nextMode = isLive ? 'dry_run' : 'live';
        const confirmMsg = nextMode === 'live'
          ? '⚠️ 切换到实盘模式会下真实订单！确定要切换吗？'
          : '切换到模拟模式，不会下真实订单。';
        setMessages(prev => [...prev, {
          type: 'system',
          content: confirmMsg,
          actions: [
            { label: nextMode === 'live' ? '🔴 确认实盘' : '🟡 确认模拟', action: 'broker_switch_confirm', payload: { mode: nextMode } },
          ]
        }]);
      }, 500);
      return;
    }
    if (action.msg === '__check_updates__') {
      if (window.potatoAPI && window.potatoAPI.checkForUpdates) {
        setMessages(prev => [...prev, { type: 'system', content: '🔍 正在检查更新...' }]);
        window.potatoAPI.checkForUpdates().then(result => {
          if (result.ok) {
            setMessages(prev => [...prev, { type: 'system', content: `ℹ️ 当前已是最新版本 (v${result.version})` }]);
          } else {
            setMessages(prev => [...prev, { type: 'system', content: `⚠️ 检查更新失败: ${result.error}` }]);
          }
        });
      } else {
        setMessages(prev => [...prev, { type: 'system', content: 'ℹ️ 更新检查仅在桌面端可用' }]);
      }
      return;
    }
    if (action.msg === '__settings__') {
      setShowSettings(true);
      return;
    }
    if (action.msg === '__trade_history__') {
      setShowTradeHistory(true);
      return;
    }
    if (action.msg === '__dashboard__') {
      setDashboardTab('chart');
      setChatOpen(true);
      return;
    }
    setChatOpen(true);
    setMessages(prev => [...prev, { type: 'user', content: action.msg }]);
    sendPacket({ type: "text_input", payload: { text: action.msg } });
  };

  const handleOpenRenewal = (keyEnv) => {
    sendPacket({ type: 'open_renewal_url', payload: { key: keyEnv } });
    setRenewalProviders([]);
  };

  const handleModelSwitch = (modelId) => {
    setCurrentModel(modelId);
    saveModelId(modelId);
    const config = getModelConfig(modelId);
    setMessages(prev => [...prev, { type: 'system', content: `🎭 切换模型: ${config ? (config.nameZh || config.name) : modelId}` }]);
  };

  const stateLabel = recording ? '🎤 录音中' : neuroState === 'thinking' ? '思考中...' : neuroState === 'speaking' ? '说话中' : '待命';
  const stateColor = recording ? '#ff8a80' : neuroState === 'thinking' ? '#64b5f6' : neuroState === 'speaking' ? '#ffb74d' : '#69f0ae';

  // Live2D expression from neuroState
  useEffect(() => {
    if (!live2dRef.current) return;
    const expr = stateToExpression(neuroState, currentModel);
    if (expr) {
      live2dRef.current.showExpression(expr, true);
    } else if (neuroState === 'idle') {
      live2dRef.current.resetExpression?.();
    }
  }, [neuroState, currentModel]);

  if (splashStage) {
    const progressMap = { init: 10, backend: 30, ws: 60, live2d: 85, ready: 100 };
    return <SplashScreen stage={splashStage} progress={progressMap[splashStage] || 0} />;
  }

  return (
    <ErrorBoundary
      fallbackTitle={t('error_boundary.title')}
      fallbackMessage={t('error_boundary.message')}
    >
    <ToastContainer />
    <CommandPalette
      onSend={(msg) => {
        if (msg.startsWith('__')) { handleQuickAction({ msg }); }
        else { sendPacket({ type: 'text_input', payload: { text: msg } }); setChatOpen(true); }
      }}
      onAction={handleCommandAction}
      lang={isZh ? 'zh' : 'en'}
    />
    <div className="app">
      {/* 桌宠：全屏 */}
      <div className="pet-layer">
        <Live2DController ref={live2dRef} modelId={currentModel} />
        <ModelPicker currentModel={currentModel} onSwitch={handleModelSwitch} />

        {recording && <div className="recording-ring" />}
        {recording && <div className="recording-ring-text">🎤</div>}

        <div className="subtitles">
          {neuroState === "thinking" ? (
            <div className="status-indicator"><LoadingDots /> 思考中</div>
          ) : (
            subtitle && <div className="subtitle-text">{subtitle}</div>
          )}
        </div>

        {/* 胸口隐形触摸区：点一下=开始/停止录音，聊天卡片打开 */}
        <div className="pet-tap-zone" onClick={handleMicClick} />

        {!chatOpen && neuroState === 'idle' && !recording && (
          <div className="tap-hint">👆 点我开始对话</div>
        )}
      </div>

      {/* 聊天浮窗：左侧 */}
      <div className={`chat-card ${chatOpen ? 'visible' : 'hidden'}`} style={{ width: chatWidth, transition: isDragging?.current ? 'none' : 'width 0.2s' }} onContextMenu={handleContextMenu}>
        <div className="chat-resize-handle" {...resizeHandleProps} style={{ position: 'absolute', top: 0, bottom: 0, right: 0, width: 6, cursor: 'ew-resize', zIndex: 10 }} />
        <div className="chat-card-head">
          <div className="head-left">
            <span className="dot" style={{ background: stateColor, color: stateColor }}></span>
            <span className="title">🥔 小土豆</span>
            <span className="state">{stateLabel}</span>
            {systemStatus && (
              <span style={{ fontSize: 10, opacity: 0.5, marginLeft: 4 }}>
                {connected ? '' : '⚠️断开'}
                {systemStatus.data_sources?.demo_mode ? '📋demo' :
                 systemStatus.data_sources?.active_providers > 0 ?
                 `🟢${systemStatus.data_sources.active_providers}key` : '🔴0key'}
              </span>
            )}
            <button
              onClick={() => wakeListening ? stopWakeListener() : startWakeListener()}
              style={{
                marginLeft: 6, fontSize: 11, border: 'none', cursor: 'pointer',
                background: wakeListening ? 'rgba(0,200,120,0.3)' : 'rgba(255,255,255,0.08)',
                borderRadius: 8, padding: '2px 6px', color: wakeListening ? '#4fc3f7' : '#888',
              }}
              title={wakeListening ? '语音唤醒已开启（喊"小土豆"即可对话）' : '点击开启语音唤醒'}
            >
              {wakeListening ? '🔊唤醒' : '🔇唤醒'}
            </button>
          </div>
          <button className="close-btn" onClick={() => setChatOpen(false)}>✕</button>
            <button onClick={clearMessages} title="清空聊天记录" style={{ background: 'none', border: 'none', color: '#888', fontSize: 14, cursor: 'pointer', padding: '0 4px', marginLeft: 4 }}>🗑️</button>
            <button onClick={() => switchLang(isZh ? 'en' : 'zh')} title={isZh ? 'Switch to English' : '切换到中文'} style={{ background: 'none', border: 'none', color: isZh ? '#69f0ae' : '#888', fontSize: 14, cursor: 'pointer', padding: '0 4px', marginLeft: 4 }}>🌐</button>
<button onClick={cycleTheme} title={theme === 'dark' ? '切换浅色' : theme === 'light' ? '跟随系统' : '切换深色'} style={{ background: 'none', border: 'none', color: '#888', fontSize: 14, cursor: 'pointer', padding: '0 4px', marginLeft: 4 }}>{effectiveTheme === 'dark' ? '🌙' : '☀️'}</button>
            <button onClick={() => setShowChatSearch(s => !s)} title="搜索聊天" style={{ background: 'none', border: 'none', color: '#888', fontSize: 14, cursor: 'pointer', padding: '0 4px', marginLeft: 4 }}>🔍</button>
         </div>

        {showChatSearch && (
          <ChatSearch
            messages={messages}
            onJumpTo={handleJumpToMessage}
            onClose={() => setShowChatSearch(false)}
            lang={isZh ? 'zh' : 'en'}
          />
        )}

        <div className="chat-quick">
          {QUICK_ACTIONS.map(a => (
            <button key={a.label} onClick={() => handleQuickAction(a)}>{a.label}</button>
          ))}
        </div>

        <QuickReplyChips
          onSend={(msg) => { sendPacket({ type: 'text_input', payload: { text: msg } }); setChatOpen(true); }}
          lastMessageType={messages.length > 0 ? messages[messages.length - 1].type : 'system'}
        />

        <div className="chat-msgs" ref={chatMessagesRef} onScroll={handleChatScroll}>
          {!connected && (
            <div style={{ position: 'sticky', top: 0, zIndex: 10, background: 'rgba(255,82,82,0.15)', borderBottom: '1px solid rgba(255,82,82,0.3)', color: '#ff8a80', textAlign: 'center', fontSize: 12, padding: '6px', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              ⚠️ 连接断开，正在重连...
              <button onClick={() => window.location.reload()} style={{ background: 'rgba(255,82,82,0.2)', border: '1px solid rgba(255,82,82,0.4)', borderRadius: 6, color: '#ff8a80', padding: '2px 10px', cursor: 'pointer', fontSize: 11 }}>🔄 刷新</button>
            </div>
          )}
          {pinnedMessages.length > 0 && (
            <div style={{ background: 'var(--msg-success)', borderRadius: 8, padding: '6px 10px', marginBottom: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 11, color: 'var(--accent)', marginBottom: 2, cursor: 'pointer' }} onClick={() => setShowPinned(s => !s)}>
                📌 置顶消息 ({pinnedMessages.length}) {showPinned ? '▲' : '▼'}
              </div>
              {showPinned && pinnedMessages.map(p => (
                <div key={p.ts} style={{ fontSize: 12, color: 'var(--text-secondary)', padding: '2px 0', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{typeof p.content === 'string' ? p.content.slice(0, 60) : ''}</span>
                  <button onClick={() => togglePin(p)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 10, marginLeft: 6 }}>✕</button>
                </div>
              ))}
            </div>
          )}
          {neuroState === 'thinking' && chatOpen && (
            <div className="chat-msg assistant" style={{ opacity: 0.7 }}>
              <div style={{ fontSize: 13, color: '#64b5f6' }}>
                思考中<LoadingDots />
              </div>
            </div>
          )}
          {messages.length === 0 && vaultReady === null && (
            <div className="empty-hint">正在连接...</div>
          )}
          {messages.length === 0 && vaultReady === false && (
            <div className="empty-hint">
              点胸口🎤开始语音<br/>
              <span className="sub">或先粘贴密钥：sk-xxx</span>
            </div>
          )}
          {messages.length === 0 && vaultReady === true && (
            <div className="empty-hint">
              点🎤语音或打字对话<br/>
              <span className="sub">密钥已就绪 ✓</span>
            </div>
          )}
          {messages.map((msg, i) => {
            const semanticClass = msg.type === 'system' && typeof msg.content === 'string'
              ? msg.content.startsWith('❌') || msg.content.startsWith('⚠️') || msg.content.startsWith('🛑') ? ' error'
                : msg.content.startsWith('✅') || msg.content.startsWith('🔗') ? ' success'
                : msg.content.startsWith('🟢') || msg.content.startsWith('🔴') || msg.content.startsWith('📊') || msg.content.startsWith('🔬') ? ' trade'
                : msg.content.startsWith('⚠️') || msg.content.startsWith('🛡️') ? ' warning'
                : ''
              : '';
            return (
            <div key={msg._key || msg.ts || i} className={`chat-msg ${msg.type}${semanticClass}`}
              style={{ position: 'relative', cursor: msg.type === 'system' || msg.type === 'user' || msg.type === 'assistant' ? 'pointer' : 'default' }}
              onClick={() => copyToClipboard(typeof msg.content === 'string' ? msg.content : '')}
              title="点击复制">
              <div style={{ fontSize: '10px', opacity: 0.4, marginBottom: 2 }}>{formatTs(msg.ts)}</div>
              {msg.type === 'image' && msg.content && msg.content.startsWith('data:image') ? (
                <div>
                  <img src={msg.content} alt={msg.alt || 'QR Code'} style={{ maxWidth: '200px', borderRadius: '8px', cursor: 'pointer' }} onClick={() => window.open(msg.content, '_blank')} />
                  {msg.alt && <div style={{ fontSize: '11px', color: '#888', marginTop: '4px' }}>{msg.alt}</div>}
                </div>
) : msg.type === 'system' && msg.content.includes('录音中') ? (
                 <>
                   {msg.content}
                   <div className="voice-bars">
                     <div className="bar" /><div className="bar" /><div className="bar" /><div className="bar" /><div className="bar" />
                   </div>
                 </>
               ) : (msg.type === 'system' || msg.type === 'assistant') && typeof msg.content === 'string' && msg.content.includes('\n') ? (
                 renderMessageContent(msg.content)
               ) : msg.content}
              {msg.image && (msg.image.startsWith('data:image/') || msg.image.startsWith('/9j/')) && (
                <img src={msg.image} alt="screenshot" className="chat-screenshot" />
              )}
              {msg.actions && msg.actions.length > 0 && (
                <div className="msg-actions" style={{ marginTop: '8px', display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                  {msg.actions.map((act, ai) => (
                    <button key={ai} style={{ padding: '4px 12px', borderRadius: '12px', fontSize: '12px', cursor: 'pointer', border: '1px solid #4a7c3f', background: act.payload?.mode === 'live' ? '#c0392b' : '#27ae60', color: '#fff' }}
                      onClick={() => {
                        if (act.action === 'broker_switch_confirm') {
                          sendPacket({ type: 'broker_switch', payload: { mode: act.payload?.mode || 'dry_run' } });
                        } else if (act.action === 'update_risk') {
                          sendPacket({ type: 'update_risk', payload: act.payload || {} });
                        }
                        setMessages(prev => prev.map((m, mi) => mi === i ? { ...m, actions: [] } : m));
                      }}>
                      {act.label}
                    </button>
                  ))}
                </div>
)}
              <MessageActions message={msg} onRetry={handleRetryMessage} onDelete={handleDeleteMessage} onPin={togglePin} isPinned={pinnedMessages.some(p => p.ts === msg.ts)} lang={isZh ? 'zh' : 'en'} />
            </div>
            );
          })}
          <div ref={messagesEndRef} />
          {showScrollBottom && (
            <button onClick={scrollToBottom} style={{
              position: 'sticky', bottom: 0, left: '50%', transform: 'translateX(-50%)',
              background: 'rgba(105,240,174,0.2)', border: '1px solid rgba(105,240,174,0.4)',
              borderRadius: 20, padding: '4px 14px', color: '#69f0ae', fontSize: 12,
              cursor: 'pointer', backdropFilter: 'blur(8px)', zIndex: 5,
            }}>↓ 新消息</button>
          )}
        </div>

        <div className="chat-input-row">
          <textarea
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            placeholder={recording ? '🎤 录音中...' : '输入消息或粘贴密钥...\nShift+Enter换行'}
            disabled={neuroState === "thinking"}
            rows={1}
            style={{
              flex: 1, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 12, padding: '8px 12px', color: '#ddd', fontSize: 13,
              resize: 'none', outline: 'none', minHeight: 36, maxHeight: 120, lineHeight: 1.4,
              fontFamily: 'inherit', scrollbarWidth: 'thin',
            }}
            onInput={e => { e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'; }}
          />
          <button className="send-btn" onClick={handleSend} disabled={!inputText.trim()} title="发送">&#10148;</button>
        </div>
        {bytebotTaskId && (
            <div className="renewal-bar">
              <button
                className="renewal-btn"
                onClick={() => { sendPacket({ type: 'bytebot_cancel', payload: { task_id: bytebotTaskId } }); }}
                style={{ background: 'linear-gradient(135deg, #ef4444, #f87171)', borderColor: 'rgba(239,68,68,0.5)' }}
                title="取消正在执行的Bytebot任务"
              >
                ⏹ 取消任务
              </button>
            </div>
          )}
          {renewalProviders.length > 0 && (
          <div className="renewal-bar">
            {renewalProviders.map(p => (
              <button
                key={p.key_env}
                className="renewal-btn"
                onClick={() => handleOpenRenewal(p.key_env)}
                title={`打开 ${p.desc} 续费页面`}
              >
                🔗 续费 {p.desc}
              </button>
            ))}
          </div>
        )}
      </div>
      {showBillingPanel && <BillingPanel
        data={billingPanelData}
        onClose={() => setShowBillingPanel(false)}
        onRenew={() => { setShowBillingPanel(false); sendPacket({ type: 'billing_renewal_payment', payload: {} }); }}
        onTopup={(amount) => { sendPacket({ type: 'billing_topup', payload: { amount } }); }}
      />}
      {showRenewalPanel && <RenewalPanel
        data={renewalPanelData}
        onClose={() => setShowRenewalPanel(false)}
        onConfirmPayment={() => { sendPacket({ type: 'billing_confirm_payment', payload: { amount: renewalPanelData?.total_renewal_cny || 0 } }); }}
      />}
      {showDataPanel && (
        <div className="sidebar-overlay" onClick={() => setShowDataPanel(false)} />
      )}
      {showDataPanel && (
        <div className="sidebar open" style={{ right: 'auto', left: 0, width: 320 }}>
          <div className="sidebar-header">
            <span style={{ fontSize: 15, fontWeight: 700 }}>📡 数据源</span>
            <button className="sidebar-close-btn" onClick={() => setShowDataPanel(false)}>&#215;</button>
          </div>
          <DataPanel sendPacket={sendPacket} messages={messages} />
        </div>
      )}

      {showSettings && (
        <SettingsPanel
          onClose={() => setShowSettings(false)}
          wakeListening={wakeListening}
          toggleWakeWord={wakeListening ? stopWakeListener : startWakeListener}
          alwaysOnTop={alwaysOnTop}
          onToggleAlwaysOnTop={() => {
            const next = !alwaysOnTop;
            setAlwaysOnTop(next);
            if (window.potatoAPI?.setAlwaysOnTop) window.potatoAPI.setAlwaysOnTop(next);
          }}
          messages={messages}
          sendPacket={sendPacket}
        />
      )}

      {showTradeHistory && (
        <TradeHistoryPanel
          onClose={() => setShowTradeHistory(false)}
          sendPacket={sendPacket}
          messages={messages}
        />
      )}

      {/* Dashboard overlay */}
      {chatOpen && (
        <div style={{
          position: 'fixed', top: 60, left: 16, bottom: 16, width: 380,
          background: 'var(--bg-secondary)', borderRadius: 16, border: '1px solid var(--border)',
          boxShadow: '0 8px 32px var(--shadow)', zIndex: 100, overflow: 'hidden',
          display: dashboardTab ? 'flex' : 'none', flexDirection: 'column',
        }}>
          <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', background: 'var(--bg-card)' }}>
            {[
              { id: 'chart', icon: '📈', label: isZh ? '行情' : 'Market' },
              { id: 'portfolio', icon: '💼', label: isZh ? '持仓' : 'Portfolio' },
              { id: 'strategy', icon: '🎯', label: isZh ? '策略' : 'Strategy' },
            ].map(tab => (
              <button key={tab.id} onClick={() => setDashboardTab(tab.id)} style={{
                flex: 1, padding: '8px 4px', border: 'none', cursor: 'pointer',
                background: dashboardTab === tab.id ? 'var(--bg-secondary)' : 'transparent',
                color: dashboardTab === tab.id ? 'var(--accent)' : 'var(--text-muted)',
                fontSize: 12, fontWeight: dashboardTab === tab.id ? 600 : 400,
                borderBottom: dashboardTab === tab.id ? '2px solid var(--accent)' : '2px solid transparent',
              }}>{tab.icon} {tab.label}</button>
            ))}
            <button onClick={() => setDashboardTab(null)} style={{
              padding: '0 10px', border: 'none', background: 'none', color: 'var(--text-muted)',
              cursor: 'pointer', fontSize: 14,
            }}>✕</button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {dashboardTab === 'chart' && <StockChart symbol={isZh ? '上证指数' : 'SSE Index'} width={356} height={220} />}
            {dashboardTab === 'portfolio' && <PortfolioDashboard lang={isZh ? 'zh' : 'en'} />}
            {dashboardTab === 'strategy' && <StrategyEditor riskConfig={{ mode: 'balanced', stopLoss: 5, takeProfit: 10, maxPositions: 3 }} onApply={(cfg) => { sendPacket({ type: 'update_risk', payload: cfg }); showToast('策略已应用', 'success'); }} lang={isZh ? 'zh' : 'en'} />}
          </div>
        </div>
      )}

      {/* Keyboard shortcuts */}
      <KeyboardShortcuts
        chatOpen={chatOpen}
        setChatOpen={setChatOpen}
        inputText={inputText}
        setInputText={setInputText}
        handleSend={handleSend}
        quickActions={QUICK_ACTIONS}
        handleQuickAction={handleQuickAction}
        setShowKeyboardHelp={setShowKeyboardHelp}
        setShowChatSearch={setShowChatSearch}
        cycleTheme={cycleTheme}
        switchLang={switchLang}
        isZh={isZh}
handleExportChat={handleExportChat}
      />

      {showOnboarding && (
        <OnboardingWizard
          onComplete={() => setShowOnboarding(false)}
          sendPacket={sendPacket}
        />
      )}

      {showKeyboardHelp && (
        <KeyboardHelp lang={isZh ? 'zh' : 'en'} onClose={() => setShowKeyboardHelp(false)} />
      )}

      {contextMenu && (
        <ContextMenu
          x={contextMenu.x} y={contextMenu.y}
          items={contextMenu.items}
          onClose={() => setContextMenu(null)}
          lang={isZh ? 'zh' : 'en'}
        />
      )}

      <DropOverlay
        onDrop={(text) => {
          const detected = detectKey(text);
          if (detected) {
            sendPacket({ type: 'vault_store', payload: { key: detected.key, value: detected.value } });
            setMessages(prev => [...prev, { type: 'system', content: `🔐 拖入密钥 ${detected.key}，正在保存...` }]);
            showToast(`${detected.key} 已识别`, 'success');
          } else {
            setMessages(prev => [...prev, { type: 'user', content: text.slice(0, 200) }]);
            sendPacket({ type: 'text_input', payload: { text: text.slice(0, 500) } });
          }
        }}
        lang={isZh ? 'zh' : 'en'}
      />

      {TooltipOverlay}
    </div>
    </ErrorBoundary>
  );
}