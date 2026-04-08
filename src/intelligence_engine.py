import asyncio
import os
import sys
import json
import re
import hashlib
import time
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

_response_cache: dict[str, dict] = {}
CACHE_TTL_SECONDS = 1800

USER_PROFILE = {
    "role": "AI编辑/科技媒体从业者",
    "interests": [
        "AI大模型进展 (GPT/Claude/Gemini/Llama/Qwen/DeepSeek)",
        "Agent/MCP协议生态",
        "开源模型与框架 (HuggingFace/LangChain/LlamaIndex)",
        "AI创业与投融资",
        "芯片/算力基础设施 (NVIDIA/TSMC/ASIC)",
        "AI安全与治理 (EU AI Act/中国AI法规)",
        "量化交易与AI结合",
        "具身智能与机器人"
    ],
    "context": "国内头部科技媒体公司，需要快速产出高质量AI领域新闻报道和深度分析。目标读者是AI从业者和科技爱好者。",
    "watchlist": [
        "OpenAI", "Anthropic", "Google DeepMind", "Meta AI", "Mistral AI",
        "NVIDIA", "AMD", "TSMC", "Intel",
        "Hugging Face", "LangChain", "LlamaIndex",
        "OpenAI GPT", "Claude", "Gemini", "Llama", "Qwen", "DeepSeek",
        "MCP协议", "Agent", "RAG", "Function Calling",
        "GPU", "TPU", "NPU", "算力", "推理优化",
        "EU AI Act", "AI安全", "对齐", "监管"
    ]
}

INTEL_SYSTEM_PROMPT = """你是 OpenNews Matrix 的情报分析引擎（Intelligence Engine v2.5）。

你的任务是将原始新闻转化为**中文结构化情报卡片**，供专业AI编辑使用。
所有输出必须使用**简体中文**。

## 分析框架：5W1H+I

| 维度 | 说明 | 输出要求 |
|------|------|---------|
| **WHO** | 关键实体（人物/机构/公司） | 1-2行，列出核心角色 |
| **WHAT** | 发生了什么 | 1-2句精炼中文描述 |
| **WHERE** | 地点/市场/领域 | 简短标注 |
| **WHEN** | 时间节点 | 相对时间（如"2小时前"） |
| **WHY** | 背景原因/深层动因 | 1-2句中文分析 |
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
  "what": "发布GPT-5预览版，支持实时联网和多模态理解",
  "where": "美国/全球AI市场",
  "when": "2026-04-08 (2小时前)",
  "why": "应对Anthropic Claude 4的竞争压力，同时满足企业级用户对多模态能力的需求",
  "how": "短期引发API价格战，长期推动多模态Agent普及，可能重塑AI应用开发范式",
  "implications": "对AI编辑而言：需关注API能力边界变化，可撰写对比评测和技术深度解析",
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
  "actionable": "建议今日跟进：测试GPT-5 API兼容性，准备技术对比稿"
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
请在 prominence 和 tier 中体现这一点。

## 特别注意：AI领域深度分析要求
对于以下类型的新闻，请进行更深入的分析：
- 大模型发布/更新：分析技术突破、与竞品对比、市场影响
- 融资/收购事件：分析资本流向、赛道格局变化、潜在影响
- 政策/法规：分析对不同市场参与者的影响、合规挑战
- 开源项目：分析社区反应、技术价值、商业潜力"""


def _build_user_profile_str() -> str:
    lines = ["**用户画像:**"]
    lines.append("- 角色: %s" % USER_PROFILE['role'])
    lines.append("- 关注领域:")
    for interest in USER_PROFILE["interests"]:
        lines.append("  * %s" % interest)
    lines.append("- 背景: %s" % USER_PROFILE['context'])
    if USER_PROFILE.get("watchlist"):
        lines.append("- 重点监控:")
        for w in USER_PROFILE["watchlist"][:20]:
            lines.append("  * %s" % w)
    return "\n".join(lines)


def _get_cache_key(prompt_text: str) -> str:
    content_hash = hashlib.md5(prompt_text.encode('utf-8')).hexdigest()[:12]
    return "intel_%s" % content_hash


def _check_cache(prompt_text: str) -> Optional[dict]:
    cache_key = _get_cache_key(prompt_text)
    if cache_key in _response_cache:
        cached = _response_cache[cache_key]
        if time.time() - cached.get("timestamp", 0) < CACHE_TTL_SECONDS:
            print("[Cache] HIT for prompt hash: %s" % cache_key[:16])
            return cached
    return None


