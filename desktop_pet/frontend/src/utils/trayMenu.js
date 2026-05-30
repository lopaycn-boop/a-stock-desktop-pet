export function getTrayMenuTemplate(lang = 'zh') {
  const l = lang === 'zh' ? {
    show: '显示小土豆',
    hide: '隐藏窗口',
    market: '📈 查看行情',
    analysis: '🔬 个股分析',
    portfolio: '💰 持仓查询',
    pick: '🎯 智能选股',
    review: '📝 今日复盘',
    balance: '💹 查看余额',
    settings: '⚙️ 设置',
    checkUpdate: '🆙 检查更新',
    quit: '退出',
  } : {
    show: 'Show Pet',
    hide: 'Hide Window',
    market: '📈 Market',
    analysis: '🔬 Analysis',
    portfolio: '💰 Portfolio',
    pick: '🎯 Smart Pick',
    review: '📝 Review',
    balance: '💹 Balance',
    settings: '⚙️ Settings',
    checkUpdate: '🆙 Check Update',
    quit: 'Quit',
  };

  return [
    { label: l.show, action: 'show' },
    { label: l.hide, action: 'hide' },
    { type: 'separator' },
    { label: l.market, action: 'trade_analysis' },
    { label: l.analysis, action: 'trade_analysis' },
    { label: l.portfolio, action: 'trade_status' },
    { label: l.pick, action: 'trade_analysis' },
    { label: l.review, action: 'trade_analysis' },
    { label: l.balance, action: 'trade_status' },
    { type: 'separator' },
    { label: l.settings, action: 'settings' },
    { label: l.checkUpdate, action: 'check_update' },
    { type: 'separator' },
    { label: l.quit, action: 'quit' },
  ];
}