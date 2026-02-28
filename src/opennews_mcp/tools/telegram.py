"""Tool for sending notifications to Telegram."""

import httpx
from mcp.server.fastmcp import Context

from opennews_mcp.app import mcp
from opennews_mcp.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

@mcp.tool()
async def send_telegram_notification(message: str, ctx: Context) -> str:
    """Send a message to the configured Telegram chat.

    Args:
        message: The text message to send.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return "Error: Telegram is not configured. Please set bot_token and chat_id in config.json."

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, timeout=10.0)
            resp.raise_for_status()
            return f"Message sent to Telegram chat {TELEGRAM_CHAT_ID}"
        except httpx.HTTPStatusError as e:
            return f"Failed to send message: HTTP {e.response.status_code} - {e.response.text}"
        except Exception as e:
            return f"Failed to send message: {str(e)}"