def _store_in_cache(prompt_text: str, response: str, success: bool):
    cache_key = _get_cache_key(prompt_text)
    _response_cache[cache_key] = {
        "timestamp": time.time(),
        "response": response,
        "success": success
    }
    if len(_response_cache) > 50:
        oldest_key = min(_response_cache, key=lambda k: _response_cache[k]["timestamp"])
        del _response_cache[oldest_key]


def _build_analysis_prompt(items: list[dict], category: str) -> str:
    news_lines = []
    for i, item in enumerate(items[:15]):
        title = item.get("title", "")[:120]
        src = item.get("source", "?")
        res = item.get("resonance_count", 1)
        tim = item.get("_pre_timeliness", 0)
        pro = item.get("_pre_prominence", 0)
        news_lines.append(
            "[%d] [%s] (共振:%d T:%.0f P:%.0f) %s" % (i, src, res, tim, pro, title)
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
    prompt += "\n\n## 当前分类: %s" % category_names.get(category, category)
    prompt += "\n\n## 待分析新闻 (%d 条):\n\n" % len(items)
    prompt += "\n".join(news_lines)
    prompt += "\n\n请为每条新闻生成完整的5W1H+I情报卡片。返回JSON数组。只返回JSON，不要其他文字。"
    
    return prompt


async def call_gemini(prompt_text: str, max_retries: int = 3) -> tuple[str, bool]:
    if not GEMINI_KEY:
        print("[Intel] No GEMINI_API_KEY found.")
        return "", False
    
    cached = _check_cache(prompt_text)
    if cached:
        return cached["response"], cached["success"]
    
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 6000,
            "responseMimeType": "application/json"
        }
    }
    url = "%s?key=%s" % (GEMINI_URL, GEMINI_KEY)
    
    last_error = None
    for attempt in range(max_retries):
        try:
            wait_time = min(2 ** attempt * 2, 30)
            if attempt > 0:
                print("[Intel] Retry #%d after %ds..." % (attempt, wait_time))
                await asyncio.sleep(wait_time)
            
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(url, json=payload)
                
                if response.status_code == 200:
                    result = response.json()
                    text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                    print("[Intel] Gemini analysis complete (%d chars)" % len(text))
                    _store_in_cache(prompt_text, text, True)
                    return text, True
                    
                elif response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "")
                    wait_extra = int(retry_after) if retry_after.isdigit() else 10 + attempt * 5
                    print("[Intel] Rate limited (429), waiting %ds..." % wait_extra)
                    await asyncio.sleep(wait_extra)
                    last_error = "rate_limited"
                    continue
                    
                elif response.status_code == 500 or response.status_code == 503:
                    print("[Intel] Server error (%d), retrying..." % response.status_code)
                    last_error = "server_error_%d" % response.status_code
                    continue
                    
                else:
                    print("[Intel] Gemini error: %d" % response.status_code)
                    last_error = "http_%d" % response.status_code
                    break
                    
        except httpx.TimeoutException:
            print("[Intel] Timeout on attempt %d/%d" % (attempt + 1, max_retries))
            last_error = "timeout"
        except Exception as e:
            print("[Intel] Connection error: %s" % e)
            last_error = str(e)[:80]
    
    print("[Intel] All retries failed: %s" % (last_error or "unknown"))
    _store_in_cache(prompt_text, "", False)
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
            "keywords": ["openai", "gpt", "claude", "gemini", "llama", "model release", "benchmark", "sota", "deepseek", "qwen"],
            "who_tmpl": "{src}",
            "what_tmpl": "{title}",
            "why": "AI技术持续迭代，模型能力边界不断扩展，竞争加剧",
            "how": "可能影响现有AI应用架构和开发范式，推动新一轮创新周期",
            "implications": "作为AI编辑：需评估新技术对内容生产流程的影响，准备技术解读稿",
            "tags": ["AI大模型", "技术突破"],
            "actionable": "建议跟进：阅读原论文/官方博客，准备深度报道素材"
        },
        "chip_hardware": {
            "keywords": ["nvidia", "gpu", "tpu", "chip", "semiconductor", "tsmc", "data center", "compute", "amd", "intel", "asic", "推理加速"],
            "who_tmpl": "{src}",
            "what_tmpl": "{title}",
            "why": "算力基础设施是AI发展的物理瓶颈，硬件创新直接影响模型训练和部署成本",
            "how": "影响训练成本和推理延迟，进而影响AI产品化节奏和商业化可行性",
            "implications": "算力动态直接影响AI行业整体发展速度，需持续跟踪供应链变化",
            "tags": ["芯片硬件", "算力基础设施"],
            "actionable": "建议关注：供应链变化对AI初创公司的影响，整理算力趋势报告"
        },
        "startup_funding": {
            "keywords": ["funding", "series", "valuation", "ipo", "acquisition", "unicorn", "startup", "venture", "融资", "投资"],
            "who_tmpl": "{src}",
            "what_tmpl": "{title}",
            "why": "资本流向反映市场对未来方向的判断，AI赛道融资热度持续高涨",
            "how": "获投领域将加速发展，资源向头部集中，可能引发并购整合潮",
            "implications": "融资动向预示未来3-6个月的技术热点和市场格局变化",
            "tags": ["融资创投", "资本市场"],
            "actionable": "建议整理：更新赛道融资地图，分析资本流向背后的逻辑"
        },
        "policy_regulation": {
            "keywords": ["regulation", "act", "law", "policy", "government", "congress", "eu", "china", "ban", "restriction", "监管", "法案"],
            "who_tmpl": "{src}",
            "what_tmpl": "{title}",
            "why": "政策法规塑造AI产业格局，全球监管趋同与差异化并存",
            "how": "合规成本上升，可能重塑市场竞争态势，影响跨国AI企业的战略布局",
            "implications": "政策变化直接影响企业AI战略布局，需及时解读政策影响",
            "tags": ["政策监管", "合规"],
            "actionable": "建议解读：分析政策对不同市场参与者的影响，准备政策解读文章"
        },
        "agent_ecosystem": {
            "keywords": ["agent", "mcp", "tool use", "function calling", "rag", "autonomous", "workflow", "automation", "智能体"],
            "who_tmpl": "{src}",
            "what_tmpl": "{title}",
            "why": "Agent是AI从聊天工具进化为生产力工具的关键，MCP等协议正在标准化",
            "how": "MCP等协议标准化将降低Agent开发门槛，推动企业级AI应用落地",
            "implications": "Agent生态成熟度直接影响AI落地速度，是下一个重要增长点",
            "tags": ["Agent生态", "MCP协议"],
            "actionable": "建议测试：验证新工具/协议的实用性，准备Agent生态观察报告"
        },
        "opensource_ai": {
            "keywords": ["open source", "hugging face", "pytorch", "tensorflow", "langchain", "llamaindex", "开源", "权重发布", "model weights"],
            "who_tmpl": "{src}",
            "what_tmpl": "{title}",
            "why": "开源AI正在重塑行业格局，降低准入门槛，加速技术创新扩散",
            "how": "开源模型质量不断提升，缩小与闭源模型的差距，推动行业民主化",
            "implications": "开源动态值得关注，可能带来新的商业模式和应用场景",
            "tags": ["开源AI", "模型发布"],
            "actionable": "建议测试：评估新开源模型的实际性能，准备对比评测"
        },
        "ai_safety_alignment": {
            "keywords": ["safety", "alignment", "red team", "adversarial", "bias", "fairness", "ethics", "安全", "对齐", "伦理"],
            "who_tmpl": "{src}",
            "what_tmpl": "{title}",
            "why": "AI安全和对齐问题日益受到重视，成为技术发展的关键约束条件",
            "how": "安全研究将影响模型设计、训练方法和部署策略，形成新的技术分支",
            "implications": "安全议题将成为AI产品化的必要考量，需关注相关标准和最佳实践",
            "tags": ["AI安全", "对齐研究"],
            "actionable": "建议关注：跟踪安全研究进展，准备AI安全专题内容"
        }
    }
    
    fallback_items = []
    now = datetime.now(timezone.utc)
    
    for idx, item in enumerate(items):
        title_lower = item.get("title", "").lower()
        summary_lower = item.get("summary", "").lower()
        combined_text = "%s %s" % (title_lower, summary_lower)
        
        matched_trigger = None
        match_score = 0
        
        for cat, info in triggers.items():
            score = sum(1 for kw in info["keywords"] if kw in combined_text)
            if score > match_score:
                match_score = score
                matched_trigger = info
        
        if not matched_trigger or match_score == 0:
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
        if match_score >= 3:
            base_score += 0.5
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
                "prominence": round(prominence, 1),
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
    
    is_watchlist = any(
        w.lower() in who.lower() or w.lower() in what.lower()
        for w in USER_PROFILE.get("watchlist", [])[:10]
    )
    watch_tag = " ⭐" if is_watchlist else ""
    
    lines = []
    lines.append("%s **[%d] %s**%s%s" % (icon, index, who, res_tag, watch_tag))
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
        lines.append("[%s](%s)" % ("原文", source_link))
    
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
    
    watchlist_count = sum(1 for it in analyzed_items if any(
        w.lower() in str(it.get("who", "")).lower() or w.lower() in str(it.get("what", "")).lower()
        for w in USER_PROFILE.get("watchlist", [])[:10]
    ))
    
    header = (
        "**OpenNews Intelligence Report v2.5**\n"
        "| %s | `%s` | 原始: %d 条 -> 分析: %d 条 |\n"
        "Engine: `%s`" % (cat_name, now_str, raw_count, len(analyzed_items), ai_mode)
    )
    if watchlist_count > 0:
        header += " | ⭐ 关注匹配: %d" % watchlist_count
    
    sections = []
    
    if critical:
        sections.append("\n**━━ CRITICAL 一级警报 ━━**\n")
        for i, it in enumerate(critical[:3]):
            sections.append(format_intelligence_card(it, i+1) + "\n")
    
    if high:
        sections.append("\n**━━ HIGH 高优先 ━━**\n")
        for i, it in enumerate(high[:5]):
            sections.append(format_intelligence_card(it, i+1) + "\n")
    
    if trending and mode == "full":
        sections.append("\n**━━ TRENDING 趋势跟踪 ━━**\n")
        for i, it in enumerate(trending[:4]):
            score = it.get("overall_score", 0)
            what = it.get("what", "")[:100]
            tags = it.get("tags", [])
            tag_str = " ".join("#%s" % t for t in tags[:3]) if tags else ""
            sections.append("~ *[%0.1f]* %s %s\n" % (score, what, tag_str))
    
    footer = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "OpenNews Matrix v2.5 | RSS + Gemini"
    )
    
    return header + "".join(sections) + footer


