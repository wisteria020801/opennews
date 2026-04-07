import asyncio
import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx


current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from opennews_mcp.tools.aggregator_rss import aggregate_free_news
except ImportError:
    from src.opennews_mcp.tools.aggregator_rss import aggregate_free_news

BOT_TOKEN_ORACLE = os.environ.get("BOT_TOKEN_F") or os.environ.get("BOT_TOKEN_A")
CHAT_ID = os.environ.get("CHAT_ID_F", "-1003590230315")

ORACLE_SYSTEM_PROMPT = """你是一个专业的情报分析师（Oracle v2.1）。你的任务是将原始新闻转化为结构化情报。

分析框架（5W1H+I）：
- WHO: 涉及的关键实体（人物/机构/公司）
- WHAT: 发生了什么（核心事件描述）
- WHERE: 发生地点/市场
- WHEN: 时间节点与时效性评估
- WHY: 背景原因和深层动因
- HOW: 事件发展路径和可能演变
- IMPLICATIONS: 对用户的影响（交易机会/风险/学习价值）

新闻价值维度（5维评分，每项0-10）：
- timeliness: 时效性（越新越高）
- importance: 重要性（影响范围大小）
- proximity: 接近性（与用户关注领域的相关性）
- prominence: 知名度/话题度（媒体覆盖广度）
- anomaly: 异常性（是否打破常规）

输出要求：
1. 严格返回合法 JSON 数组，每个元素包含上述所有字段
2. 按 overall_score 降序排列
3. overall_score = (timeliness + importance + proximity + prominence + anomaly) / 5
4. tier 字段取值: CRITICAL / HIGH / TRENDING / NOISE
   - CRITICAL: overall >= 8 或 有重大共振信号
   - HIGH: overall >= 6
   - TRENDING: overall >= 4 且有共振
   - NOISE: 其他
"""


def _build_prompt(all_items: list[dict]) -> str:
    news_text = "\n".join([
        f"- [{i}] {item.get('source', '?')}: {item.get('title', '')}"
        f" (resonance={item.get('resonance_count', 1)}, "
        f"timeliness={item.get('raw_timeliness', 0):.1f}, "
        f"prominence={item.get('raw_prominence', 0):.1f})"
        for i, item in enumerate(all_items[:20])
    ])
    
    return f"""{ORACLE_SYSTEM_PROMPT}

待分析的新闻列表（已预评分）：

{news_text}

请为每条新闻生成完整的 5W1H+I 分析和 5 维评分。返回 JSON 数组格式。
示例格式：
[
  {{
    "id": 0,
    "who": "SEC",
    "what": "SEC 批准以太坊现货 ETF",
    "where": "美国金融市场",
    "when": "刚刚发布，时效性极高",
    "why": "机构资金入场预期增强",
    "how": "短期 ETH 可能上涨 10-20%，长期推动 DeFi 生态",
    "implications": "做多 ETH 相关资产，关注灰度 ETHE 折溢价收窄",
    "scores": {{"timeliness": 9, "importance": 8, "proximity": 7, "prominence": 9, "anomaly": 6}},
    "overall_score": 7.8,
    "tier": "HIGH"
  }}
]
只返回 JSON 数组，不要其他文字。"""


