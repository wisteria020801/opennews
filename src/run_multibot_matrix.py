import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path so we can import opennews_mcp
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Try importing with and without src prefix
try:
    from opennews_mcp.tools.aggregator_rss import aggregate_free_news
except ImportError:
    from src.opennews_mcp.tools.aggregator_rss import aggregate_free_news

# --- Configuration Matrix ---
# Define your bots here. 
# You can use the same Chat ID for all bots to aggregate into one group, 
# or different Chat IDs to split into different groups.
BOT_MATRIX = [
    {
        "name": "🌍 Alpha-Sentry (哨兵) | 全球突发",
        "category": "world",
        "bot_token": os.environ.get("BOT_TOKEN_A", "8779113331:AAFcreicqAYw3o1kpXuM0tg18_M9OK5BwYc"), 
        "chat_id": os.environ.get("CHAT_ID_A", "-1002490641199"),
        "enabled": True
    },
    {
        "name": "💹 Beta-Tracker (追踪) | 金融异动",
        "category": "finance",
        "bot_token": os.environ.get("BOT_TOKEN_B", "8620644736:AAEbQO4Pyd85DSnl9sWeNarvFoE_eHJi6Wc"),
        "chat_id": os.environ.get("CHAT_ID_B", "-1002490641199"),
        "enabled": True
    },
    {
        "name": "🏛️ Charlie-Watch (守望) | 政治博弈",
        "category": "politics",
        "bot_token": os.environ.get("BOT_TOKEN_C", "8796569408:AAF92dVSIpePhNah-_9oSiQrN336LeuehKY"),
        "chat_id": os.environ.get("CHAT_ID_C", "-1002490641199"),
        "enabled": True
    },
    {
        "name": "📡 Delta-Radar (雷达) | 娱乐/舆情",
        "category": "entertainment",
        "bot_token": os.environ.get("BOT_TOKEN_D", "8761221962:AAH30LkK8w3_0MYskER1SEHOFKkKZm1gDWE"),
        "chat_id": os.environ.get("CHAT_ID_D", "-1002490641199"),
        "enabled": True
    },
    {
        "name": "⚔️ Echo-WarRoom (战情) | 军事冲突",
        "category": "military",
        "bot_token": os.environ.get("BOT_TOKEN_E", "8522929670:AAEsHh99W4M_erlW5vgsymJFDlqTmJpRHSY"),
        "chat_id": os.environ.get("CHAT_ID_E", "-1002490641199"),
        "enabled": True
    },
]

async def run_matrix():
    print("🚀 Starting Multi-Bot News Matrix...")
    
    for bot_config in BOT_MATRIX:
        if not bot_config["enabled"]:
            continue
            
        print(f"\n--------------------------------------------------")
        print(f"🤖 Running: {bot_config['name']}")
        print(f"📂 Category: {bot_config['category']}")
        
        # Skip if credentials missing (demo safety)
        if not bot_config["bot_token"] or not bot_config["chat_id"]:
            print(f"⚠️  Skipping: Missing token or chat_id for {bot_config['name']}")
            print(f"   (Please set environment variables or edit this script)")
            continue
        
        # Debug: Print Token Masked
        masked_token = bot_config["bot_token"][:4] + "***" + bot_config["bot_token"][-4:]
        print(f"   🔑 Using Token: {masked_token} | Chat ID: {bot_config['chat_id']}")

        try:
            result = await aggregate_free_news(
                ctx=None,
                max_items=10,
                send_to_telegram=True,
                category=bot_config["category"],
                bot_token=bot_config["bot_token"],
                chat_id=bot_config["chat_id"]
            )
            
            status = result.get("telegram", "unknown")
            count = result.get("count", 0)
            print(f"✅ Success. Fetched {count} items. Telegram status: {status}")
            
        except Exception as e:
            print(f"❌ Error running {bot_config['name']}: {e}")

    print("\n--------------------------------------------------")
    print("🏁 Matrix Run Complete.")

if __name__ == "__main__":
    # Load .env if you have python-dotenv installed, otherwise rely on system envs
    # from dotenv import load_dotenv
    # load_dotenv()
    
    asyncio.run(run_matrix())
