"""Autonomous A-stock trading system for 小土豆.

Architecture:
    analyzer.py   — Stock screening & analysis engine (technical + fundamental)
    executor.py   — Platform login & trade execution via Bytebot/Playwright
    journal.py    — Trade journal & 复盘 engine (P&L, win rate, AI review)
    risk.py       — Risk management, position sizing, stop-loss
    scheduler.py  — Market hours, auto-cycle scheduling
"""