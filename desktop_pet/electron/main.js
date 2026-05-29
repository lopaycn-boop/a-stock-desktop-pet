const { app, BrowserWindow, Tray, Menu, shell, systemPreferences, powerMonitor, screen, globalShortcut, ipcMain, nativeImage } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
const fs = require('fs');
const net = require('net');

let mainWindow = null;
let tray = null;
let backendProc = null;
let isQuitting = false;

const BACKEND_PORT = 8000;
const FRONTEND_PORT = 5173;
const APP_NAME = '小土豆 AI操盘桌宠';

// ── All permissions pre-granted ──
async function grantAllPermissions() {
  // Windows: systemPreferences doesn't exist the same way, but we handle it gracefully
  try {
    if (process.platform === 'darwin') {
      // macOS permissions
      const perms = [
        'camera', 'microphone', 'screen', 'accessibility',
        'calendar', 'reminders', 'notifications', 'location',
        'music-library', 'photos', 'bluetooth'
      ];
      for (const perm of perms) {
        try { await systemPreferences.askForMediaAccess(perm); } catch(e) { /* ignore */ }
      }
    }
  } catch(e) { /* ignore on Windows */ }
  
  // Windows: request MIC/Camera access via registry (auto-grant on install)
  try {
    if (process.platform === 'win32') {
      // Set Windows registry keys for microphone and camera access
      const regCmds = [
        // Allow apps to access microphone
        'reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\microphone" /v Value /t Reg_Expand_Sz /d Allow /f',
        // Allow apps to access camera
        'reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\camera" /v Value /t Reg_Expand_Sz /d Allow /f',
      ];
      for (const cmd of regCmds) {
        try { spawn('reg', cmd.split(' ').slice(1), { stdio: 'ignore' }); } catch(e) {}
      }
    }
  } catch(e) {}
}

// ── Check & wait for backend ──
function waitForBackend(port, maxRetries = 30) {
  return new Promise((resolve) => {
    let tries = 0;
    const check = () => {
      const req = http.get(`http://127.0.0.1:${port}/health`, (res) => {
        if (res.statusCode === 200) {
          resolve(true);
        } else {
          tries++;
          if (tries < maxRetries) setTimeout(check, 1000);
          else resolve(false);
        }
      });
      req.on('error', () => {
        tries++;
        if (tries < maxRetries) setTimeout(check, 1000);
        else resolve(false);
      });
      req.end();
    };
    check();
  });
}

// ── Find Python ──
function findPython() {
  const candidates = [
    process.env.PYTHON_PATH,
    path.join(process.resourcesPath || '', 'python', 'python.exe'),
    'python',
    'python3',
    'C:\\Python312\\python.exe',
    'C:\\Python311\\python.exe',
    'C:\\Python310\\python.exe',
  ].filter(Boolean);

  for (const p of candidates) {
    try {
      const result = spawn(p, ['--version'], { stdio: 'pipe' });
      if (result.status === 0) return p;
    } catch(e) {}
  }
  return 'python';
}

// ── Start backend ──
function startBackend() {
  // Dev mode: if backend is already running on BACKEND_PORT, skip spawning
  const http = require('http');
  const req = http.get(`http://127.0.0.1:${BACKEND_PORT}/health`, (res) => {
    res.resume();
    if (res.statusCode === 200) {
      console.log(`[electron] Backend already running on port ${BACKEND_PORT}, skipping spawn`);
      return;
    }
    _spawnBackend();
  });
  req.on('error', () => { _spawnBackend(); });
  req.end();
}

// ── Start Bytebot Agent ──
let agentProc = null;
function startBytebotAgent() {
  const agentPort = process.env.BYTEBOT_AGENT_PORT || '9991';
  // Check if already running
  const req = http.get(`http://127.0.0.1:${agentPort}/health`, (res) => {
    res.resume();
    if (res.statusCode === 200) {
      console.log(`[electron] Bytebot Agent already running on port ${agentPort}`);
      return;
    }
    _spawnAgent();
  });
  req.on('error', () => { _spawnAgent(); });
  req.end();
}

