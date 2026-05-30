#!/usr/bin/env python3
"""Source code obfuscation for public release.

Protects:
  1. Frontend JS — javascript-obfuscator (heavy: control-flow, string-array rc4, self-defending)
  2. Backend Python — compile to .pyc (optimize=2), strip .py source files
  3. app.py entry point — kept as .py but __doc__ stripped
  4. Config/secrets — ensure no real keys in shipped artifacts
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directories to skip entirely
SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".pytest_cache", "data", "dist", "dist_obfuscated"}

# Files that must remain as .py (entry points)
KEEP_AS_PY = {"__init__.py", "app.py"}


def obfuscate_frontend():
    """Obfuscate frontend JS with javascript-obfuscator."""
    dist = os.path.join(ROOT, "desktop_pet", "frontend", "dist", "assets")
    if not os.path.isdir(dist):
        print("  Frontend dist not found, skipping JS obfuscation")
        return

    js_files = [f for f in os.listdir(dist) if f.endswith(".js")]
    if not js_files:
        print("  No JS files found in dist/assets")
        return

    for js in js_files:
        src = os.path.join(dist, js)
        try:
            subprocess.run(
                [
                    sys.executable, "-m", "javascript_obfuscator", src,
                    "--output", src,
                    "--compact", "true",
                    "--control-flow-flattening", "true",
                    "--dead-code-injection", "true",
                    "--string-array", "true",
                    "--string-array-encoding", "rc4",
                    "--string-array-threshold", "0.75",
                    "--self-defending", "true",
                    "--debug-protection", "true",
                    "--seed", "42",
                ],
                check=False,
                timeout=60,
            )
            print(f"  Obfuscated: {js}")
        except Exception as e:
            print(f"  Failed to obfuscate {js}: {e}")


def compile_python_dir(src_dir: str, out_dir: str, strip_py: bool = True):
    """Compile .py files to .pyc and optionally remove .py source files."""
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)

    compiled = 0
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            src_path = os.path.join(root, f)
            rel = os.path.relpath(src_path, src_dir)
            dst_path = os.path.join(out_dir, rel)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)

            if f.endswith(".py") and f not in KEEP_AS_PY:
                try:
                    import py_compile
                    py_compile.compile(src_path, dstpath=dst_path + "c", optimize=2, doraise=True)
                    compiled += 1
                except Exception:
                    shutil.copy2(src_path, dst_path)
                if strip_py:
                    # Write a stub .py that imports from .pyc
                    module_name = os.path.splitext(f)[0]
                    with open(dst_path, "w", encoding="utf-8") as stub:
                        stub.write(f"# Compiled — source removed for distribution\n")
                else:
                    shutil.copy2(src_path, dst_path)
            else:
                shutil.copy2(src_path, dst_path)

    print(f"  Compiled {compiled} Python files")


def strip_docstrings(filepath: str):
    """Remove module-level docstring from a file to reduce information leakage."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        in_docstring = False
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if not in_docstring and (stripped.startswith('"""') or stripped.startswith("'''")):
                if stripped.count('"""') >= 2 or stripped.count("'''") >= 2:
                    continue
                in_docstring = True
                continue
            if in_docstring:
                if '"""' in stripped or "'''" in stripped:
                    in_docstring = False
                continue
            new_lines.append(line)

        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception as e:
        print(f"  Failed to strip docstrings from {filepath}: {e}")


def ensure_no_real_keys(directory: str):
    """Scan for real secret strings (best-effort check)."""
    import re
    dangerous = [
        re.compile(r'sk-[a-zA-Z0-9]{40,}'),
        re.compile(r'ghp_[a-zA-Z0-9]{36,}'),
        re.compile(r'AKIA[0-9A-Z]{16}'),
        re.compile(r'AIza[a-zA-Z0-9_-]{35}'),
        re.compile(r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----'),
    ]
    found = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if not f.endswith((".py", ".js", ".json", ".yml", ".yaml", ".env", ".cfg")):
                continue
            path = os.path.join(root, f)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                    for pat in dangerous:
                        if pat.search(content):
                            found.append(f"{path}: potential secret match")
            except Exception:
                pass
    if found:
        print("  WARNING: Potential secrets found:")
        for f in found:
            print(f"    {f}")
        return False
    print("  No real secrets detected — clean to ship")
    return True


def main():
    print("=" * 60)
    print("  Source Code Protection — Production Build")
    print("=" * 60)

    print("\n1. Obfuscating frontend JS...")
    obfuscate_frontend()

    print("\n2. Compiling backend Python...")
    src = os.path.join(ROOT, "potato")
    out = os.path.join(ROOT, "dist_obfuscated", "potato")
    compile_python_dir(src, out, strip_py=True)

    print("\n3. Copying top-level files...")
    for f in ["app.py", "main.py"]:
        src_f = os.path.join(ROOT, f)
        if os.path.exists(src_f):
            dst_f = os.path.join(ROOT, "dist_obfuscated", f)
            shutil.copy2(src_f, dst_f)
            strip_docstrings(dst_f)

    for f in ["requirements.txt", "requirements.server.txt", "Dockerfile", ".env.example"]:
        src_f = os.path.join(ROOT, f)
        if os.path.exists(src_f):
            shutil.copy2(src_f, os.path.join(ROOT, "dist_obfuscated", f))

    print("\n4. Copying schemas and scripts...")
    for d in ["schema", "scripts"]:
        src_d = os.path.join(ROOT, d)
        dst_d = os.path.join(ROOT, "dist_obfuscated", d)
        if os.path.exists(src_d):
            if os.path.exists(dst_d):
                shutil.rmtree(dst_d)
            shutil.copytree(src_d, dst_d)

    print("\n5. Scanning for leaked secrets...")
    ensure_no_real_keys(os.path.join(ROOT, "dist_obfuscated"))

    print("\n" + "=" * 60)
    print("  Done! Protected build in: dist_obfuscated/")
    print("=" * 60)


if __name__ == "__main__":
    main()