import asyncio
import os
import sys
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import httpx

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from opennews_mcp.tools.aggregator_rss import (
        detect_resonance, calc_timeliness, calc_prominence,
        _extract_entities, _rank, PRIORITY, HIGH_WEIGHT_ENTITIES
    )
except ImportError:
    from src.opennews_mcp.tools.aggregator_rss import (
        detect_resonance, calc_timeliness, calc_prominence,
        _extract_entities, _rank, PRIORITY, HIGH_WEIGHT_ENTITIES
    )

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_KEY:
    try:
        key_file = project_root / "list_gemini_models.py"
        if key_file.exists():
            content = key_file.read_text(encoding="utf-8")
            match = re.search(r'GEMINI_API_KEY["\']?\s*[:=]\s*["\']([^"\']+)', content)
            if match:
                GEMINI_KEY = match.group(1)
    except Exception:
        pass
if not GEMINI_KEY:
    try:
        key_file = current_dir / ".." / "list_gemini_models.py"
        if key_file.exists():
            content = key_file.read_text(encoding="utf-8")
            match = re.search(r'GEMINI_API_KEY["\']?\s*[:=]\s*["\']([^"\']+)', content)
            if match:
                GEMINI_KEY = match.group(1)
    except Exception:
        pass

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent"

USER_PROFILE = {
    "role": "AI编辑/科技媒体从业者",
    "interests": [
        "AI大模型进展 (GPT/Claude/Gemini/Llama/Qwen)",
        "Agent/MCP协议生态",
        "开源模型与框架",
        "AI创业与投融资",
        "芯片/算力基础设施",
        "AI安全与治理",
        "量化交易与AI结合"
    ],
    "context": "国内头部科技媒体公司，需要快速产出高质量AI领域新闻报道和深度分析"
}

INTEL_SYSTEM_PROMPT = """你是 OpenNews Matrix 的情报分析引擎（Intelligence Engine v2.2）。

你的任务是将原始新闻转化为**结构化情报卡片**，供专业AI编辑使用。

## 分析框架：5W1H+I

| 维度 | 说明 | 输出要求 |
|------|------|---------|
| **WHO** | 关键实体（人物/机构/公司） | 1-2行，列出核心角色 |
| **WHAT** | 发生了什么 | 1-2句精炼描述 |
| **WHERE** | 地点/市场/领域 | 简短标注 |
| **WHEN** | 时间节点 | 相对时间（如"2小时前"） |
| **WHY** | 背景原因/深层动因 | 1-2句分析 |
| **HOW** | 发展路径/可能演变 | 预测性判断 |
| **IMPLICATIONS** | 对用户的影响和价值 | 可操作的建议 |

## 新闻价值评分（5维，每项0-10）

| 维度 | 权重说明 |
|------|---------|
| **timeliness** | 时效性 — 越新越高，30分钟内=10 |
| **importance** | 重要性 — 影响范围（全球>行业>公司） |
| **proximity** | 接近性 — 与用户关注领域的匹配度 |
| **prominence** | 知名度 — 媒体覆盖广度（共振源数量） |
| **anomaly** | 异常性 — 是否打破常规/意外事件 |

## 输出格式要求

严格返回 JSON 数组，每个元素包含：
```json
{{
  "id": 0,
  "who": "OpenAI, Sam Altman",
  "what": "发布 GPT-5 预览版，支持实时联网",
  "where": "美国/全球AI市场",
  "when": "2026-04-07 (2小时前)",
  "why": "应对 Anthropic Claude 4 的竞争压力",
  "how": "短期引发API价格战，长期推动多模态Agent普及",
  "implications": "对AI编辑而言：需关注API能力边界变化，可撰写对比评测",
  "scores": {{
    "timeliness": 9.0,
    "importance": 8.0,
    "proximity": 9.0,
    "prominence": 8.0,
    "anomaly": 6.0
  }},
  "overall_score": 8.0,
  "tier": "CRITICAL",
  "tags": ["LLM", "OpenAI", "API", "竞争"],
  "actionable": "建议今日跟进：测试GPT-5 API兼容性"
}}
```

## 分级标准
- **CRITICAL**: overall >= 8 或 共振源 >= 3 → 必须立即关注
- **HIGH**: overall >= 6-7.9 → 重要，当日必读
- **TRENDING**: overall >= 4-5.9 → 趋势性，值得了解
- **NOISE**: overall < 4 → 噪音，可忽略

## 用户画像
{user_profile_str}

## 共振信号说明
如果某条新闻被多个信息源同时报道（resonance_count >= 2），这表示该事件具有高话题度，
请在 prominence 和 tier 中体现这一点。"""