function _spawnAgent() {
  const python = findPython();
  const agentScript = path.join(__dirname, '..', 'backend', 'bytebot_agent.py');
  if (!fs.existsSync(agentScript)) {
    console.log('[electron] bytebot_agent.py not found, skipping agent start');
    return;
  }
  const agentPort = process.env.BYTEBOT_AGENT_PORT || '9991';
  const env = { ...process.env, BYTEBOT_AGENT_PORT: agentPort };
  agentProc = spawn(python, [agentScript], {
    cwd: path.dirname(agentScript),
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: true,
  });
  agentProc.stdout.on('data', (data) => {
    console.log(`[agent] ${data.toString().trim()}`);
  });
  agentProc.stderr.on('data', (data) => {
    console.error(`[agent] ${data.toString().trim()}`);
  });
  agentProc.on('close', (code) => {
    if (!isQuitting) {
      console.log(`Bytebot Agent exited with code ${code}, restarting in 5s...`);
      setTimeout(() => _spawnAgent(), 5000);
    }
  });
  console.log(`[electron] Bytebot Agent started on port ${agentPort}`);
}

function _spawnBackend() {
  const python = findPython();
  const backendDir = path.join(process.resourcesPath || path.join(__dirname, '..'), 'backend');
  const mainPy = path.join(backendDir, 'main.py');

  if (!fs.existsSync(mainPy)) {
    console.error(`Backend not found at ${mainPy}, trying project root backend`);
    const altMainPy = path.join(__dirname, '..', 'backend', 'main.py');
    if (!fs.existsSync(altMainPy)) {
      console.error(`Backend not found at ${altMainPy} either, relying on existing backend`);
      return;
    }
  }

  const env = { ...process.env };
  env.PORT = String(BACKEND_PORT);
  env.PYTHONPATH = [
    path.join(__dirname, '..', '..'),
    path.join(__dirname, '..', 'backend'),
  ].join(path.delimiter) + (env.PYTHONPATH ? path.delimiter + env.PYTHONPATH : '');

  const mainPyPath = fs.existsSync(path.join(__dirname, '..', 'backend', 'main.py'))
    ? path.join(__dirname, '..', 'backend', 'main.py')
    : mainPy;
  const cwd = path.dirname(mainPyPath);

  backendProc = spawn(python, [mainPyPath], {
    cwd,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: true,
  });

  backendProc.stdout.on('data', (data) => {
    console.log(`[backend] ${data.toString().trim()}`);
  });
  backendProc.stderr.on('data', (data) => {
    console.error(`[backend] ${data.toString().trim()}`);
  });
  backendProc.on('close', (code) => {
    if (!isQuitting) {
      console.log(`Backend exited with code ${code}, restarting in 3s...`);
      setTimeout(() => _spawnBackend(), 3000);
    }
  });
}

