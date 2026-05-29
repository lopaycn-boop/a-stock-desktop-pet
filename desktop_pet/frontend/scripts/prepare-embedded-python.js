#!/usr/bin/env node
/**
 * 自动化嵌入式 Python 准备脚本
 * 在打包前下载和配置嵌入式 Python 3.12
 * 用法: node scripts/prepare-embedded-python.js
 */

import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import https from 'https';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PYTHON_VERSION = '3.12.10';
const PYTHON_URL = `https://www.python.org/ftp/python/${PYTHON_VERSION}/python-${PYTHON_VERSION}-embed-amd64.zip`;
const PYTHON_DIR = path.join(__dirname, '../python');
const ZIP_FILE = path.join(PYTHON_DIR, 'python.zip');
const PYTHON_EXE = path.join(PYTHON_DIR, 'python.exe');

console.log('🔧 小土豆嵌入式 Python 准备工具 v1.0');
console.log(`📦 Python 版本: ${PYTHON_VERSION}`);
console.log(`📍 目标目录: ${PYTHON_DIR}\n`);

// 1. 检查是否已存在
if (fs.existsSync(PYTHON_EXE)) {
  console.log('✅ 嵌入式 Python 已存在，跳过下载');
  console.log(`   ${PYTHON_EXE}\n`);
  process.exit(0);
}

// 2. 创建目录
if (!fs.existsSync(PYTHON_DIR)) {
  console.log(`📁 创建目录: ${PYTHON_DIR}`);
  fs.mkdirSync(PYTHON_DIR, { recursive: true });
}

// 3. 下载
console.log(`⬇️  正在下载 Python ${PYTHON_VERSION}...`);
console.log(`   ${PYTHON_URL}\n`);

downloadFile(PYTHON_URL, ZIP_FILE, (err) => {
  if (err) {
    console.error(`\n❌ 下载失败: ${err.message}`);
    process.exit(1);
  }

  console.log(`✅ 下载完成: ${ZIP_FILE}\n`);

  // 4. 解压
  console.log('📦 解压 Python...');
  try {
    if (process.platform === 'win32') {
      // Windows: 使用 PowerShell 解压
      execSync(
        `powershell -NoProfile -Command "Expand-Archive -Path '${ZIP_FILE}' -DestinationPath '${PYTHON_DIR}' -Force"`,
        { stdio: 'inherit' }
      );
    } else {
      // macOS/Linux: 使用 unzip
      execSync(`unzip -q "${ZIP_FILE}" -d "${PYTHON_DIR}"`, { stdio: 'inherit' });
    }
    console.log('✅ 解压完成\n');
  } catch (e) {
    console.error(`\n❌ 解压失败: ${e.message}`);
    process.exit(1);
  }

  // 5. 清理 zip
  try {
    fs.unlinkSync(ZIP_FILE);
    console.log('🗑️  已删除临时文件\n');
  } catch (e) {
    console.warn(`⚠️  无法删除 ${ZIP_FILE}: ${e.message}\n`);
  }

  // 6. 验证
  if (!fs.existsSync(PYTHON_EXE)) {
    console.error(`❌ Python 解压失败，未找到 ${PYTHON_EXE}`);
    process.exit(1);
  }

  // 7. 升级 pip
  console.log('🔄 升级 pip...');
  try {
    execSync(`"${PYTHON_EXE}" -m pip install --upgrade pip setuptools wheel`, {
      stdio: 'inherit',
      timeout: 120000,
    });
    console.log('✅ pip 已升级\n');
  } catch (e) {
    console.warn(`⚠️  pip 升级失败（非关键）: ${e.message}\n`);
  }

  // 8. 安装后端依赖
  console.log('📦 安装后端依赖...');
  const backendReqFile = path.join(__dirname, '..', 'backend', 'requirements.txt');
  const rootReqFile = path.join(__dirname, '..', '..', 'requirements.txt');

  const reqFile = fs.existsSync(backendReqFile) ? backendReqFile : rootReqFile;

  if (!fs.existsSync(reqFile)) {
    console.warn(`⚠️  找不到 requirements.txt: ${reqFile}`);
    console.log('   跳过依赖安装，需要手动运行:');
    console.log(`   "${PYTHON_EXE}" -m pip install -r "${rootReqFile}"\n`);
  } else {
    try {
      execSync(
        `"${PYTHON_EXE}" -m pip install -r "${reqFile}" --no-warn-script-location`,
        {
          stdio: 'inherit',
          timeout: 300000, // 5 分钟
        }
      );
      console.log('✅ 依赖安装完成\n');
    } catch (e) {
      console.error(`\n❌ 依赖安装失败: ${e.message}`);
      console.log('\n🔧 手动修复:');
      console.log(`   "${PYTHON_EXE}" -m pip install -r "${reqFile}"\n`);
      process.exit(1);
    }
  }

  console.log('═══════════════════════════════════════════════════════');
  console.log('✅ 嵌入式 Python 准备完成！');
  console.log('═══════════════════════════════════════════════════════');
  console.log(`\n📌 Python 位置: ${PYTHON_EXE}`);
  console.log(`   现在可以运行: npm run pack:win\n`);
});

/**
 * 下载文件
 */
function downloadFile(url, dest, callback) {
  const file = fs.createWriteStream(dest);
  let totalSize = 0;
  let downloadedSize = 0;

  https
    .get(url, (response) => {
      if (response.statusCode === 302 || response.statusCode === 301) {
        // 重定向
        return downloadFile(response.headers.location, dest, callback);
      }

      if (response.statusCode !== 200) {
        callback(new Error(`HTTP ${response.statusCode}`));
        return;
      }

      totalSize = parseInt(response.headers['content-length'], 10);

      response.on('data', (chunk) => {
        downloadedSize += chunk.length;
        const percent = Math.round((downloadedSize / totalSize) * 100);
        process.stdout.write(`\r   下载进度: ${percent}% (${formatBytes(downloadedSize)}/${formatBytes(totalSize)})`);
      });

      response.pipe(file);
    })
    .on('error', (err) => {
      fs.unlink(dest, () => {});
      callback(err);
    });

  file.on('finish', () => {
    file.close(callback);
  });

  file.on('error', (err) => {
    fs.unlink(dest, () => {});
    callback(err);
  });
}

function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}
