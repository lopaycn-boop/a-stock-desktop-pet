import { useState } from 'react';
import { getAvailableModels, getSavedModelId, saveModelId, getModelConfig } from './Live2D/modelRegistry';

export default function ModelPicker({ currentModel, onSwitch }) {
  const [open, setOpen] = useState(false)
  const models = getAvailableModels()
  const active = getModelConfig(currentModel)

  return (
    <div className="model-picker">
      <button
        className="model-picker-trigger"
        onClick={() => setOpen(!open)}
        title="切换桌宠模型"
      >
        <span className="model-picker-avatar">
          {active ? (active.nameZh || active.name).charAt(0) : '?'}
        </span>
        <span className="model-picker-name">{active ? (active.nameZh || active.name) : '加载中'}</span>
        <span className="model-picker-arrow">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <>
          <div className="model-picker-overlay" onClick={() => setOpen(false)} />
          <div className="model-picker-dropdown">
            <div className="model-picker-header">🎭 选择桌宠模型</div>
            {models.map(m => (
              <button
                key={m.id}
                className={`model-picker-item ${currentModel === m.id ? 'active' : ''}`}
                onClick={() => {
                  onSwitch(m.id)
                  saveModelId(m.id)
                  setOpen(false)
                }}
              >
                <span className="model-picker-item-avatar">
                  {(m.nameZh || m.name).charAt(0)}
                </span>
                <span className="model-picker-item-info">
                  <span className="model-picker-item-name">{m.nameZh || m.name}</span>
                  <span className="model-picker-item-desc">{m.description}</span>
                </span>
                {currentModel === m.id && <span className="model-picker-check">✓</span>}
              </button>
            ))}
            <div className="model-picker-footer">
              更多模型从 Live2D 官网下载后放入 public/models/ 目录
            </div>
          </div>
        </>
      )}
    </div>
  )
}