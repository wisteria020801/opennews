"""Configuration and shared utilities for the OpenNews MCP server.

Reads settings from config.json at project root. Environment variables
can still override any value.
"""

import json
import os
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path

# ---------- Load config.json ----------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config.json"

_cfg: dict = {}
if _CONFIG_PATH.exists():
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        _cfg = json.load(f)

# ---------- API (env vars take precedence) ----------
API_BASE_URL = os.environ.get("OPENNEWS_API_BASE") or _cfg.get("api_base_url", "https://ai.6551.io")
WSS_URL      = os.environ.get("OPENNEWS_WSS_URL")  or _cfg.get("wss_url", "wss://ai.6551.io/open/news_wss")
API_TOKEN    = os.environ.get("OPENNEWS_TOKEN")    or _cfg.get("api_token", "")

# 检查 token 是否配置 (RSS 模式下可选，不再强制报错)
if not API_TOKEN:
    # 兼容旧代码逻辑，给一个 dummy 值，避免导入时报错
    # 真正的鉴权会在调用 6551 API 时进行，如果不用 6551 API 则无影响
    API_TOKEN = "dummy_token_rss_mode"
    # print("Warning: OPENNEWS_TOKEN 未配置，将无法使用 6551.io 数据源 (RSS 源不受影响)。")

# ---------- Telegram ----------
_telegram_cfg = _cfg.get("telegram", {})
TELEGRAM_BOT_TOKEN = os.environ.get("OPENNEWS_TELEGRAM_BOT_TOKEN") or _telegram_cfg.get("bot_token", "")
TELEGRAM_CHAT_ID   = os.environ.get("OPENNEWS_TELEGRAM_CHAT_ID")   or _telegram_cfg.get("chat_id", "")

# ---------- Safety ----------
MAX_ROWS = int(os.environ.get("OPENNEWS_MAX_ROWS", 0) or _cfg.get("max_rows", 100))


def clamp_limit(limit: int) -> int:
    """Clamp user-supplied limit to [1, MAX_ROWS]."""
    return min(max(1, limit), MAX_ROWS)


def make_serializable(obj):
    """Recursively convert non-JSON-serializable types."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [make_serializable(item) for item in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    return obj