def build_empty_intel_report(category: str) -> str:
    now_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    category_names = {
        "tech": "AI/科技", "finance": "金融", "world": "全球",
        "military": "军事", "politics": "政治", "all": "全领域"
    }
    
    return (
        "**Intelligence Report -- %s**\n\n"
        "%s 分类当前无重大情报信号。\n\n"
        "**系统状态:** 在线\n"
        "**扫描源数:** 55+ 个\n"
        "**最后扫描:** %s\n\n"
        "*后台监控持续运行，检测到重大事件时自动推送。*\n\n"
        "输入 `/new` 查看全领域最新动态"
        % (now_str, category_names.get(category, category), now_str)
    )


async def analyze_news(items: list[dict], category: str = "tech", max_analyze: int = 12) -> tuple[list[dict], str]:
    if not items:
        return [], "no_items"
    
    try:
        from opennews_mcp.tools.aggregator_rss import _parse_time
        for item in items:
            raw_time = item.get("time")
            if isinstance(raw_time, str):
                try:
                    item["time"] = _parse_time(raw_time)
                except Exception:
                    pass
    except ImportError:
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
    try:
        from opennews_mcp.tools.aggregator_rss import aggregate_free_news
    except ImportError:
        from src.opennews_mcp.tools.aggregator_rss import aggregate_free_news
    
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
    
    return {"report": report, "count": len(analyzed_items), "engine": engine_type}


async def send_to_telegram(message: str, chat_id: str = None, bot_token: str = None) -> bool:
    target_chat = chat_id or os.environ.get("CHAT_ID_G", "-1003590230315")
    token = bot_token or os.environ.get("BOT_TOKEN_G") or os.environ.get("TECHBOTTOKEN")
    
    if not token:
        print("[Send] No bot token available")
        return False
    
    url = "https://api.telegram.org/bot%s/sendMessage" % token
    
    chunks = []
    current_chunk = ""
    for line in message.split('\n'):
        if len(current_chunk) + len(line) + 1 > 4000:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = line + '\n'
        else:
            current_chunk += line + '\n'
    if current_chunk.strip():
        chunks.append(current_chunk.strip)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for chunk in chunks:
            payload = {
                "chat_id": target_chat,
                "text": chunk,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }
            try:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    plain_payload = payload.copy()
                    plain_payload["parse_mode"] = None
                    resp = await client.post(url, json=plain_payload)
            except Exception as e:
                print("[Send] Error: %s" % e)
                return False
    
    return True