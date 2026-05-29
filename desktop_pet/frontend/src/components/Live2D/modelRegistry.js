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
    description: '支持融合变形、正片叠底色和屏幕色特效',
    path: '/models/Mao/Mao.model3.json',
    thumbnail: '/models/Mao/Mao.2048/texture_00.png',
    tags: ['特效', '融合变形', 'VTuber'],
    available: true,
    hasExpressions: true,
    expressionMap: {
      '开心': 'exp_01',
      '眨眼': 'exp_02',
      '害羞': 'exp_03',
      '惊讶': 'exp_04',
      '沉思': 'exp_05',
      '嘟嘴': 'exp_06',
      '委屈': 'exp_07',
      '难过': 'exp_08',
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
    placement: { xRatio: 0.73, yRatio: 1.0, anchorX: 0.5, anchorY: 1.0, scaleW: 0.5, scaleH: 0.6 },
  },
  Mark: {
    id: 'Mark',
    name: '马克君 (Mark)',
    nameZh: '马克君',
    description: '新手友好模型，支持物理模拟和眨眼',
    path: '/models/Mark/Mark.model3.json',
    thumbnail: '/models/Mark/Mark.2048/texture_00.png',
    tags: ['新手', '简单', '眨眼'],
    available: true,
    hasExpressions: false,
    expressionMap: {},
    emotionToExpression: {},
    placement: { xRatio: 0.73, yRatio: 1.0, anchorX: 0.5, anchorY: 1.0, scaleW: 0.5, scaleH: 0.6 },
  },
  Natori: {
    id: 'Natori',
    name: 'ナトリ (Natori)',
    nameZh: 'ナトリ',
    description: '表情丰富模型，含生气/脸红/微笑等6种情绪表达',
    path: '/models/Natori/Natori.model3.json',
    thumbnail: '/models/Natori/Natori.2048/texture_00.png',
    tags: ['表情', 'VTuber', '情绪'],
    available: true,
    hasExpressions: true,
    expressionMap: {
      '生气': 'Angry',
      '脸红': 'Blushing',
      '正常': 'Normal',
      '难过': 'Sad',
      '微笑': 'Smile',
      '惊讶': 'Surprised',
    },
    emotionToExpression: {
      'happy': '微笑',
      'excited': '微笑',
      'neutral': null,
      'bored': '正常',
      'angry': '生气',
      'sad': '难过',
      'surprised': '惊讶',
      'shy': '脸红',
      'thinking': '正常',
      'love': '脸红',
      'money': '微笑',
      'cry': '难过',
      'pout': '生气',
    },
    placement: { xRatio: 0.73, yRatio: 1.0, anchorX: 0.5, anchorY: 1.0, scaleW: 0.5, scaleH: 0.6 },
  },
  Rice: {
    id: 'Rice',
    name: '米 (Rice)',
    nameZh: '米',
    description: '简洁可爱模型，支持物理模拟',
    path: '/models/Rice/Rice.model3.json',
    thumbnail: '/models/Rice/Rice.2048/texture_00.png',
    tags: ['简洁', '可爱', '眨眼'],
    available: true,
    hasExpressions: false,
    expressionMap: {},
    emotionToExpression: {},
    placement: { xRatio: 0.73, yRatio: 1.0, anchorX: 0.5, anchorY: 1.0, scaleW: 0.5, scaleH: 0.6 },
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