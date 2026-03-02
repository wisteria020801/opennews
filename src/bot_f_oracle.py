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

    # 2. AI Analysis (Gemini Cloud API > Local Ollama > Keyword Fallback)
    # ------------------------------------------------------------------
    # Strategy:
    # 1. Try Gemini API (Cloud-Ready, Free Tier)
    # 2. Try Local Ollama (Local Dev)
    # 3. Fallback to Keywords
    # ------------------------------------------------------------------
    print(f"   - Analyzing {len(all_items)} data points using AI...")
    
    ai_insight = ""
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    # Prepare prompt (Shared)
    news_text = "\n".join([f"- {item.get('source')}: {item.get('title')}" for item in all_items[:15]])
    prompt_text = f"""
    你是一个专业的情报分析师（Oracle）。请根据以下新闻标题，分析全球风险和金融套利机会：
    
    {news_text}
    
    任务：
    1. 识别一个最关键的事件。
    2. 预测一个短期市场影响（如：黄金上涨，加密货币下跌）。
    3. 请用中文回答，保持简练（50字以内）。
    4. 格式： "🔴 [事件] -> 📉/📈 [影响]"
    """

    # Attempt 1: Gemini API
    if gemini_key:
        try:
            print(f"   - Calling Google Gemini API...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Using Gemini 1.5 Flash (Free Tier friendly)
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt_text}]}]
                }
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    result = response.json()
                    ai_insight = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                    print("   ✅ Gemini Analysis Complete.")
                else:
                    print(f"   ⚠️ Gemini Error: {response.status_code} {response.text}")
        except Exception as e:
            print(f"   ⚠️ Gemini connection failed: {e}")

    # Attempt 2: Local Ollama (if Gemini failed or no key)
    if not ai_insight:
        ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
        ollama_model = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
        try:
            print(f"   - Calling Local Ollama ({ollama_model})...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    ollama_url,
                    json={"model": ollama_model, "prompt": prompt_text, "stream": False}
                )
                if response.status_code == 200:
                    result = response.json()
                    ai_insight = result.get("response", "").strip()
                    print("   ✅ Ollama Analysis Complete.")
        except Exception as e:
            print(f"   ⚠️ Ollama connection failed: {e}")

    # Fallback: Keyword Resonance
    resonant_items = []
    if not ai_insight:
        print("   - Fallback to Keyword Resonance...")
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
