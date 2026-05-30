const JavaScriptObfuscator = require('javascript-obfuscator');
const fs = require('fs');
const path = require('path');

const DIST_DIR = path.join(__dirname, 'desktop_pet', 'frontend', 'dist');

const OBFUSCATOR_OPTIONS = {
  compact: true,
  controlFlowFlattening: true,
  controlFlowFlatteningThreshold: 0.75,
  deadCodeInjection: true,
  deadCodeInjectionThreshold: 0.4,
  debugProtection: true,
  debugProtectionInterval: 4000,
  disableConsoleOutput: false,
  identifierNamesGenerator: 'hexadecimal',
  log: false,
  numbersToExpressions: true,
  renameGlobals: false,
  selfDefending: true,
  simplify: true,
  splitStrings: true,
  splitStringsChunkLength: 10,
  stringArray: true,
  stringArrayCallsTransform: true,
  stringArrayCallsTransformThreshold: 0.75,
  stringArrayEncoding: ['rc4'],
  stringArrayIndexShift: true,
  stringArrayRotate: true,
  stringArrayShuffle: true,
  stringArrayWrappersCount: 2,
  stringArrayWrappersChainedCalls: true,
  stringArrayWrappersParametersMaxCount: 4,
  stringArrayWrappersType: 'function',
  stringArrayThreshold: 0.75,
  transformObjectKeys: true,
  unicodeEscapeSequence: false,
};

function obfuscateFile(filePath) {
  const ext = path.extname(filePath);
  if (ext !== '.js' && ext !== '.mjs') return;

  console.log(`Obfuscating: ${path.relative(DIST_DIR, filePath)}`);
  try {
    const source = fs.readFileSync(filePath, 'utf8');
    if (source.length < 200) return;

    const result = JavaScriptObfuscator.obfuscate(source, OBFUSCATOR_OPTIONS);
    fs.writeFileSync(filePath, result.getObfuscatedCode(), 'utf8');
  } catch (e) {
    console.error(`Failed: ${filePath} - ${e.message}`);
  }
}

function walkDir(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walkDir(fullPath);
    } else {
      obfuscateFile(fullPath);
    }
  }
}

console.log('Starting JS obfuscation...');
walkDir(DIST_DIR);
console.log('Done!');