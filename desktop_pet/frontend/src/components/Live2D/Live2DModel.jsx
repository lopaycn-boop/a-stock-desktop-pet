import { useLayoutEffect, useRef, forwardRef, useImperativeHandle, useState, useEffect } from 'react'
import { getModelConfig } from './modelRegistry'

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

const FALLBACK_EXPRESSIONS = {
  '开心': 'F01',
  '眨眼': 'F02',
  '害羞': 'F03',
  '惊讶': 'F04',
  '沉思': 'F05',
  '嘟嘴': 'F06',
  '委屈': 'F07',
  '难过': 'F08',
}

const FALLBACK_EMOTION_MAP = {
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
}

const Live2DDisplay = forwardRef(({ modelId }, ref) => {
  const pixiContainerRef = useRef(null)
  const appRef = useRef(null)
  const modelRef = useRef(null)
  const currentModelIdRef = useRef(null)
  const [loadError, setLoadError] = useState(null)
  const [modelInfo, setModelInfo] = useState(null)

  useImperativeHandle(ref, () => ({
    showExpression: (expression, active = true) => {
      if (!modelRef.current) return
      const config = modelInfo || getModelConfig(modelId)
      const exprMap = config.hasExpressions ? (Object.keys(config.expressionMap).length > 0 ? config.expressionMap : FALLBACK_EXPRESSIONS) : FALLBACK_EXPRESSIONS
      const emoMap = Object.keys(config.emotionToExpression).length > 0 ? config.emotionToExpression : FALLBACK_EMOTION_MAP
      const mapped = emoMap[expression]
      const exprName = mapped || expression
      const expressionId = exprMap[exprName]
      if (!expressionId) return
      if (active) {
        try {
          modelRef.current.expression(expressionId)
        } catch {
          try {
            modelRef.current.internalModel.coreModel.setParameterValueById(expressionId, 1)
          } catch (e) {
            console.warn(`expression ${expressionId} failed:`, e)
          }
        }
      } else {
        setTimeout(() => {
          if (modelRef.current) {
            try { modelRef.current.expression() } catch {}
          }
        }, 200)
      }
    },

    setTracking: (enabled) => {
      if (modelRef.current) {
        modelRef.current.autoInteract = enabled
        modelRef.current.internalModel.motionManager.settings.autoAddRandomMotion = enabled
        console.log(`模型跟踪功能已${enabled ? '开启' : '关闭'}~`)
      }
    },

    switchModel: (newModelId) => {
      return loadModel(newModelId)
    }
  }))

  const loadModel = async (targetModelId) => {
    const config = getModelConfig(targetModelId)
    if (!config) {
      console.error(`Model not found in registry: ${targetModelId}`)
      return
    }

    if (config.available === false) {
      const hint = config.installHint || `${config.nameZh || config.name} 模型文件未安装，请下载后放入 public/models/${targetModelId}/`
      console.warn(`Model not available: ${targetModelId}`)
      setLoadError(hint)
      return
    }

    if (modelRef.current) {
      try { modelRef.current.destroy() } catch {}
      modelRef.current = null
    }
    if (appRef.current) {
      try { appRef.current.stage.removeChildren() } catch {}
    }

    currentModelIdRef.current = targetModelId

    try {
      const PIXI = await import('pixi.js')
      const { Live2DModel } = await import('pixi-live2d-display/cubism4')

      window.PIXI = PIXI

      const basePath = window.location.protocol === 'file:'
        ? '.' + config.path
        : config.path
      const model = await Live2DModel.from(basePath)

      if (!appRef.current) return

      const app = appRef.current
      model.internalModel.motionManager.settings.autoAddRandomMotion = true
      model.autoInteract = true

      const place = config.placement
      const scale = Math.min(
        app.view.width / model.width * (place.scaleW || 0.55),
        app.view.height / model.height * (place.scaleH || 0.65)
      )
      model.scale.set(scale)
      model.x = app.view.width * (place.xRatio || 0.73)
      model.y = app.view.height * (place.yRatio || 1.0)
      model.anchor.set(place.anchorX || 0.5, place.anchorY || 1.0)

      app.stage.addChild(model)
      modelRef.current = model
      setModelInfo(config)
      setLoadError(null)

      try {
        const expressions = config.expressionMap && Object.keys(config.expressionMap).length > 0
          ? config.expressionMap
          : null
        const cdiUrl = config.path.replace('.model3.json', '.cdi3.json')
        const cdiResp = await fetch(cdiUrl)
        if (cdiResp.ok && !expressions) {
          const cdiData = await cdiResp.json()
          if (cdiData.Expressions && cdiData.Expressions.length > 0) {
            const autoMap = {}
            cdiData.Expressions.forEach((expr, i) => {
              autoMap[expr.Name] = expr.Id || expr.Name
            })
            config.expressionMap = autoMap
          }
        }
      } catch (e) {
        console.warn('Could not load CDI for expression auto-detect:', e)
      }

      console.log(`Model ${config.name} loaded successfully`)
    } catch (error) {
      console.error('Error loading model:', error)
      if (currentModelIdRef.current === targetModelId) {
        setLoadError(`${config.nameZh || config.name} 加载失败: ${error.message}`)
      }
    }
  }

  useLayoutEffect(() => {
    let isDestroyed = false
    let pixiApp = null

    async function initScene() {
      if (isDestroyed || !pixiContainerRef.current) return

      await LIVE2D_CORE_LOADED
      if (isDestroyed) return

      const PIXI = await import('pixi.js')
      if (isDestroyed) return

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

      await loadModel(modelId || 'Haru')
    }

    if (pixiContainerRef.current) {
      while (pixiContainerRef.current.firstChild) {
        pixiContainerRef.current.removeChild(pixiContainerRef.current.firstChild)
      }
    }

    initScene()

    return () => {
      isDestroyed = true
      if (modelRef.current) { modelRef.current.destroy(); modelRef.current = null }
      if (pixiApp) { pixiApp.destroy(true); pixiApp = null }
      appRef.current = null
    }
  }, [])

  useEffect(() => {
    if (modelId && modelId !== currentModelIdRef.current) {
      loadModel(modelId)
    }
  }, [modelId])

  return (
    <div ref={pixiContainerRef} className="live2d-container">
      {loadError && <div className="live2d-error" style={{
        position: 'absolute', bottom: 10, left: '50%', transform: 'translateX(-50%)',
        color: '#ff9800', fontSize: 12, textAlign: 'center', padding: '4px 8px',
        background: 'rgba(0,0,0,0.5)', borderRadius: 4, whiteSpace: 'nowrap',
      }}>{loadError}</div>}
    </div>
  )
})

Live2DDisplay.displayName = 'Live2DDisplay'
export default Live2DDisplay