const { app, BrowserWindow, screen } = require('electron');
const path = require('path');
const { spawn, execSync } = require('child_process');
const fs = require('fs');

app.commandLine.appendSwitch('disable-features', 'OutOfBlinkCors');
app.commandLine.appendSwitch('enable-webgl');
app.commandLine.appendSwitch('ignore-gpu-blocklist');
app.commandLine.appendSwitch('enable-features', 'HardwareMediaKeyHandling,MediaSessionService');
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.commandLine.appendSwitch('enable-media-stream');

let backendProcess = null;
let backendShutdown = false;
let backendStarted = false;
let backendReady = false;

const LOG_FILE = path.join(app.getPath('userData'), 'backend.log');
const logger = {
  info: (msg) => {
    const line = `[${new Date().toISOString()}] ℹ️  ${msg}`;
    console.log(line);
    fs.appendFileSync(LOG_FILE, line + '\n', 'utf-8');
  },
  success: (msg) => {
    const line = `[${new Date().toISOString()}] ✅ ${msg}`;
    console.log(line);
    fs.appendFileSync(LOG_FILE, line + '\n', 'utf-8');
  },
  warn: (msg) => {
    const line = `[${new Date().toISOString()}] ⚠️  ${msg}`;
    console.warn(line);
    fs.appendFileSync(LOG_FILE, line + '\n', 'utf-8');
  },
  error: (msg) => {
    const line = `[${new Date().toISOString()}] ❌ ${msg}`;
    console.error(line);
    fs.appendFileSync(LOG_FILE, line + '\n', 'utf-8');
  },
};

logger.info('═════════════════════════════════════════');
logger.info('小土豆桌宠启动');
logger.info(`应用版本: 1.0.0 | 平台: ${process.platform} | Electron: ${process.versions.electron}`);

function getResourcePath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath);
  }
  return path.join(__dirname, '..', '..');
}

function findPython() {
  const resourcesPath = getResourcePath();
  const embeddedPython = path.join(resourcesPath, 'python', 'python', 'python.exe');
  logger.info(`🔍 搜索 Python...`);
  logger.info(`   embedded: ${embeddedPython}`);
  if (fs.existsSync(embeddedPython)) {
    logger.success(`找到嵌入式 Python: ${embeddedPython}`);
    return embeddedPython;
  }
  const candidates = process.platform === 'win32'
    ? ['python', 'python3', 'py', 'C:\\Python311\\python.exe', 'C:\\Python312\\python.exe']
    : ['python3', 'python'];
  for (const cmd of candidates) {
    try {
      execSync(`${cmd} --version`, { stdio: 'pipe', timeout: 5000 });
      logger.success(`找到系统 Python: ${cmd}`);
      return cmd;
    } catch (_) { logger.warn(`   ${cmd} 不可用`); }
  }
  logger.error('❌ 未找到 Python！');
  return null;
}

function findBackendDir() {
  const resourcesPath = getResourcePath();
  const possible = [
    path.join(resourcesPath, 'backend'),
    path.join(__dirname, '..', 'backend'),
    path.join(__dirname, 'backend'),
  ];
  logger.info(`🔍 搜索后端目录...`);
  for (const dir of possible) {
    logger.info(`   检查: ${dir}`);
    if (fs.existsSync(path.join(dir, 'main.py'))) {
      logger.success(`找到后端: ${dir}`);
      return dir;
    }
  }
  logger.error('❌ 未找到后端目录！');
  return null;
}

function checkBackendHealth(timeout = 3000) {
  return new Promise((resolve) => {
    let healthChecks = 0;
    const maxChecks = Math.ceil(timeout / 500);
    const check = () => {
      healthChecks++;
      if (healthChecks > maxChecks) { logger.error(`后端健康检查超时 (${timeout}ms)`); resolve(false); return; }
      if (!backendProcess || backendProcess.killed) { logger.error('后端进程已退出'); resolve(false); return; }
      const http = require('http');
      const req = http.get('http://localhost:8000/health', { timeout: 500 }, (res) => {
        if (res.statusCode === 200) { logger.success('后端健康检查通过'); resolve(true); }
        else { logger.warn(`后端返回状态码 ${res.statusCode}，重试...`); setTimeout(check, 500); }
      });
      req.on('error', () => { if (healthChecks < maxChecks) { setTimeout(check, 500); } else { logger.error('后端健康检查最终失败'); resolve(false); } });
    };
    check();
  });
}

function findPotatoDir() {
  const resourcesPath = getResourcePath();
  const possible = [
    path.join(resourcesPath, 'potato'),
    path.join(__dirname, '..', '..', 'potato'),
    path.join(__dirname, 'potato'),
  ];
  logger.info('🔍 搜索 potato 核心包...');
  for (const dir of possible) {
    logger.info(`   检查: ${dir}`);
    if (fs.existsSync(path.join(dir, '__init__.py'))) {
      logger.success(`找到 potato 包: ${dir}`);
      return dir;
    }
  }
  logger.warn('⚠️  未找到 potato 包目录，后端可能无法启动');
  return null;
}

function findConfigDir() {
  const resourcesPath = getResourcePath();
  const possible = [
    path.join(resourcesPath, 'config'),
    path.join(__dirname, '..', '..', 'config'),
  ];
  for (const dir of possible) {
    if (fs.existsSync(dir)) { logger.success(`找到 config: ${dir}`); return dir; }
  }
  return null;
}

