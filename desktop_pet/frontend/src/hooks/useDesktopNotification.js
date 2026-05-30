import { useCallback, useEffect, useRef } from 'react';

const NOTIFY_EVENTS = {
  trade_signal: (p) => {
    const actionEmoji = { BUY: '买入', SELL: '卖出', HOLD: '持有', WATCH: '观察' }[p.action] || p.action;
    return { title: `交易信号: ${actionEmoji}`, body: `${p.name || ''}(${p.symbol || ''}) ${p.action || ''}` };
  },
  trade_result: (p) => {
    if (p.ok) return { title: '交易提交成功', body: `${p.action || ''} ${p.name || p.symbol || ''} ¥${p.amount_cny || ''}` };
    return { title: '交易被拦截', body: p.reason || '风控不通过' };
  },
  risk_updated: (p) => ({ title: '风控参数更新', body: p.summary || '风控参数已更新' }),
  circuit_breaker: (p) => ({ title: '熔断触发', body: p.reason || '风控熔断' }),
  quota_exhausted: (p) => ({ title: 'API额度用尽', body: p.message || '请续费' }),
  backend_crash: () => ({ title: '后端异常', body: '后端进程已崩溃，正在自动重启' }),
  agent_crash: () => ({ title: 'Agent异常', body: 'Bytebot Agent已崩溃，正在自动重启' }),
  schedule_step: (p) => ({ title: '调度步骤', body: p.step || p.name || '调度步骤完成' }),
  trade_review: (p) => ({ title: '复盘完成', body: `${p.total_trades || 0}笔 胜率${p.win_rate || 0}%` }),
};

export function useDesktopNotification(sendPacket) {
  const askedRef = useRef(false);
  const permittedRef = useRef(false);

  useEffect(() => {
    if (askedRef.current) return;
    askedRef.current = true;
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission().then((perm) => {
        permittedRef.current = perm === 'granted';
      });
    } else if ('Notification' in window && Notification.permission === 'granted') {
      permittedRef.current = true;
    }
  }, []);

  const notify = useCallback((packet) => {
    if (!permittedRef.current) return null;
    const builder = NOTIFY_EVENTS[packet.type];
    if (!builder) return null;
    const { title, body } = builder(packet.payload || packet);
    try {
      const n = new Notification(title, {
        body,
        icon: '/logo.png',
        silent: false,
        tag: `potato-${packet.type}-${Date.now()}`,
      });
      n.onclick = () => {
        window.focus();
        n.close();
      };
      setTimeout(() => n.close(), 8000);
      return n;
    } catch (e) {
      return null;
    }
  }, []);

  return { notify };
}