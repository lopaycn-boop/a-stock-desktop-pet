import { getModelConfig } from '../components/Live2D/modelRegistry';

const TRADE_EMOJIS = {
  '🟢': 'money',
  '🔴': 'sad',
  '🟡': 'neutral',
  '👀': 'surprised',
  '📊': 'thinking',
  '🔬': 'thinking',
  '✅': 'happy',
  '🛑': 'angry',
  '❌': 'sad',
  '⚠️': 'surprised',
  '🛡️': 'neutral',
  '💰': 'money',
  '💹': 'happy',
  '📈': 'money',
  '📉': 'sad',
  '🔥': 'excited',
  '📅': 'neutral',
};

const STATE_EMOTIONS = {
  thinking: 'thinking',
  speaking: 'neutral',
  idle: 'neutral',
  recording: 'surprised',
};

export function inferEmotionFromMessage(msg) {
  if (!msg || !msg.content || typeof msg.content !== 'string') return null;

  for (const [emoji, emotion] of Object.entries(TRADE_EMOJIS)) {
    if (msg.content.startsWith(emoji)) return emotion;
  }

  if (msg.type === 'system' && msg.content.includes('交易提交成功')) return 'happy';
  if (msg.type === 'system' && msg.content.includes('交易被拦截')) return 'angry';
  if (msg.type === 'system' && msg.content.includes('熔断')) return 'sad';
  if (msg.type === 'system' && msg.content.includes('额度已用完')) return 'sad';
  if (msg.type === 'system' && msg.content.includes('密钥已就绪')) return 'happy';
  if (msg.type === 'system' && msg.content.includes('连接已恢复')) return 'happy';

  return null;
}

export function emotionToExpression(emotion, modelId) {
  const config = getModelConfig(modelId);
  if (!config || !config.emotionToExpression) return null;
  const zhName = config.emotionToExpression[emotion];
  if (!zhName) return null;
  return config.expressionMap?.[zhName] || zhName;
}

export function stateToExpression(neuroState, modelId) {
  const emotion = STATE_EMOTIONS[neuroState];
  if (!emotion) return null;
  return emotionToExpression(emotion, modelId);
}