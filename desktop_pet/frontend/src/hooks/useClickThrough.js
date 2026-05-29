// 不再使用 setIgnoreMouseEvents
// 窗口拖拽由 -webkit-app-region: drag 处理
// 按钮/输入框由 -webkit-app-region: no-drag + pointer-events: auto 处理
export function useClickThrough() {
  // no-op
}