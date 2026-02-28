
import asyncio
import logging
import os
import sys
import json
import httpx
from datetime import datetime, timedelta, timezone

# Add src to path so we can import modules
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(os.path.dirname(current_dir))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

try:
    from opennews_mcp.config import API_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    from opennews_mcp.api_client import NewsAPIClient
except ImportError:
    from .config import API_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    from .api_client import NewsAPIClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("cron_job")

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

def parse_time(time_str):
    """Parse ISO time string to datetime object."""
    try:
        # Handle various formats like "2023-10-27T10:00:00Z" or "2023-10-27 10:00:00"
        if time_str.endswith("Z"):
            time_str = time_str[:-1]
        return datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)
    except:
        return datetime.now(timezone.utc)

async def run_cron_job():
    logger.info("Starting Cron Job: Fetch Latest News...")
    
    if not API_TOKEN:
        logger.error("API_TOKEN is missing!")
        return

    client = NewsAPIClient(token=API_TOKEN)
    
    try:
        # 1. Get latest 20 news
        logger.info("Fetching news from API...")
        result = await client.search_news(limit=20, page=1)
        news_list = result.get("data", [])
        
        if not news_list:
            logger.info("No news found.")
            return

        # 2. Filter news from the last 65 minutes (to cover hourly cron + buffer)
        # Assuming we run every hour
        now = datetime.now(timezone.utc)
        time_threshold = now - timedelta(minutes=65)
        
        new_items = []
        for item in news_list:
            # Check publish time field, usually "publishTime" or "time" or "created_at"
            # Based on API, it's often "publishTime" (epoch ms) or "time" string
            # Let's inspect the item structure or try common fields
            
            pub_time = None
            if "publishTime" in item:
                # epoch milliseconds
                try:
                    ts = int(item["publishTime"]) / 1000.0
                    pub_time = datetime.fromtimestamp(ts, timezone.utc)
                except:
                    pass
            elif "time" in item:
                 # ISO string
                 pub_time = parse_time(item["time"])
            elif "createTime" in item:
                 pub_time = parse_time(item["createTime"])
            
            # If no time found, assume it's recent enough if it's in top 20
            # But to be safe for cron duplication, we should try to filter.
            # If we can't parse time, we include it? No, better to be strict or rely on ID storage.
            # Since this is a stateless cron, filtering by time is best.
            
            if pub_time:
                if pub_time > time_threshold:
                    new_items.append(item)
            else:
                # Fallback: if no time, maybe include top 5 unconditionally?
                # Let's just log warning
                pass
        
        if not new_items:
            logger.info("No *new* news in the last hour.")
            return

        logger.info(f"Found {len(new_items)} new articles.")
        
        # 3. Send to Telegram (Oldest first to maintain timeline order)
        for item in reversed(new_items):
            title = item.get("title", "No Title")
            content = item.get("content", "")
            url = item.get("url", "")
            source = item.get("source", "Unknown")
            coins = ", ".join(item.get("coins", []) or [])
            
            tg_text = f"*{title}*\n\n{content[:200]}...\n\n"
            if coins:
                tg_text += f"Coins: `{coins}`\n"
            tg_text += f"Source: {source}\n"
            if url:
                tg_text += f"[Read More]({url})"
            
            await send_tg_msg(tg_text)
            # Small delay to avoid rate limits
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Job failed: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_cron_job())
