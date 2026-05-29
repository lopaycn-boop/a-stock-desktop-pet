const MODEL_REGISTRY = {
  Haru: {
    id: 'Haru',
    name: '春 (Haru)',
    nameZh: '春',
    description: '默认助手模型，支持表情、语音、眨眼追踪',
    path: '/models/Haru/Haru.model3.json',
    thumbnail: '/models/Haru/Haru.2048/texture_00.png',
    tags: ['VTuber', '表情', '语音', '新手推荐'],
    available: true,
    hasExpressions: true,
    expressionMap: {
      '开心': 'F01',
      '眨眼': 'F02',
      '害羞': 'F03',
      '惊讶': 'F04',
      '沉思': 'F05',
      '嘟嘴': 'F06',
      '委屈': 'F07',
      '难过': 'F08',
    },
    emotionToExpression: {
      'happy': '开心',
      'excited': '开心',
      'neutral': null,
      'bored': '沉思',
      'angry': '嘟嘴',
      'sad': '难过',
      'surprised': '惊讶',
      'shy': '害羞',
      'thinking': '沉思',
      'love': '开心',
      'money': '眨眼',
      'cry': '委屈',
      'pout': '嘟嘴',
    },
    placement: { xRatio: 0.73, yRatio: 1.0, anchorX: 0.5, anchorY: 1.0, scaleW: 0.55, scaleH: 0.65 },
  },
  Hiyori: {
    id: 'Hiyori',
    name: '桃濑日和 (Hiyori)',
    nameZh: '日和',
    description: 'Cubism 3.0 标准模型，支持物理模拟和眨眼',
    path: '/models/Hiyori/Hiyori.model3.json',
    thumbnail: '/models/Hiyori/Hiyori.2048/texture_00.png',
    tags: ['VTuber', '物理模拟', '眨眼'],
    available: true,
    hasExpressions: false,
    expressionMap: {},
    emotionToExpression: {},
    placement: { xRatio: 0.73, yRatio: 1.0, anchorX: 0.5, anchorY: 1.0, scaleW: 0.5, scaleH: 0.6 },
  },
  Mao: {
    id: 'Mao',
    name: '虹色Mao (Nijiiro Mao)',
    nameZh: 'Mao',
    description: '支持融合变形、正片叠底色和屏幕色特效（需下载模型）',
    path: '/models/Mao/Mao.model3.json',
    thumbnail: '',
    tags: ['特效', '融合变形', 'VTuber'],
    available: false,
    hasExpressions: true,
    expressionMap: {},
    emotionToExpression: {},
    placement: { xRatio: 0.73, yRatio: 1.0, anchorX: 0.5, anchorY: 1.0, scaleW: 0.5, scaleH: 0.6 },
    installHint: '请从 Live2D 官网下载 Cubism SDK，将 Mao 模型文件夹放入 public/models/Mao/',
  },
  Mark: {
    id: 'Mark',
    name: '马克君 (Mark)',
    nameZh: '马克君',
    description: '新手友好模型，支持物理模拟和眨眼（需下载模型）',
    path: '/models/Mark/Mark.model3.json',
    thumbnail: '',
    tags: ['新手', '简单', '眨眼'],
    available: false,
    hasExpressions: false,
    expressionMap: {},
    emotionToExpression: {},
    placement: { xRatio: 0.73, yRatio: 1.0, anchorX: 0.5, anchorY: 1.0, scaleW: 0.5, scaleH: 0.6 },
    installHint: '请从 Live2D 官网下载 Cubism SDK，将 Mark 模型文件夹放入 public/models/Mark/',
  },
  Epsilon: {
    id: 'Epsilon',
    name: '伊普西隆 (Epsilon)',
    nameZh: '伊普西隆',
    description: '标准模型，含眼泪和生气标记等表情效果（需下载模型）',
    path: '/models/Epsilon/Epsilon.model3.json',
    thumbnail: '',
    tags: ['表情', '特效', 'VTuber'],
    available: false,
    hasExpressions: true,
    expressionMap: {},
    emotionToExpression: {},
    placement: { xRatio: 0.73, yRatio: 1.0, anchorX: 0.5, anchorY: 1.0, scaleW: 0.5, scaleH: 0.6 },
    installHint: '请从 Live2D 官网下载 Cubism SDK，将 Epsilon 模型文件夹放入 public/models/Epsilon/',
  },
  Shizuku: {
    id: 'Shizuku',
    name: '雫 (Shizuku)',
    nameZh: '雫',
    description: '"Shizuku Talk"主模型，手势细腻丰富（需下载模型）',
    path: '/models/Shizuku/Shizuku.model3.json',
    thumbnail: '',
    tags: ['手势', 'VTuber', '细腻'],
    available: false,
    hasExpressions: false,
    expressionMap: {},
    emotionToExpression: {},
    placement: { xRatio: 0.73, yRatio: 1.0, anchorX: 0.5, anchorY: 1.0, scaleW: 0.5, scaleH: 0.6 },
    installHint: '请从 Live2D 官网下载 Cubism SDK，将 Shizuku 模型文件夹放入 public/models/Shizuku/',
  },
};

const DEFAULT_MODEL_ID = 'Haru';

function getSavedModelId() {
  try {
    return localStorage.getItem('pet_model_id') || DEFAULT_MODEL_ID;
  } catch {
    return DEFAULT_MODEL_ID;
  }
}

function saveModelId(id) {
  try {
    localStorage.setItem('pet_model_id', id);
  } catch {}
}

function getModelConfig(modelId) {
  return MODEL_REGISTRY[modelId] || MODEL_REGISTRY[DEFAULT_MODEL_ID];
}

function getAvailableModels() {
  return Object.values(MODEL_REGISTRY);
}

export { MODEL_REGISTRY, DEFAULT_MODEL_ID, getSavedModelId, saveModelId, getModelConfig, getAvailableModels };