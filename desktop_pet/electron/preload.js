const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('potatoAPI', {
  // System control — full computer access
  shellOpen: (url) => ipcRenderer.invoke('shell-open', url),
  shellOpenPath: (path) => ipcRenderer.invoke('shell-open-path', path),
  systemInfo: () => ipcRenderer.invoke('system-info'),
  executeCommand: (cmd, args) => ipcRenderer.invoke('execute-command', cmd, args),
  cleanupPC: (level) => ipcRenderer.invoke('cleanup-pc', level),
  setAutoStart: (enable) => ipcRenderer.invoke('set-auto-start', enable),
  getAutoStart: () => ipcRenderer.invoke('get-auto-start'),
  setAlwaysOnTop: (onTop) => ipcRenderer.invoke('set-always-on-top', onTop),
  setWindowSize: (w, h) => ipcRenderer.invoke('set-window-size', w, h),
  setWindowPosition: (x, y) => ipcRenderer.invoke('set-window-position', x, y),
  minimize: () => ipcRenderer.invoke('minimize'),
  hideWindow: () => ipcRenderer.invoke('hide-window'),
  showWindow: () => ipcRenderer.invoke('show-window'),
  setOpacity: (opacity) => ipcRenderer.invoke('set-opacity', opacity),
  powerStatus: () => ipcRenderer.invoke('power-status'),
  screenSources: () => ipcRenderer.invoke('screen-sources'),
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),

  // Event listeners from main process
  onTrayAction: (callback) => {
    ipcRenderer.on('tray-action', (event, action) => callback(action));
  },
  onSystemEvent: (callback) => {
    ipcRenderer.on('system-event', (event, data) => callback(data));
  },
});