function startBackend() {
  logger.info('🚀 启动后端...\n');
  const py = findPython();
  if (!py) { logger.error('Python 不可用'); return; }
  const backendDir = findBackendDir();
  if (!backendDir) { logger.error('后端目录不可用'); return; }
  const env = { ...process.env };
  env.PORT = '8000';
  env.POTATO_SECRETS_ENV_FALLBACK = 'true';
  env.POTATO_TRADING_MODE = env.POTATO_TRADING_MODE || 'dry_run';
  const potatoDir = findPotatoDir();
  const configDir = findConfigDir();
  const pythonPaths = [backendDir];
  if (potatoDir) pythonPaths.push(path.dirname(potatoDir));
  if (configDir) pythonPaths.push(path.dirname(configDir));
  env.PYTHONPATH = pythonPaths.join(path.delimiter);
  let stderrBuffer = '';
  try {
    backendProcess = spawn(py, ['main.py'], { cwd: backendDir, stdio: ['ignore', 'pipe', 'pipe'], env, detached: false });
    backendStarted = true;
    backendProcess.stdout.on('data', (data) => { const msg = data.toString().trim(); if (msg) { console.log('[backend]', msg); fs.appendFileSync(LOG_FILE, `[${new Date().toISOString()}] [backend] ${msg}\n`, 'utf-8'); } });
    backendProcess.stderr.on('data', (data) => { const msg = data.toString().trim(); if (msg) { console.error('[backend]', msg); stderrBuffer += msg + '\n'; fs.appendFileSync(LOG_FILE, `[${new Date().toISOString()}] [backend-err] ${msg}\n`, 'utf-8'); } });
    backendProcess.on('error', (e) => { logger.error(`后端进程错误: ${e.message}`); });
    backendProcess.on('exit', (code, signal) => { if (!backendShutdown) { logger.error(`后端意外退出 (code=${code}, signal=${signal})`); } backendReady = false; });
    logger.success(`后端进程已启动 (PID: ${backendProcess.pid})`);
    setTimeout(() => { if (!backendReady) { checkBackendHealth(3000).then((healthy) => { if (healthy) { backendReady = true; logger.success('🎉 后端已准备就绪！'); } else { logger.warn('⚠️  后端启动缓慢或未就绪，等待中...'); } }); } }, 1000);
  } catch (e) { logger.error(`启动后端异常: ${e.message}`); }
}

function createWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;

  const win = new BrowserWindow({
    width: 1100,
    height: 750,
    x: Math.max(0, (width - 1100) / 2),
    y: Math.max(0, (height - 750) / 2),
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    alwaysOnTop: true,
    hasShadow: false,
    resizable: true,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  });

  // 麦克风权限：自动允许所有媒体权限
  win.webContents.session.setPermissionRequestHandler((webContents, permission, callback) => {
    if (['media', 'audioCapture', 'videoCapture', 'midi', 'clipboardRead', 'clipboardWrite'].includes(permission)) {
      callback(true);
    } else {
      callback(true);
    }
  });
  win.webContents.session.setPermissionCheckHandler((webContents, permission, requestingOrigin) => {
    return true;
  });

  const isDev = !app.isPackaged;
  if (isDev) {
    win.loadURL('http://localhost:5173');
  } else {
    const distIndex = path.join(__dirname, 'dist', 'index.html');
    if (fs.existsSync(distIndex)) { win.loadFile(distIndex); }
    else { const altIndex = path.join(process.resourcesPath, 'app', 'dist', 'index.html'); if (fs.existsSync(altIndex)) { win.loadFile(altIndex); } else { logger.error(`找不到界面文件`); } }
  }

  // 不穿透 — 依赖CSS pointer-events来控制穿透
  // 透明区域pointer-events:none, 聊天卡片pointer-events:auto
  // 这样窗口可通过聊天卡片头拖拽

  win.on('did-fail-load', (_e, code, desc) => { logger.error(`页面加载失败: ${code} ${desc}`); });
  win.on('render-process-gone', (_e, details) => { logger.error(`渲染进程崩溃: ${details.reason}`); setTimeout(() => win.reload(), 1000); });
  logger.success('前端窗口已创建');
}

function killBackend() {
  if (!backendProcess) return;
  backendShutdown = true;
  logger.info('🛑 停止后端进程...');
  try {
    if (process.platform === 'win32') { execSync(`taskkill /pid ${backendProcess.pid} /T /F`, { stdio: 'ignore', timeout: 5000 }); }
    else { backendProcess.kill('SIGTERM'); }
    logger.success('后端已停止');
  } catch (e) { logger.warn(`后端强制关闭: ${e.message}`); try { backendProcess.kill(); } catch (__) {} }
  backendProcess = null;
}

app.whenReady().then(() => {
  startBackend();
  // 延迟创建窗口，等后端启动
  setTimeout(() => {
    createWindow();
  }, 1500);
});

app.on('window-all-closed', () => { killBackend(); if (process.platform !== 'darwin') app.quit(); });
app.on('before-quit', () => { killBackend(); logger.info('应用已关闭'); });
process.on('uncaughtException', (err) => { logger.error(`未捕获异常: ${err.message}`); logger.error(err.stack); });