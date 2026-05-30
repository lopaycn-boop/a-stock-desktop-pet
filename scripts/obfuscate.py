#!/usr/bin/env python3
"""Source code obfuscation for public release."""
import os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def obfuscate_frontend():
    dist = os.path.join(ROOT, 'desktop_pet', 'frontend', 'dist', 'assets')
    js_files = [f for f in os.listdir(dist) if f.endswith('.js')]
    for js in js_files:
        src = os.path.join(dist, js)
        print(f'  Obfuscating {js}...')
        subprocess.run([
            sys.executable, '-m', 'javascript_obfuscator', src,
            '--output', src,
            '--compact', 'true',
            '--control-flow-flattening', 'true',
            '--dead-code-injection', 'true',
            '--string-array', 'true',
            '--string-array-encoding', 'rc4',
            '--string-array-threshold', '0.75',
            '--self-defending', 'true',
            '--debug-protection', 'true',
            '--seed', '42',
        ], check=False)

def compile_backend():
    src = os.path.join(ROOT, 'potato')
    out = os.path.join(ROOT, 'dist_obfuscated', 'potato')
    if os.path.exists(out):
        shutil.rmtree(out)
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in files:
            src_path = os.path.join(root, f)
            rel = os.path.relpath(src_path, src)
            dst_path = os.path.join(out, rel)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            if f.endswith('.py') and f != '__init__.py':
                import py_compile
                try:
                    py_compile.compile(src_path, optimize=2)
                    print(f'  Compiled: {rel}')
                except Exception:
                    shutil.copy2(src_path, dst_path)
            else:
                shutil.copy2(src_path, dst_path)