// ── Create main window ──
function createWindow() {
  const { width: screenW, height: screenH } = screen.getPrimaryDisplay().workAreaSize;

  mainWindow = new BrowserWindow({
    width: 420,
    height: 700,
    x: screenW - 440,
    y: screenH - 720,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: false,
    resizable: true,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,
      webSecurity: false,
      allowRunningInsecureContent: true,
      autoplayPolicy: 'no-user-gesture-required',
    },
  });

  // Make window draggable from .app region, pass-through elsewhere
  mainWindow.webContents.on('did-finish-load', () => {
    mainWindow.webContents.executeJavaScript(`
      document.querySelectorAll('.app').forEach(el => {
        el.style['-webkit-app-region'] = 'drag';
      });
      document.querySelectorAll('button, input, textarea, select, a, .no-drag').forEach(el => {
        el.style['-webkit-app-region'] = 'no-drag';
      });
    `);
  });

  // Load frontend
  const frontendUrl = `http://127.0.0.1:${FRONTEND_PORT}`;
  const distPath = path.join(__dirname, '..', 'frontend', 'dist', 'index.html');

  if (fs.existsSync(distPath)) {
    mainWindow.loadFile(distPath);
  } else {
    mainWindow.loadURL(frontendUrl);
  }

  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });

  // Register global shortcuts
  globalShortcut.register('CommandOrControl+Shift+P', () => {
    if (mainWindow.isVisible()) {
      mainWindow.hide();
    } else {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

// ── System tray ──
function createTray() {
  // Use a simple 16x16 dark circle as tray icon
  const icon = nativeImage.createFromBuffer(
    Buffer.from('iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABGdBTUEAALGPC/xhBQAAAAlwSFlzAAAAdAAAAHQBMYXfQAAAAZJREFUOE+tk71KA0EQhn2khRZCIWgRellpYy2CggVoa2NlZ2NnZ2FjYSEKCwsLCOxsbGz8H8jtJO8mN+ESuZ3O3Oy8d7ubDJ/0zJw7M+dmCv8DfgF9YMz3Yc6AK3CIGfAEHIHHcI/gCzghB2yBz3DvYIBbcAZuwQVwmhtwC27BHXCOG3APnsM9uAcP4B68hQdwB67BbbgOl+AO3IUPcA2eQdwOS7q7B7ES7uwC7OgB09kOd3WC2HCD4Dk9jOM7gha4A+ekPQSHOIEPcIIbcI4bcB7uwx3YB3fDE3gGV+AS3IYbcAd2wV3YB3fDE3gHV+AS3IYbcAd2wV3YB3fDE3gHd+AS3IY7cAcOwBP2wB04Ag/gFDyCG3AH7sMdOAK/4RU8ghuwB07BA3gGV+AS3IYbcAd2wV3YB3fDE3gHd+AS3IY7cAcOwBP2wB04Ag/gFDyCG7AH7sMdOIK/4BU8ghuwB07BA3gHd+AS3IYbcAd2wV3YB3fDE3gHd+AS3IY7cAcOwBP2wB04Ag/gFDyCG7AH7sMdOIK/4BU8Ae2EO3AJDsAJ+wxOwx1Yg1dwAS7BXbgFV+AUHMEduAT34Q58gxvxD0U8ASrkEQI7yl2pAAAAAElFTkSuQmCC', 'base64')
  );

  tray = new Tray(icon);
  const contextMenu = Menu.buildFromTemplate([
    { label: '显示小土豆', click: () => { mainWindow?.show(); mainWindow?.focus(); } },
    { label: '分析选股', click: () => { mainWindow?.show(); mainWindow?.webContents.send('tray-action', 'trade_analysis'); } },
    { label: '操盘状态', click: () => { mainWindow?.show(); mainWindow?.webContents.send('tray-action', 'trade_status'); } },
    { label: '清理电脑', click: () => { mainWindow?.show(); mainWindow?.webContents.send('tray-action', 'cleanup_pc'); } },
    { type: 'separator' },
    { label: '重启后端', click: () => { if (backendProc) backendProc.kill(); startBackend(); } },
    { label: '开发者工具', click: () => { mainWindow?.webContents?.openDevTools(); } },
    { type: 'separator' },
    { label: '退出', click: () => { isQuitting = true; app.quit(); } },
  ]);
  tray.setToolTip(APP_NAME);
  tray.setContextMenu(contextMenu);
  tray.on('click', () => {
    mainWindow?.isVisible() ? mainWindow.hide() : mainWindow?.show();
  });
}

// ── Auto-start on boot ──
function setAutoStart(enable = true) {
  const appFolder = path.dirname(process.execPath);
  const exePath = path.join(appFolder, APP_NAME + '.exe');
  const regKey = 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run';

  if (enable) {
    try {
      spawn('reg', ['add', regKey, '/v', 'PotatoDesktopPet', '/t', 'REG_SZ', '/d', `"${exePath}"`, '/f'], { stdio: 'ignore' });
    } catch(e) {}
  } else {
    try {
      spawn('reg', ['delete', regKey, '/v', 'PotatoDesktopPet', '/f'], { stdio: 'ignore' });
    } catch(e) {}
  }
}

// ── IPC handlers for full system control ──
function setupIPC() {
  // System control — the pet can do EVERYTHING on the computer
  ipcMain.handle('shell-open', async (event, url) => {
    shell.openExternal(url);
    return { ok: true };
  });

  ipcMain.handle('shell-open-path', async (event, filePath) => {
    shell.openPath(filePath);
    return { ok: true };
  });

  ipcMain.handle('system-info', async () => {
    return {
      platform: process.platform,
      arch: process.arch,
      cpuCount: require('os').cpus().length,
      totalMemory: Math.round(require('os').totalmem() / 1024 / 1024 / 1024) + 'GB',
      freeMemory: Math.round(require('os').freemem() / 1024 / 1024 / 1024) + 'GB',
      uptime: Math.round(require('os').uptime() / 3600) + 'h',
    };
  });

  ipcMain.handle('execute-command', async (event, cmd, args = []) => {
    return new Promise((resolve) => {
      const proc = spawn(cmd, args, { shell: true, stdio: 'pipe' });
      let stdout = '', stderr = '';
      proc.stdout.on('data', (d) => stdout += d.toString());
      proc.stderr.on('data', (d) => stderr += d.toString());
      proc.on('close', (code) => {
        resolve({ ok: code === 0, code, stdout, stderr });
      });
      proc.on('error', (err) => {
        resolve({ ok: false, error: err.message });
      });
    });
  });

  ipcMain.handle('cleanup-pc', async (event, level = 'quick') => {
    // Delegated to the backend cleanup_pc handler via WebSocket
    return { ok: true, level, message: '清理指令已发送到后端' };
  });

  ipcMain.handle('set-auto-start', async (event, enable) => {
    setAutoStart(enable);
    return { ok: true };
  });

  ipcMain.handle('get-auto-start', async () => {
    return new Promise((resolve) => {
      const proc = spawn('reg', ['query', 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run', '/v', 'PotatoDesktopPet'], { shell: true, stdio: 'pipe' });
      let out = '';
      proc.stdout.on('data', (d) => out += d.toString());
      proc.on('close', () => resolve({ enabled: out.includes('PotatoDesktopPet') }));
      proc.on('error', () => resolve({ enabled: false }));
    });
  });

  ipcMain.handle('set-always-on-top', async (event, onTop) => {
    mainWindow?.setAlwaysOnTop(onTop);
    return { ok: true };
  });

  ipcMain.handle('set-window-size', async (event, w, h) => {
    mainWindow?.setSize(w, h);
    return { ok: true };
  });

  ipcMain.handle('set-window-position', async (event, x, y) => {
    mainWindow?.setPosition(x, y);
    return { ok: true };
  });

  ipcMain.handle('minimize', async () => {
    mainWindow?.minimize();
    return { ok: true };
  });

  ipcMain.handle('hide-window', async () => {
    mainWindow?.hide();
    return { ok: true };
  });

  ipcMain.handle('show-window', async () => {
    mainWindow?.show();
    mainWindow?.focus();
    return { ok: true };
  });

  ipcMain.handle('set-opacity', async (event, opacity) => {
    mainWindow?.setOpacity(Math.max(0.1, Math.min(1, opacity)));
    return { ok: true };
  });

  ipcMain.handle('power-status', async () => {
    return powerMonitor.getSystemPowerState
      ? { supported: true }
      : { supported: false };
  });

  ipcMain.handle('screen-sources', async () => {
    try {
      const sources = await require('electron').desktopCapturer.getSources({ types: ['screen'] });
      return { ok: true, sources: sources.map(s => ({ id: s.id, name: s.name })) };
    } catch(e) {
      return { ok: false, error: e.message };
    }
  });
}

// ── App lifecycle ──
app.whenReady().then(async () => {
  // Grant ALL permissions — no popup interruptions
  await grantAllPermissions();

  // Start backend first
  startBackend();

  // Wait for backend to be ready
  const backendReady = await waitForBackend(BACKEND_PORT, 30);
  if (!backendReady) {
    console.error('Backend failed to start within 30s');
  }

  // Start Bytebot Agent
  startBytebotAgent();

  // Create UI
  createWindow();
  createTray();
  setupIPC();

  // Set auto-start
  setAutoStart(true);

  // Power monitor events
  powerMonitor.on('suspend', () => {
    mainWindow?.webContents.send('system-event', { type: 'suspend' });
  });
  powerMonitor.on('resume', () => {
    mainWindow?.webContents.send('system-event', { type: 'resume' });
  });
  powerMonitor.on('on-ac', () => {
    mainWindow?.webContents.send('system-event', { type: 'on-ac' });
  });
  powerMonitor.on('on-battery', () => {
    mainWindow?.webContents.send('system-event', { type: 'on-battery' });
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    } else {
      mainWindow?.show();
    }
  });
});

app.on('window-all-closed', () => {
  // Don't quit — keep running in tray
});

app.on('before-quit', () => {
  isQuitting = true;
  if (backendProc) {
    backendProc.kill('SIGTERM');
  }
  if (agentProc) {
    agentProc.kill('SIGTERM');
  }
  globalShortcut.unregisterAll();
});