def _build_user_profile_str() -> str:
    lines = ["**用户画像:**"]
    lines.append(f"- 角色: {USER_PROFILE['role']}")
    lines.append("- 关注领域:")
    for interest in USER_PROFILE["interests"]:
        lines.append(f"  * {interest}")
    lines.append(f"- 背景: {USER_PROFILE['context']}")
    return "\n".join(lines)


def _build_analysis_prompt(items: list[dict], category: str) -> str:
    news_lines = []
    for i, item in enumerate(items[:15]):
        title = item.get("title", "")[:120]
        src = item.get("source", "?")
        res = item.get("resonance_count", 1)
        tim = item.get("_pre_timeliness", 0)
        pro = item.get("_pre_prominence", 0)
        news_lines.append(
            f"[{i}] [{src}] (共振:{res} T:{tim:.0f} P:{pro:.0f}) {title}"
        )
    
    category_names = {
        "tech": "AI/科技前沿",
        "finance": "金融/加密市场",
        "world": "全球突发",
        "military": "军事冲突",
        "politics": "政治博弈",
        "all": "全领域"
    }
    
    prompt = INTEL_SYSTEM_PROMPT.format(user_profile_str=_build_user_profile_str())
    prompt += f"\n\n## 当前分类: {category_names.get(category, category)}"
    prompt += f"\n\n## 待分析新闻 ({len(items)} 条):\n\n"
    prompt += "\n".join(news_lines)
    prompt += "\n\n请为每条新闻生成完整的5W1H+I情报卡片。返回JSON数组。只返回JSON，不要其他文字。"
    
    return prompt