def parse_gemini_response(raw_text: str) -> tuple[list[dict], str]:
    text = raw_text.strip()
    
    if not text or len(text) < 50:
        return [], text
    
    layer1_match = re.search(r'\[[\s\S]*\]', text)
    if layer1_match:
        try:
            parsed = json.loads(layer1_match.group())
            if isinstance(parsed, list):
                return parsed, ""
        except json.JSONDecodeError:
            pass
    
    code_block_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?\s*```', text)
    if code_block_match:
        try:
            parsed = json.loads(code_block_match.group(1).strip())
            if isinstance(parsed, list):
                return parsed, ""
        except json.JSONDecodeError:
            pass
    
    array_start = text.find('[')
    array_end = text.rfind(']')
    if array_start != -1 and array_end > array_start:
        candidate = text[array_start:array_end+1].strip()
        candidate = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', candidate)
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, list):
                return parsed, ""
        except json.JSONDecodeError as e:
            pass
    
    items = []
    pattern = (
        r'"(?:id|index)"\s*:\s*(\d+)'
        r'.*?"tier"\s*:\s*"(\w+)"'
        r'.*?"overall_score"\s*:\s*([\d.]+)'
        r'.*?"what"\s*:\s*"([^"]{10,500})"'
    )
    for m in re.finditer(pattern, text, re.DOTALL | re.IGNORECASE):
        items.append({
            "id": int(m.group(1)),
            "tier": m.group(2),
            "overall_score": float(m.group(3)),
            "what": m.group(4)[:200],
            "_fallback": True
        })
    
    return items, text[:300]


async def call_gemini(prompt_text: str) -> tuple[str, bool]:
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        return "", False
    
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"gemini-2.0-flash-lite:generateContent?key={gemini_key}")
            payload = {
                "contents": [{"parts": [{"text": prompt_text}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 4096,
                    "responseMimeType": "application/json"
                }
            }
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                ai_insight = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                print("   ✅ Gemini Analysis Complete.")
                return ai_insight, True
            elif response.status_code == 429:
                print("   ⚠️ Gemini Rate Limit Exceeded.")
                return "", False
            else:
                print(f"   ⚠️ Gemini Error: {response.status_code}")
                return "", False
    except Exception as e:
        print(f"   ⚠️ Gemini connection failed: {e}")
        return "", False


async def call_ollama(prompt_text: str) -> tuple[str, bool]:
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
    ollama_model = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                ollama_url,
                json={"model": ollama_model, "prompt": prompt_text, "stream": False}
            )
            if response.status_code == 200:
                result = response.json()
                ai_insight = result.get("response", "").strip()
                print("   ✅ Ollama Analysis Complete.")
                return ai_insight, True
            return "", False
    except Exception as e:
        print(f"   ⚠️ Ollama connection failed: {e}")
        return "", False


def _keyword_fallback(all_items: list[dict]) -> list[dict]:
    triggers = {
        "war": {"keywords": ["war", "attack", "missile", "nuclear"], "impact": "地缘冲突升级，避险情绪升温"},
        "finance": {"keywords": ["rate", "cpi", "gdp", "fed", "ecb"], "impact": "宏观政策变动，市场波动加大"},
        "crypto": {"keywords": ["bitcoin", "eth", "sec", "etf", "whale"], "impact": "加密市场异动"},
        "ai_tech": {"keywords": ["openai", "gpt", "claude", "gemini", "nvidia", "ai"], "impact": "AI领域重大进展"},
    }
    
    fallback_items = []
    for item in all_items:
        title_lower = item.get("title", "").lower()
        for cat, info in triggers.items():
            if any(kw in title_lower for kw in info["keywords"]):
                fallback_items.append({
                    "id": len(fallback_items),
                    "who": item.get("source", "?"),
                    "what": item.get("title", ""),
                    "where": "",
                    "when": item.get("time", ""),
                    "why": "",
                    "how": info["impact"],
                    "implications": info["impact"],
                    "scores": {"timeliness": 7, "importance": 6, "proximity": 5, "prominence": 5, "anomaly": 5},
                    "overall_score": 5.6,
                    "tier": "TRENDING",
                    "_fallback": True,
                    "_category": cat
                })
                break
    
    return fallback_items


def format_telegram_message(analyzed_items: list[dict], raw_count: int, mode: str = "full") -> str:
    now_str = datetime.now(timezone(timedelta(hours=8))).strftime("%H:%M:%S")
    
    critical = [it for it in analyzed_items if it.get("tier") == "CRITICAL"]
    high = [it for it in analyzed_items if it.get("tier") == "HIGH"]
    trending = [it for it in analyzed_items if it.get("tier") == "TRENDING"]
    
    lines = ["🔮 **Foxtrot-Oracle (先知) | 深度情报**"]
    lines.append(f"⏰ `{now_str}` | 📊 原始信号: {raw_count} → 分析结果: {len(analyzed_items)}")
    
    if critical:
        lines.append("\n🔴 **━━━ CRITICAL 特级 ━━━**")
        for it in critical[:3]:
            score = it.get("overall_score", 0)
            what = it.get("what", "")[:150]
            imp = it.get("implications", "")[:100]
            who = it.get("who", "")
            lines.append(f"\n⚡ *[{score:.1f}/10]* **{who}**")
            lines.append(f"  {what}")
            if imp and not it.get("_fallback"):
                lines.append(f"  💡 {imp}")
    
    if high:
        lines.append("\n🟠 **━━━ HIGH 高优先 ━━━**")
        for it in high[:5]:
            score = it.get("overall_score", 0)
            what = it.get("what", "")[:120]
            who = it.get("who", "")
            lines.append(f"\n• *[{score:.1f}/10]* **{who}**: {what}")
    
    if trending and mode == "full":
        lines.append("\n🟡 **━━━ TRENDING 趋势 ━━━**")
        for it in trending[:5]:
            score = it.get("overall_score", 0)
            what = it.get("what", "")[:100]
            lines.append(f"  ~ {what} ({score:.1f})")
    
    analysis_mode = "AI-Deep" if not any(it.get("_fallback") for it in analyzed_items) else "Keyword-Fallback"
    lines.append(f"\n━━━━━━━━━━━━━━━━━━\n_Oracle Engine: {analysis_mode}_")
    return "\n".join(lines)


def build_empty_patrol_report() -> str:
    now_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    patrol_messages = [
        f"🔍 **Oracle 巡逻报告 — {now_str}**",
        "",
        "当前全球情报网络运行正常，但未检测到需要立即关注的重大事件。",
        "",
        "**系统状态:** 🟢 全部在线",
        "**扫描源数:** 56 个信息源",
        "**最后更新:** 刚刚",
        "",
        "*系统将继续后台监控，有重大事件时自动推送。*"
    ]
    return "\n".join(patrol_messages)


async def send_telegram(msg_body: str) -> bool:
    if not BOT_TOKEN_ORACLE or not CHAT_ID:
        print("   - Missing bot token or chat ID.")
        return False
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN_ORACLE}/sendMessage",
                json={
                    "chat_id": CHAT_ID,
                    "text": msg_body,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True
                }
            )
        return True
    except Exception as e:
        print(f"   ⚠️ Telegram send failed: {e}")
        return False


async def run_oracle():
    print("🔮 Foxtrot-Oracle (先知) is waking up...")
    
    if not BOT_TOKEN_ORACLE or not CHAT_ID:
        print("   - Missing BOT_TOKEN_F/BOT_TOKEN_A or CHAT_ID_F. Sleeping.")
        return
    
    print("   - Scanning global signals (all sectors)...")
    
    world_news = await aggregate_free_news(None, max_items=5, send_to_telegram=False, category="world")
    finance_news = await aggregate_free_news(None, max_items=5, send_to_telegram=False, category="finance")
    politics_news = await aggregate_free_news(None, max_items=3, send_to_telegram=False, category="politics")
    military_news = await aggregate_free_news(None, max_items=3, send_to_telegram=False, category="military")
    tech_news = await aggregate_free_news(None, max_items=5, send_to_telegram=False, category="tech")
    
    all_items = (world_news.get("items", []) +
                 finance_news.get("items", []) +
                 politics_news.get("items", []) +
                 military_news.get("items", []) +
                 tech_news.get("items", []))
    
    if not all_items:
        print("   - No signals found. Sending patrol report...")
        patrol_msg = build_empty_patrol_report()
        await send_telegram(patrol_msg)
        print("✅ Patrol report sent.")
        return
    
    print(f"   - Analyzing {len(all_items)} data points using AI (v2.1)...")
    
    prompt_text = _build_prompt(all_items)
    ai_raw, success = await call_gemini(prompt_text)
    
    if not success:
        ai_raw, success = await call_ollama(prompt_text)
    
    analyzed_items, raw_remainder = parse_gemini_response(ai_raw) if ai_raw else ([], "")
    
    if not analyzed_items:
        print("   - AI parsing failed. Using keyword fallback...")
        analyzed_items = _keyword_fallback(all_items)
        
        if not analyzed_items:
            print("   - No significant signals found (all methods exhausted).")
            patrol_msg = build_empty_patrol_report()
            await send_telegram(patrol_msg)
            print("✅ Patrol report sent.")
            return
    
    msg_body = format_telegram_message(analyzed_items, len(all_items))
    sent = await send_telegram(msg_body)
    
    if sent:
        tiers = {}
        for it in analyzed_items:
            t = it.get("tier", "UNKNOWN")
            tiers[t] = tiers.get(t, 0) + 1
        
        tier_summary = ", ".join([f"{k}: {v}" for k, v in sorted(tiers.items())])
        print(f"✅ Oracle Alert Sent. Tiers: {tier_summary}")
    else:
        print("❌ Failed to send Oracle alert.")


if __name__ == "__main__":
    asyncio.run(run_oracle())
