import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import httpx

# Add project root to sys.path so we can import opennews_mcp
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from opennews_mcp.tools.aggregator_rss import aggregate_free_news
except ImportError:
    from src.opennews_mcp.tools.aggregator_rss import aggregate_free_news

# Configuration for Bot F (The Oracle / 先知)
# Strategy: Reuse Bot A's token if a dedicated Oracle token is not provided.
# This implements the "5+1" architecture where the 6th bot (Oracle) runs sequentially.
BOT_TOKEN_ORACLE = os.environ.get("BOT_TOKEN_F", os.environ.get("BOT_TOKEN_A", "8779113331:AAFcreicqAYw3o1kpXuM0tg18_M9OK5BwYc"))
CHAT_ID = os.environ.get("CHAT_ID_F", "-5129534387") # Send to same group

async def run_oracle():
    print("🔮 Foxtrot-Oracle (先知) is waking up...")
    
    # 1. Aggregate signals from all sectors (World, Finance, Politics)
    print("   - Scanning global signals...")
    
    # Fetch top 3 items from each key sector
    world_news = await aggregate_free_news(None, max_items=3, send_to_telegram=False, category="world")
    finance_news = await aggregate_free_news(None, max_items=3, send_to_telegram=False, category="finance")
    politics_news = await aggregate_free_news(None, max_items=2, send_to_telegram=False, category="politics")
    military_news = await aggregate_free_news(None, max_items=2, send_to_telegram=False, category="military")
    
    all_items = world_news.get("items", []) + finance_news.get("items", []) + politics_news.get("items", []) + military_news.get("items", [])
    
    if not all_items:
        print("   - No significant signals found. Sleeping.")
        return

    # 2. AI Analysis (Ollama with Fallback)
    # ------------------------------------------------------------------
    # Connects to local Ollama instance (http://localhost:11434)
    # Default model: llama3 (can be changed via OLLAMA_MODEL env var)
    # ------------------------------------------------------------------
    print(f"   - Analyzing {len(all_items)} data points using AI...")
    
    ai_insight = ""
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
    ollama_model = os.environ.get("OLLAMA_MODEL", "llama3")
    
    # Prepare prompt
    news_text = "\n".join([f"- {item.get('source')}: {item.get('title')}" for item in all_items[:15]])
    prompt = f"""
    As an expert intelligence analyst (Oracle), analyze these news headlines for critical global risks and financial arbitrage opportunities:
    
    {news_text}
    
    Task:
    1. Identify the single most critical event.
    2. Predict 1 short-term market impact (e.g., Gold up, Crypto down).
    3. Keep it under 50 words. Use Chinese.
    4. Format: "🔴 [Event] -> 📉/📈 [Impact]"
    """
    
    try:
        print(f"   - Calling Ollama ({ollama_model})...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                ollama_url,
                json={
                    "model": ollama_model,
                    "prompt": prompt,
                    "stream": False
                }
            )
            if response.status_code == 200:
                result = response.json()
                ai_insight = result.get("response", "").strip()
                print("   ✅ AI Analysis Complete.")
            else:
                print(f"   ⚠️ Ollama Error: {response.status_code}")
    except Exception as e:
        print(f"   ⚠️ Ollama connection failed: {e}. Falling back to Keyword Resonance.")

    # Fallback: Keyword Resonance
    resonant_items = []
    if not ai_insight:
        triggers = ["war", "rate", "attack", "sanction", "bitcoin", "oil", "gold", "inflation", "nuclear", "missile", "crash"]
        for item in all_items:
            title = item.get("title", "").lower()
            for t in triggers:
                if t in title:
                    resonant_items.append(item)
                    break
        if resonant_items:
            ai_insight = "检测到高频风险关键词 (War/Finance)。建议关注 **黄金/原油/BTC** 短期剧烈波动。(Fallback Mode)"
        else:
            print("   - No significant signals found (AI & Keyword). Sleeping.")
            return

    # 3. Generate Oracle Report
    print(f"   - Generating Oracle Report...")
    
    report_lines = []
    report_lines.append("🔮 **Foxtrot-Oracle (先知) | 深度总结**")
    report_lines.append(f"⏰ `{datetime.now(timezone(timedelta(hours=8))).strftime('%H:%M:%S')}`\n")
    
    # Show top 3 headlines as context
    for item in all_items[:3]: 
        src = item.get("source", "Unknown")
        title = item.get("title", "")
        report_lines.append(f"⚠️ *{src}*: {title}")
    
    report_lines.append("\n🧠 **Oracle Insight (AI预测)**:")
    report_lines.append(ai_insight)
    report_lines.append("\n━━━━━━━━━━━━━━━━━━\n_Powered by Wisteria_")
    
    # 4. Send via Bot
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