async def call_gemini(prompt_text: str) -> tuple[str, bool]:
    if not GEMINI_KEY:
        print("[Intel] No GEMINI_API_KEY found.")
        return "", False
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "contents": [{"parts": [{"text": prompt_text}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 6000,
                    "responseMimeType": "application/json"
                }
            }
            url = f"{GEMINI_URL}?key={GEMINI_KEY}"
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                print("[Intel] Gemini analysis complete (%d chars)" % len(text))
                return text, True
            elif response.status_code == 429:
                print("[Intel] Gemini rate limited")
                return "", False
            else:
                print("[Intel] Gemini error: %d" % response.status_code)
                return "", False
    except Exception as e:
        print("[Intel] Gemini connection failed: %s" % e)
        return "", False


def parse_gemini_response(raw_text: str) -> tuple[list[dict], str]:
    text = raw_text.strip()
    
    if not text or len(text) < 50:
        return [], text
    
    layer1_match = re.search(r'\[[\s\S]*\]', text)
    if layer1_match:
        try:
            parsed = json.loads(layer1_match.group())
            if isinstance(parsed, list) and len(parsed) > 0:
                return parsed, ""
        except json.JSONDecodeError:
            pass
    
    code_block_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?\s*```', text)
    if code_block_match:
        try:
            parsed = json.loads(code_block_match.group(1).strip())
            if isinstance(parsed, list) and len(parsed) > 0:
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
        except json.JSONDecodeError:
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


def _keyword_fallback(items: list[dict]) -> list[dict]:
    triggers = {
        "ai_breakthrough": {
            "keywords": ["openai", "gpt", "claude", "gemini", "llama", "model release", "benchmark", "sota"],
            "who_tmpl": "{src}",
            "what_tmpl": "{title}",
            "why": "AI技术持续迭代，模型能力边界不断扩展",
            "how": "可能影响现有AI应用架构和开发范式",
            "implications": "作为AI编辑：需评估新技术对内容生产流程的影响",
            "tags": ["AI", "模型"],
            "actionable": "建议跟进：阅读原论文/官方博客，准备深度报道素材"
        },
        "chip_hardware": {
            "keywords": ["nvidia", "gpu", "tpu", "chip", "semiconductor", "tsmc", "data center", "compute"],
            "who_tmpl": "{src}",
            "what_tmpl": "{title}",
            "why": "算力基础设施是AI发展的物理瓶颈",
            "how": "影响训练成本和推理延迟，进而影响AI产品化节奏",
            "implications": "算力动态直接影响AI行业整体发展速度",
            "tags": ["硬件", "算力"],
            "actionable": "建议关注：供应链变化对AI初创公司的影响"
        },
        "startup_funding": {
            "keywords": ["funding", "series", "valuation", "ipo", "acquisition", "unicorn", "startup", "venture"],
            "who_tmpl": "{src}",
            "what_tmpl": "{title}",
            "why": "资本流向反映市场对未来方向的判断",
            "how": "获投领域将加速发展，资源向头部集中",
            "implications": "融资动向预示未来3-6个月的技术热点",
            "tags": ["融资", "创投"],
            "actionable": "建议整理：更新赛道融资地图"
        },
        "policy_regulation": {
            "keywords": ["regulation", "act", "law", "policy", "government", "congress", "eu", "china", "ban", "restriction"],
            "who_tmpl": "{src}",
            "what_tmpl": "{title}",
            "why": "政策法规塑造AI产业格局",
            "how": "合规成本上升，可能重塑市场竞争态势",
            "implications": "政策变化直接影响企业AI战略布局",
            "tags": ["政策", "监管"],
            "actionable": "建议解读：分析政策对不同市场参与者的影响"
        },
        "agent_ecosystem": {
            "keywords": ["agent", "mcp", "tool use", "function calling", "rag", "autonomous", "workflow", "automation"],
            "who_tmpl": "{src}",
            "what_tmpl": "{title}",
            "why": "Agent是AI从聊天工具进化为生产力工具的关键",
            "how": "MCP等协议标准化将降低Agent开发门槛",
            "implications": "Agent生态成熟度直接影响AI落地速度",
            "tags": ["Agent", "MCP"],
            "actionable": "建议测试：验证新工具/协议的实用性"
        }
    }
    
    fallback_items = []
    now = datetime.now(timezone.utc)
    
    for idx, item in enumerate(items):
        title_lower = item.get("title", "").lower()
        matched_trigger = None
        
        for cat, info in triggers.items():
            if any(kw in title_lower for kw in info["keywords"]):
                matched_trigger = info
                break
        
        if not matched_trigger:
            continue
        
        pub_time = item.get("time", now)
        timeliness = calc_timeliness(pub_time, now)
        resonance = item.get("resonance_count", 1)
        prominence = calc_prominence(item.get("source", "?"), resonance)
        
        src = item.get("source", "?")
        title = item.get("title", "")
        
        base_score = (timeliness + 7.0 + 7.0 + prominence + 5.0) / 5
        if resonance >= 3:
            base_score += 1.0
        base_score = min(base_score, 9.5)
        
        if base_score >= 8:
            tier = "CRITICAL"
        elif base_score >= 6:
            tier = "HIGH"
        elif base_score >= 4:
            tier = "TRENDING"
        else:
            tier = "NOISE"
        
        delta = now - pub_time if pub_time else timedelta(0)
        hours_ago = int(delta.total_seconds() / 3600)
        if hours_ago < 1:
            time_str = "刚刚"
        elif hours_ago < 24:
            time_str = "%d小时前" % hours_ago
        else:
            time_str = "%d天前" % (hours_ago // 24)
        
        fallback_items.append({
            "id": idx,
            "who": matched_trigger["who_tmpl"].format(src=src),
            "what": matched_trigger["what_tmpl"].format(title=title[:150]),
            "where": "",
            "when": time_str,
            "why": matched_trigger["why"],
            "how": matched_trigger["how"],
            "implications": matched_trigger["implications"],
            "scores": {
                "timeliness": round(timeliness, 1),
                "importance": 7.0,
                "proximity": 7.0,
                "prominence:": round(prominence, 1),
                "anomaly": 5.0
            },
            "overall_score": round(base_score, 1),
            "tier": tier,
            "tags": matched_trigger["tags"],
            "actionable": matched_trigger["actionable"],
            "_source_title": title,
            "_source_link": item.get("link", ""),
            "_source_src": src,
            "_resonance": resonance,
            "_fallback": True
        })
    
    fallback_items.sort(key=lambda x: x.get("overall_score", 0), reverse=True)
    return fallback_items


def format_intelligence_card(item: dict, index: int) -> str:
    tier_icons = {
        "CRITICAL": "🔴",
        "HIGH": "🟠",
        "TRENDING": "🟡",
        "NOISE": "⚪"
    }
    icon = tier_icons.get(item.get("tier", "NOISE"), "⚪")
    score = item.get("overall_score", 0)
    who = item.get("who", "?")[:50]
    what = item.get("what", "?")[:150]
    where = item.get("where", "")
    when = item.get("when", "")
    why = item.get("why", "")[:100]
    how = item.get("how", "")[:100]
    implications = item.get("implications", "")[:120]
    tags = item.get("tags", [])
    actionable = item.get("actionable", "")
    resonance = item.get("_resonance", item.get("resonance_count", 1))
    
    scores = item.get("scores", {})
    t_val = scores.get("timeliness", 0)
    i_val = scores.get("importance", 0)
    p_val = scores.get("proximity", 0)
    pr_val = scores.get("prominence", 0) if isinstance(scores.get("prominence"), (int, float)) else scores.get("prominence:", 0)
    a_val = scores.get("anomaly", 0)
    
    tag_str = " ".join("#%s" % t for t in tags[:5]) if tags else ""
    res_tag = " x%d" % resonance if resonance > 1 else ""
    
    lines = []
    lines.append("%s **[%d] %s** %s%s" % (icon, index, who, res_tag, ""))
    lines.append("")
    lines.append("**What:** %s" % what)
    if where:
        lines.append("**Where:** %s" % where)
    if when:
        lines.append("**When:** %s" % when)
    if why:
        lines.append("**Why:** %s" % why)
    if how:
        lines.append("**How:** %s" % how)
    if implications:
        lines.append("**Implications:** %s" % implications)
    if actionable:
        lines.append("**Action:** %s" % actionable)
    lines.append("")
    lines.append("*Score: %.1f | T:%.0f I:%.0f P:%.0f Pr:%.0f A:%.0f*" % (score, t_val, i_val, p_val, pr_val, a_val))
    if tag_str:
        lines.append("%s" % tag_str)
    
    source_link = item.get("_source_link", "")
    if source_link:
        lines.append("[原文](%s)" % source_link)
    
    return "\n".join(lines)


def format_intelligence_report(analyzed_items: list[dict], raw_count: int, category: str, mode: str = "full") -> str:
    now_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    category_names = {
        "tech": "AI/科技前沿", "finance": "金融/加密", "world": "全球突发",
        "military": "军事冲突", "politics": "政治博弈", "all": "全领域"
    }
    cat_name = category_names.get(category, category)
    
    critical = [it for it in analyzed_items if it.get("tier") == "CRITICAL"]
    high = [it for it in analyzed_items if it.get("tier") == "HIGH"]
    trending = [it for it in analyzed_items if it.get("tier") == "TRENDING"]
    
    ai_mode = "Gemini-Deep" if not any(it.get("_fallback") for it in analyzed_items) else "Keyword-Smart"
    
    header = (
        "🔍 **OpenNews Intelligence Report v2.2**\n"
        "| %s | `%s` | 📥 原始: %d → 🧠 分析: %d |\n"
        "_Engine: %s_" % (cat_name, now_str, raw_count, len(analyzed_items), ai_mode)
    )
    
    sections = []
    
    if critical:
        sections.append("\n🔴 **━━ CRITICAL 一级警报 ━━**\n")
        for i, it in enumerate(critical[:3]):
            sections.append(format_intelligence_card(it, i+1) + "\n")
    
    if high:
        sections.append("\n🟠 **━━ HIGH 高优先 ━━**\n")
        for i, it in enumerate(high[:5]):
            sections.append(format_intelligence_card(it, i+1) + "\n")
    
    if trending and mode == "full":
        sections.append("\n🟡 **━━ TRENDING 趋势跟踪 ━━**\n")
        for i, it in enumerate(trending[:4]):
            score = it.get("overall_score", 0)
            what = it.get("what", "")[:100]
            tags = it.get("tags", [])
            tag_str = " ".join("#%s" % t for t in tags[:3]) if tags else ""
            sections.append("~ *[%0.1f]* %s %s\n" % (score, what, tag_str))
    
    footer = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "_OpenNews Matrix v2.2 | Powered by RSS + Gemini_"
    )
    
    return header + "".join(sections) + footer


def build_empty_intel_report(category: str) -> str:
    now_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    category_names = {
        "tech": "AI/科技", "finance": "金融", "world": "全球",
        "military": "军事", "politics": "政治", "all": "全领域"
    }
    
    return (
        "🔍 **Intelligence Report — %s**\n\n"
        "%s 分类当前无重大情报信号。\n\n"
        "**系统状态:** 🟢 在线\n"
        "**扫描源数:** 55 个\n"
        "**最后扫描:** %s\n\n"
        "*后台监控持续运行，检测到重大事件时自动推送。*\n\n"
        "输入 `/new` 查看全领域最新动态"
        % (now_str, category_names.get(category, category), now_str)
    )


async def analyze_news(items: list[dict], category: str = "tech", max_analyze: int = 12) -> tuple[list[dict], str]:
    if not items:
        return [], "no_items"
    
    from opennews_mcp.tools.aggregator_rss import _parse_time
    for item in items:
        raw_time = item.get("time")
        if isinstance(raw_time, str):
            try:
                item["time"] = _parse_time(raw_time)
            except Exception:
                pass
    
    items = detect_resonance(items, threshold=0.35)
    
    now = datetime.now(timezone.utc)
    for item in items:
        pub_time = item.get("time", now)
        item["_pre_timeliness"] = calc_timeliness(pub_time, now)
        item["_pre_prominence"] = calc_prominence(
            item.get("source", "?"),
            item.get("resonance_count", 1)
        )
    
    items.sort(key=lambda x: (
        x.get("resonance_count", 1) * -2 +
        x.get("_pre_timeliness", 0) +
        x.get("_pre_prominence", 0) * 0.5
    ), reverse=True)
    
    to_analyze = items[:max_analyze]
    
    prompt = _build_analysis_prompt(to_analyze, category)
    raw_response, success = await call_gemini(prompt)
    
    if success and raw_response:
        analyzed, remainder = parse_gemini_response(raw_response)
        if analyzed:
            for intel_item in analyzed:
                orig_idx = intel_item.get("id", 0)
                if 0 <= orig_idx < len(to_analyze):
                    orig = to_analyze[orig_idx]
                    intel_item["_source_title"] = orig.get("title", "")
                    intel_item["_source_link"] = orig.get("link", "")
                    intel_item["_source_src"] = orig.get("source", "?")
                    intel_item["_resonance"] = orig.get("resonance_count", 1)
            
            analyzed.sort(key=lambda x: x.get("overall_score", 0), reverse=True)
            return analyzed, "gemini"
    
    print("[Intel] Gemini failed/empty, using keyword-fallback engine...")
    fallback_items = _keyword_fallback(to_analyze)
    return fallback_items, "keyword"


async def run_intelligence_report(category: str = "tech", chat_id: str = None, bot_token: str = None) -> dict:
    from opennews_mcp.tools.aggregator_rss import aggregate_free_news
    
    target_category = category if category != "oracle" else "all"
    max_items = 20 if target_category == "all" else 15
    
    raw_result = await aggregate_free_news(
        None,
        max_items=max_items,
        send_to_telegram=False,
        category=target_category
    )
    
    items = raw_result.get("items", [])
    
    if not items:
        report = build_empty_intel_report(target_category)
        return {"report": report, "count": 0, "engine": "none"}
    
    analyzed_items, engine_type = await analyze_news(items, target_category)
    
    if not analyzed_items:
        report = build_empty_intel_report(target_category)
        return {"report": report, "count": 0, "engine": "none"}
    
    mode = "full" if category == "oracle" else "compact"
    report = format_intelligence_report(
        analyzed_items,
        len(items),
        target_category,
        mode=mode
    )
    
    return {
        "report": report,
        "count": len(analyzed_items),
        "engine": engine_type,
        "items": analyzed_items
    }


async def send_to_telegram(text: str, chat_id: str, token: str = None) -> bool:
    bot = token or os.environ.get("BOT_TOKEN_G") or os.environ.get("BOT_TOKEN_F") or ""
    if not bot or not chat_id:
        return False
    
    if len(text) > 4000:
        parts = []
        current = ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > 3900:
                parts.append(current)
                current = line + "\n"
            else:
                current += line + "\n"
        if current:
            parts.append(current)
    else:
        parts = [text]
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        for part in parts:
            try:
                await client.post(
                    f"https://api.telegram.org/bot{bot}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": part,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True
                    }
                )
            except Exception as e:
                print("[Telegram Send Error]: %s" % e)
                return False
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Intelligence Engine Test")
    parser.add_argument("--category", default="tech", help="News category to analyze")
    parser.add_argument("--send", action="store_true", help="Send to Telegram after analysis")
    args = parser.parse_args()
    
    async def test():
        print("=" * 60)
        print("  Intelligence Engine v2.2 Test")
        print("=" * 60)
        print("\n[Step 1] Fetching news: %s ..." % args.category)
        
        result = await run_intelligence_report(category=args.category)
        
        print("\n[Step 2] Analysis complete!")
        print("  Engine: %s" % result["engine"])
        print("  Items analyzed: %d" % result["count"])
        print("\n--- Report Preview ---")
        safe = result["report"].replace('\U0001f535', '[R]').replace('\U0001f4ca', '[chart]').replace('\U0001f514', '[bell]')
        try:
            print(safe[:2000])
        except UnicodeEncodeError:
            print(safe.encode('ascii', 'replace').decode('ascii')[:2000])
        
        if args.send:
            print("\n[Step 3] Sending to Telegram...")
            token = os.environ.get("BOT_TOKEN_G", "")
            chat_id = os.environ.get("CHAT_ID_G", "-1003590230315")
            sent = await send_to_telegram(result["report"], chat_id, token)
            print("  Result: %s" % ("Sent OK" if sent else "Failed"))
    
    asyncio.run(test())
