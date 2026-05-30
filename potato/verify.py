"""Startup verification — checks all components are importable and functional.

Run: python -m potato.verify
"""

from potato.version import __version__, __author__, BUILD, FEATURES


def verify():
    errors = []
    warnings = []

    print(f"🥔 小土豆 AI操盘桌宠 v{__version__} (build {BUILD})")
    print(f"   Author: {__author__}")
    print()

    # Version module
    print(f"  ✅ version: v{__version__}, {len(FEATURES)} features")

    # Core imports
    modules = [
        ("potato.llm", "LLM路由(5层+Demo+async)"),
        ("potato.billing", "统一计费(2x加价+QR续费)"),
        ("potato.vault", "密钥保险箱(Fernet AES-128)"),
        ("potato.risk", "风控系统(15条规则)"),
        ("potato.trading.scheduler", "7阶段调度器"),
        ("potato.trading.analyzer", "AI选股引擎"),
        ("potato.trading.executor", "交易执行器"),
        ("potato.trading.broker", "券商适配(dry_run/live)"),
        ("potato.trading.journal", "专业复盘系统"),
        ("potato.trading.plan_execute", "PlanExecute多步分析"),
        ("potato.eastmoney", "东方财富AI SaaS(8API+情感+异动+K线+多源回退)"),
        ("potato.iwencai", "问财智能选股(2API+网页回退+数据中心回退)"),
        ("potato.config", "配置管理"),
        ("potato.memory", "30天记忆系统"),
        ("potato.security", "安全模块(密钥保护+源码保护)"),
        ("potato.plugins", "插件系统(AIS+DeepAudit)"),
    ]

    for mod_name, desc in modules:
        try:
            __import__(mod_name)
            print(f"  ✅ {desc}")
        except Exception as e:
            errors.append(f"{mod_name}: {e}")
            print(f"  ❌ {desc} — {e}")

    # Optional imports
    optional = [
        ("potato.voice", "TTS/STT语音"),
        ("potato.intel", "资讯抓取(RSS)"),
        ("potato.plugins", "插件系统(AIS+DeepAudit)"),
    ]
    for mod_name, desc in optional:
        try:
            __import__(mod_name)
            print(f"  ✅ {desc}")
        except Exception:
            warnings.append(f"{mod_name}: optional, not available")
            print(f"  ⚠️ {desc} — 未安装(可选)")

    # Vault keys
    try:
        from potato.vault import Vault, KNOWN_KEYS
        vault = Vault()
        active = 0
        for key_name in ["DEEPSEEK_API_KEY", "SILICON_API_KEY", "LINER_API_KEY", "OPENAI_API_KEY", "BASE44_API_KEY", "EM_API_KEY", "IWENCAI_API_KEY"]:
            val = vault.get(key_name)
            if val:
                active += 1
                masked = val[:6] + "..." + val[-4:] if len(val) > 10 else "***"
                print(f"  🔑 {key_name}: {masked}")
            else:
                print(f"  🔑 {key_name}: (empty)")

        if active == 0:
            print()
            print("  📋 Demo模式: 无API Key，将使用智能模拟响应")
            print("     粘贴DeepSeek API Key即可解锁真实AI分析")
        else:
            print(f"\n  🟢 {active} API Key(s) 已配置")
    except Exception as e:
        errors.append(f"vault: {e}")
        print(f"  ❌ 密钥保险箱: {e}")

    # Database
    try:
        from db_plugin import health_check
        db = health_check()
        if db.get("ok"):
            print(f"  ✅ 数据库: {db.get('backend', 'unknown')}")
        else:
            warnings.append(f"database: {db}")
            print(f"  ⚠️ 数据库: {db}")
    except Exception as e:
        print(f"  ⚠️ 数据库: 未初始化({e})")

    # Summary
    print()
    if errors:
        print(f"  ❌ {len(errors)} 个错误:")
        for e in errors:
            print(f"     • {e}")
    if warnings:
        print(f"  ⚠️ {len(warnings)} 个警告(可选模块)")
    if not errors:
        print(f"  ✅ 所有核心组件验证通过！")

    return len(errors) == 0


if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    ok = verify()
    sys.exit(0 if ok else 1)