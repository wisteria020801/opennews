
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

        # 2. Filter news from the last 24 hours (for daily digest)
        # We will iterate all 20 items. If we find older items, we might need to fetch more pages?
        # For simplicity, let's just use what we have, but loosen the time check or debug it.
        # Actually, let's look at the raw time first.
        
        now = datetime.now(timezone.utc)
        # Use a very generous threshold (e.g. 25 hours) to be safe
        time_threshold = now - timedelta(hours=25)
        
        new_items = []
        for item in news_list:
            # Check publish time field, usually "publishTime" or "time" or "created_at"
            # Based on API, it's often "publishTime" (epoch ms) or "time" string
            
            pub_time = None
            if "publishTime" in item:
                # epoch milliseconds
                try:
                    ts = int(item["publishTime"]) / 1000.0
                    pub_time = datetime.fromtimestamp(ts, timezone.utc)
                except:
                    pass
            elif "time" in item:
                 # ISO string or timestamp
                 try:
                     # Some APIs return time as string timestamp
                     if str(item["time"]).isdigit():
                         ts = int(item["time"]) / 1000.0
                         pub_time = datetime.fromtimestamp(ts, timezone.utc)
                     else:
                         pub_time = parse_time(item["time"])
                 except:
                     pass
            elif "createTime" in item:
                 try:
                     pub_time = parse_time(item["createTime"])
                 except:
                     pass
            
            # Debug log
            # logger.info(f"Item time: {pub_time} vs Threshold: {time_threshold}")

            if pub_time:
                # Ensure pub_time has timezone info
                if pub_time.tzinfo is None:
                    pub_time = pub_time.replace(tzinfo=timezone.utc)
                
                if pub_time > time_threshold:
                    new_items.append(item)
            else:
                # Fallback: if no time found, include it anyway to be safe
                new_items.append(item)
        
        if not new_items:
            logger.info("No new news in the last 24 hours.")
            # Daily heartbeat
            await send_tg_msg("🟢 **Daily Report**: No significant news in the past 24 hours.\nMonitor is active and healthy.")
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
        error_msg = f"⚠️ **Monitor Error**: Job failed with error: {str(e)}"
        logger.error(error_msg)
        await send_tg_msg(error_msg)
    finally:
        await client.close()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_cron_job())
