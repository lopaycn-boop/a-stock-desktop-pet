import React, { useState, useEffect } from 'react';

const ONBOARDING_KEY = 'potato_onboarding_done';

const STEPS = [
  { icon: '🔑', title: '粘贴API密钥', desc: '直接在聊天框粘贴你的DeepSeek/SiliconFlow/Liner等API Key，小土豆会自动识别并加密保存', action: 'paste' },
  { icon: '💬', title: '语音或文字对话', desc: '点击胸口麦克风录音，或直接打字。说"小土豆"也可以唤醒', action: 'chat' },
  { icon: '📈', title: 'AI自主操盘', desc: '设定投入金额后，小土豆自动执行7阶段交易闭环：盘前→选股→分析→下单→盘中→复盘→收仓', action: 'trade' },
  { icon: '🛡️', title: '风控保护', desc: '止损5%/止盈10%/最多3只持仓/稳健模式，全部AI自主管理。在设置面板可以调整参数', action: 'settings' },
  { icon: '⚙️', title: '个性化设置', desc: '右上角设置可以调整音量、透明度、语音唤醒、桌面通知等', action: 'done' },
];

export default function OnboardingWizard({ onComplete, sendPacket }) {
  const [step, setStep] = useState(0);
  const [skipped, setSkipped] = useState(false);

  useEffect(() => {
    const done = localStorage.getItem(ONBOARDING_KEY);
    if (done) { setSkipped(true); onComplete?.(); }
  }, [onComplete]);

  if (skipped) return null;

  const current = STEPS[step];

  const handleNext = () => {
    if (step < STEPS.length - 1) {
      setStep(step + 1);
    } else {
      localStorage.setItem(ONBOARDING_KEY, '1');
      onComplete?.();
    }
  };

  const handleSkip = () => {
    localStorage.setItem(ONBOARDING_KEY, '1');
    onComplete?.();
  };

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 99999, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: '#1a1a2e', borderRadius: 20, width: 380, padding: 0, boxShadow: '0 16px 48px rgba(0,0,0,0.6)', border: '1px solid rgba(105,240,174,0.2)' }}>
        <div style={{ padding: '28px 28px 0', textAlign: 'center' }}>
          <div style={{ fontSize: 48, marginBottom: 8 }}>{current.icon}</div>
          <h2 style={{ color: '#69f0ae', margin: '0 0 8px', fontSize: 18 }}>{current.title}</h2>
          <p style={{ color: '#bbb', fontSize: 14, lineHeight: 1.5, margin: '0 0 20px' }}>{current.desc}</p>
        </div>
        <div style={{ padding: '0 28px 24px' }}>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginBottom: 16 }}>
            {STEPS.map((_, i) => (
              <div key={i} style={{ width: 8, height: 8, borderRadius: 4, background: i === step ? '#69f0ae' : i < step ? '#4a7c3f' : '#333' }} />
            ))}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <button onClick={handleSkip} style={{ background: 'none', border: '1px solid #444', borderRadius: 10, padding: '8px 20px', color: '#888', cursor: 'pointer', fontSize: 13 }}>
              跳过
            </button>
            <button onClick={handleNext} style={{ background: '#69f0ae', border: 'none', borderRadius: 10, padding: '8px 24px', color: '#1a1a2e', cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>
              {step < STEPS.length - 1 ? '下一步' : '开始使用'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}