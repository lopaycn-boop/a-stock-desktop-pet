const zh = {
  app_name: '小土豆 AI操盘桌宠',
  chat_placeholder: '输入消息或按 Ctrl+Enter 发送...',
  send: '发送',
  settings: '设置',
  trade_history: '交易记录',
  close: '关闭',
  clear_chat: '清空聊天',
  copy: '复制',
  copied: '已复制',
  reconnect: '刷新',
  disconnected: '连接断开',
  connecting: '连接中...',
  thinking: '思考中...',
  onboarding: {
    welcome: '欢迎来到小土豆！',
    step1: '设置 API 密钥',
    step2: '开始聊天',
    step3: '开启操盘',
    step4: '设置风控',
    step5: '完成设置',
  },
  risk: {
    stop_loss: '止损',
    take_profit: '止盈',
    max_positions: '最多持仓',
    mode: '操盘模式',
    conservative: '稳健',
    balanced: '均衡',
    aggressive: '激进',
  },
  notifications: {
    trade_signal: '交易信号',
    risk_alert: '风险提醒',
    crash: '程序异常',
  },
  wake_word: '语音唤醒',
  always_on_top: '置顶',
  auto_start: '开机自启',
  volume: '音量',
  export_chat: '导出聊天',
  quick_actions: {
    market: '行情',
    analyze: '分析',
    review: '复盘',
    pick: '选股',
    opinion: '舆情',
    update: '更新',
  },
  memory_search: '记忆搜索',
  keys: '密钥',
  error_boundary: {
    title: '小土豆遇到了一点问题',
    message: '别担心，数据已保存。点击重置或刷新页面即可恢复。',
    reset: '重置界面',
    reload: '刷新页面',
    details: '错误详情',
  },
  splash: {
    init: '正在初始化...',
    backend: '连接后端...',
    ws: '建立通道...',
    live2d: '加载模型...',
    ready: '就绪！',
  },
};

const en = {
  app_name: 'Potato AI Trading Pet',
  chat_placeholder: 'Type a message or press Ctrl+Enter to send...',
  send: 'Send',
  settings: 'Settings',
  trade_history: 'Trade History',
  close: 'Close',
  clear_chat: 'Clear Chat',
  copy: 'Copy',
  copied: 'Copied',
  reconnect: 'Refresh',
  disconnected: 'Disconnected',
  connecting: 'Connecting...',
  thinking: 'Thinking...',
  onboarding: {
    welcome: 'Welcome to Potato!',
    step1: 'Set API Keys',
    step2: 'Start Chatting',
    step3: 'Enable Trading',
    step4: 'Set Risk Controls',
    step5: 'All Done!',
  },
  risk: {
    stop_loss: 'Stop Loss',
    take_profit: 'Take Profit',
    max_positions: 'Max Positions',
    mode: 'Mode',
    conservative: 'Conservative',
    balanced: 'Balanced',
    aggressive: 'Aggressive',
  },
  notifications: {
    trade_signal: 'Trade Signal',
    risk_alert: 'Risk Alert',
    crash: 'Crash',
  },
  wake_word: 'Wake Word',
  always_on_top: 'On Top',
  auto_start: 'Auto Start',
  volume: 'Volume',
  export_chat: 'Export Chat',
  quick_actions: {
    market: 'Market',
    analyze: 'Analyze',
    review: 'Review',
    pick: 'Pick',
    opinion: 'Sentiment',
    update: 'Update',
  },
  memory_search: 'Memory Search',
  keys: 'Keys',
  error_boundary: {
    title: 'Potato encountered an issue',
    message: 'Don\'t worry, your data is saved. Click Reset or Refresh to recover.',
    reset: 'Reset UI',
    reload: 'Refresh Page',
    details: 'Error Details',
  },
  splash: {
    init: 'Initializing...',
    backend: 'Connecting backend...',
    ws: 'Establishing channel...',
    live2d: 'Loading model...',
    ready: 'Ready!',
  },
};

const locales = { zh, en };

export function t(key, lang = 'zh') {
  const dict = locales[lang] || locales.zh;
  const parts = key.split('.');
  let val = dict;
  for (const p of parts) {
    if (val == null) return key;
    val = val[p];
  }
  return val != null ? val : key;
}

export function getAvailableLocales() {
  return Object.keys(locales);
}

export default locales;