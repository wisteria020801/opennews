import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add project root to sys.path so we can import opennews_mcp
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from opennews_mcp.tools.aggregator_rss import aggregate_free_news
except ImportError:
    from src.opennews_mcp.tools.aggregator_rss import aggregate_free_news

# Configuration for Bot E (The Oracle)
# Use a separate token if available, otherwise reuse one (e.g. Bot A) but run independently
BOT_TOKEN_ORACLE = os.environ.get("BOT_TOKEN_ORACLE", os.environ.get("BOT_TOKEN_A", "8779113331:AAFcreicqAYw3o1kpXuM0tg18_M9OK5BwYc"))
CHAT_ID = os.environ.get("CHAT_ID_E", "-5129534387") # Send to same group

async def run_oracle():
    print("🔮 Oracle (Bot Final) is waking up...")
    
    # 1. Aggregate signals from all sectors (World, Finance, Politics)
    print("   - Scanning global signals...")
    
    # Fetch top 3 items from each key sector
    world_news = await aggregate_free_news(None, max_items=3, send_to_telegram=False, category="world")
    finance_news = await aggregate_free_news(None, max_items=3, send_to_telegram=False, category="finance")
    politics_news = await aggregate_free_news(None, max_items=2, send_to_telegram=False, category="politics")
    
    all_items = world_news.get("items", []) + finance_news.get("items", []) + politics_news.get("items", [])
    
    if not all_items:
        print("   - No significant signals found. Sleeping.")
        return

    # 2. Mock AI Analysis (Replace this with real LLM call later)
    # In Phase 2, we will send `all_items` to GPT-4o/Claude/DeepSeek
    print(f"   - Analyzing {len(all_items)} data points...")
    
    # Simple keyword-based resonance check (The "Poor Man's AI")
    triggers = ["war", "rate", "attack", "sanction", "bitcoin", "oil", "gold", "inflation"]
    resonant_items = []
    
    for item in all_items:
        title = item.get("title", "").lower()
        for t in triggers:
            if t in title:
                resonant_items.append(item)
                break
    
    if not resonant_items:
        print("   - No resonance found. No alert needed.")
        return

    # 3. Generate Oracle Report
    print(f"   - Generating Oracle Report for {len(resonant_items)} critical events...")
    
    report_lines = []
    report_lines.append("🚨 **ORACLE ALERT | 红色高能预警** 🚨")
    report_lines.append(f"⏰ `{datetime.now(timezone(timedelta(hours=8))).strftime('%H:%M:%S')}`\n")
    
    for item in resonant_items[:3]: # Top 3 only
        src = item.get("source", "Unknown")
        title = item.get("title", "")
        report_lines.append(f"⚠️ *{src}*: {title}")
    
    report_lines.append("\n🧠 **Oracle Insight (AI预测)**:")
    report_lines.append("当前局势可能引发 **黄金/原油/BTC** 短期剧烈波动。建议关注波动率指数 (VIX)。")
    report_lines.append("\n━━━━━━━━━━━━━━━━━━\n_Powered by Wisteria Intelligence (Oracle Core)_")
    
    # 4. Send via Bot E
    import httpx
    msg_body = "\n".join(report_lines)
    
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN_ORACLE}/sendMessage",
            json={
                "chat_id": CHAT_ID, 
                "text": msg_body, 
                "parse_mode": "Markdown", 
                "disable_web_page_preview": True
            }
        )
    print("✅ Oracle Alert Sent.")

if __name__ == "__main__":
    asyncio.run(run_oracle())
