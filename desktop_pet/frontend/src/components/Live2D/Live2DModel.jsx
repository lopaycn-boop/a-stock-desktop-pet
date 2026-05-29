import { useLayoutEffect, useRef, forwardRef, useImperativeHandle, useState } from 'react'

const LIVE2D_CORE_LOADED = new Promise((resolve) => {
  const existing = document.getElementById('live2d-core-sdk')
  if (existing) { resolve(); return }
  const script = document.createElement('script')
  script.id = 'live2d-core-sdk'
  script.src = './libs/live2dcubismcore.min.js'
  script.onload = resolve
  script.onerror = () => { console.warn('Live2D core SDK failed to load'); resolve() }
  document.head.appendChild(script)
})

const EXPRESSIONS = {
    '开心': 'F01',
    '眨眼': 'F02',
    '害羞': 'F03',
    '惊讶': 'F04',
    '沉思': 'F05',
    '嘟嘴': 'F06',
    '委屈': 'F07',
    '难过': 'F08',
  }

  const EMOTION_MAP = {
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
  };

const Live2DDisplay = forwardRef((props, ref) => {
  const pixiContainerRef = useRef(null)
  const appRef = useRef(null)
  const modelRef = useRef(null)
  const [loadError, setLoadError] = useState(null)

  useImperativeHandle(ref, () => ({
    showExpression: (expression, active = true) => {
      if (modelRef.current) {
        const mapped = EMOTION_MAP[expression];
        const exprName = mapped || expression;
        const expressionId = EXPRESSIONS[exprName];
        if (expressionId && active) {
          try {
            modelRef.current.expression(expressionId);
          } catch {
            try {
              modelRef.current.internalModel.coreModel.setParameterValueById(expressionId, 1);
            } catch (e) {
              console.warn(`expression ${expressionId} failed:`, e);
            }
          }
        } else if (!active && expressionId) {
          setTimeout(() => {
            if (modelRef.current) {
              try { modelRef.current.expression(); } catch {}
            }
          }, 200);
        }
      }
    },

    // 新增：设置跟踪功能
    setTracking: (enabled) => {
      if (modelRef.current) {
        modelRef.current.autoInteract = enabled;
        modelRef.current.internalModel.motionManager.settings.autoAddRandomMotion = enabled;
        console.log(`模型跟踪功能已${enabled ? '开启' : '关闭'}~`);
      }
    }
  }))

  useLayoutEffect(() => {
    let isDestroyed = false
    let pixiApp = null
    let live2dModel = null

    async function initScene() {
      if (isDestroyed || !pixiContainerRef.current) return

      await LIVE2D_CORE_LOADED

      const PIXI = await import('pixi.js')
      const { Live2DModel } = await import('pixi-live2d-display/cubism4')

      if (isDestroyed) return

      window.PIXI = PIXI

      const app = new PIXI.Application({
        width: window.innerWidth,
        height: window.innerHeight,
        backgroundAlpha: 0,
        resizeTo: window,
        antialias: true,
      })
      pixiApp = app
      appRef.current = app
      pixiContainerRef.current.appendChild(app.view)

      try {
        const basePath = window.location.protocol === 'file:'
          ? './models/Haru/Haru.model3.json'
          : '/models/Haru/Haru.model3.json'
        const model = await Live2DModel.from(basePath)

        if (isDestroyed || !appRef.current) return

        console.log('Model loaded:', model)
        live2dModel = model
        modelRef.current = model

        model.internalModel.motionManager.settings.autoAddRandomMotion = true
        model.autoInteract = true

        const scale = Math.min(
          app.view.width / model.width * 0.55,
          app.view.height / model.height * 0.65
        )
        model.scale.set(scale)
        model.x = app.view.width * 0.73
        model.y = app.view.height - 10
        model.anchor.set(0.5, 1.0)
        app.stage.addChild(model)
      } catch (error) {
        console.error('Error loading model:', error)
        setLoadError(error.message)
      }
    }

    if (pixiContainerRef.current) {
      while (pixiContainerRef.current.firstChild) {
        pixiContainerRef.current.removeChild(pixiContainerRef.current.firstChild)
      }
    }

    initScene()

    return () => {
      isDestroyed = true
      if (live2dModel) { live2dModel.destroy(); live2dModel = null }
      if (pixiApp) { pixiApp.destroy(true); pixiApp = null }
      modelRef.current = null
      appRef.current = null
    }
  }, [])

  return (
    <div ref={pixiContainerRef} className="live2d-container">
      {loadError && <div className="live2d-error" style={{
        position: 'absolute', bottom: 10, left: '50%', transform: 'translateX(-50%)',
        color: '#ff9800', fontSize: 12, textAlign: 'center', padding: '4px 8px',
        background: 'rgba(0,0,0,0.5)', borderRadius: 4,
      }}>{loadError}</div>}
    </div>
  )
})
// 添加这行给组件命名
Live2DDisplay.displayName = 'Live2DDisplay'
export default Live2DDisplay 