
import asyncio
import logging
import os
import sys
import json
import httpx

# Add src to path so we can import modules
# File is at src/opennews_mcp/monitor.py
# We want to add 'src' to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(os.path.dirname(current_dir))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

try:
    from opennews_mcp.config import API_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    from opennews_mcp.api_client import NewsWSClient
except ImportError:
    # If run as module "python -m opennews_mcp.monitor"
    from .config import API_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    from .api_client import NewsWSClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("monitor")

async def send_tg_msg(text: str, chat_id: str = None):
    target_chat_id = chat_id or TELEGRAM_CHAT_ID
    if not TELEGRAM_BOT_TOKEN or not target_chat_id:
        logger.error("Telegram not configured (missing token or chat_id)")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json={
                "chat_id": target_chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            })
        except Exception as e:
            logger.error(f"Failed to send TG message: {e}")

# Global status
WS_CONNECTED = False
LAST_WS_ERROR = None

async def news_monitor_loop():
    global WS_CONNECTED, LAST_WS_ERROR
    logger.info("Starting News Monitor...")
    if not API_TOKEN:
        logger.error("API_TOKEN is missing! Cannot connect to WebSocket.")
        await send_tg_msg("⚠️ **Error**: API Token is missing. Please configure it.")
        return

    ws_client = NewsWSClient(token=API_TOKEN)
    
    retry_delay = 5
    while True:
        try:
            logger.info("Connecting to OpenNews WebSocket...")
            await ws_client.connect()
            WS_CONNECTED = True
            LAST_WS_ERROR = None
            
            # Subscribe to all news
            sub_resp = await ws_client.subscribe_latest()
            logger.info(f"Subscribed: {sub_resp}")
            
            await send_tg_msg("🟢 *OpenNews Monitor Started!*\nWatching for news updates...")
            
            while True:
                try:
                    msg = await ws_client.receive_news(timeout=20.0)
                except asyncio.TimeoutError:
                    # Send a ping or just continue to keep connection alive check
                    continue
                except Exception as e:
                    logger.warning(f"Receive error: {e}")
                    break

                if msg:
                    # ... (process msg)
                    data = msg
                    if isinstance(msg, dict) and "data" in msg and isinstance(msg["data"], dict):
                        data = msg["data"]
                    
                    if not isinstance(data, dict) or "title" not in data:
                        continue

                    try:
                        title = data.get("title", "No Title")
                        content = data.get("content", "")
                        url = data.get("url", "")
                        source = data.get("source", "Unknown")
                        coins = ", ".join(data.get("coins", []) or [])
                        
                        tg_text = f"*{title}*\n\n{content[:200]}...\n\n"
                        if coins:
                            tg_text += f"Coins: `{coins}`\n"
                        tg_text += f"Source: {source}\n"
                        if url:
                            tg_text += f"[Read More]({url})"
                            
                        logger.info(f"New News: {title}")
                        await send_tg_msg(tg_text)
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                        
        except Exception as e:
            WS_CONNECTED = False
            LAST_WS_ERROR = str(e)
            logger.error(f"WS Connection error: {e}")
            if "401" in str(e):
                 await send_tg_msg("⚠️ **Error**: API Token is invalid (HTTP 401). Please update your token.")
                 # Sleep longer for auth errors
                 await asyncio.sleep(60)
            else:
                 logger.info(f"Retrying in {retry_delay}s...")
                 await asyncio.sleep(retry_delay)
            
            try:
                await ws_client.close()
            except:
                pass

async def telegram_command_loop():
    # Simple polling for commands
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("Telegram Bot Token missing")
        return

    offset = 0
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    
    logger.info("Starting Telegram Command Listener...")
    async with httpx.AsyncClient() as client:
        while True:
            try:
                try:
                    resp = await client.get(url, params={"offset": offset, "timeout": 30}, timeout=40.0)
                except httpx.ReadTimeout:
                    continue
                except Exception as e:
                    logger.error(f"Polling connection error: {e}")
                    await asyncio.sleep(5)
                    continue

                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        message = update.get("message", {})
                        text = message.get("text", "")
                        chat_id = message.get("chat", {}).get("id")
                        
                        if not text:
                            continue

                        logger.info(f"Received: {text} from {chat_id}")

                        # Handle commands
                        if text.startswith("/start"):
                            await send_tg_msg(
                                "👋 *Hello!*\nI am your OpenNews Bot.\n\n"
                                "Commands:\n"
                                "/ping - Check health\n"
                                "/status - Check connection status\n"
                                "/help - Show this menu",
                                chat_id
                            )
                        elif text.startswith("/ping"):
                            await send_tg_msg("Pong! 🏓", chat_id)
                        elif text.startswith("/status"):
                            status = "🟢 Connected" if WS_CONNECTED else "🔴 Disconnected"
                            msg = f"**System Status**\nWS Connection: {status}"
                            if LAST_WS_ERROR:
                                msg += f"\nLast Error: `{LAST_WS_ERROR}`"
                            await send_tg_msg(msg, chat_id)
                        elif text.startswith("/help"):
                            await send_tg_msg(
                                "🤖 **Bot Commands**\n\n"
                                "/start - Initialize bot\n"
                                "/ping - Check health\n"
                                "/status - Check connection status\n"
                                "/help - Show help",
                                chat_id
                            )
                        elif "@" in text and "bot" in text.lower(): # Simple mention check
                             await send_tg_msg("I received your message! Use /help to see what I can do.", chat_id)
                            
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"TG Polling unexpected error: {e}")
                await asyncio.sleep(5)

async def main():
    print("---------------------------------------------------------")
    print("   OpenNews Monitor & Bot is Running 🚀")
    print("   Press Ctrl+C to stop")
    print("---------------------------------------------------------")

    # Run both tasks
    await asyncio.gather(
        news_monitor_loop(),
        telegram_command_loop()
    )

if __name__ == "__main__":
    try:
        # Windows specific event loop policy
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped by user")
