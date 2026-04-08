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
from enum import Enum
from dataclasses import dataclass, field, asdict
from collections import defaultdict

import httpx

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from opennews_mcp.tools.aggregator_rss import aggregate as rss_aggregate
except ImportError:
    try:
        from aggregator_rss import aggregate_free_news as rss_aggregate
    except ImportError:
        from src.opennews_mcp.tools.aggregator_rss import aggregate_free_news as rss_aggregate


class SignalType(Enum):
    MODEL_BREAKTHROUGH = "model_breakthrough"
    ARCHITECTURE_INNOVATION = "architecture_innovation"
    PRACTICAL_TOOLCHAIN = "practical_toolchain"
    INDUSTRY_MILESTONE = "industry_milestone"
    FUNDING_ACQUISITION = "funding_acquisition"
    POLICY_REGULATION = "policy_regulation"
    WRAPPER_PROJECT = "wrapper_project"
    REINVENTION = "reinvention"
    MARKETING_HYPE = "marketing_hype"
    NOISE = "noise"


class ContentTier(Enum):
    GOLD = "gold"      # 核心突破/原创架构
    SILVER = "silver"  # 实用工具链/行业里程碑
    BRONZE = "bronze"  # 一般资讯
    FILTER = "filter"  # 过滤掉的内容


@dataclass
class NoisePattern:
    pattern: re.Pattern
    signal_type: SignalType
    confidence: float
    reason: str


@dataclass 
class CuratedItem:
    id: str = ""
    title: str = ""
    summary: str = ""
    source: str = ""
    link: str = ""
    published_at: str = ""
    
    signal_type: SignalType = SignalType.NOISE
    content_tier: ContentTier = ContentTier.FILTER
    
    who: str = ""
    what: str = ""
    where: str = ""
    when: str = ""
    why: str = ""
    how: str = ""
    implications: str = ""
    
    scores: dict = field(default_factory=dict)
    overall_score: float = 0.0
    tier: str = "NOISE"
    
    tags: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    
    core_highlight: str = ""
    industry_impact: str = ""
    comparison_context: str = ""
    
    fact_checks: list[dict] = field(default_factory=list)
    source_chain: list[str] = field(default_factory=list)
    
    actionable_for_editor: str = ""
    draft_angles: list[str] = field(default_factory=list)
    
    is_wrapper: bool = False
    is_reinvention: bool = False
    noise_reasons: list[str] = field(default_factory=list)


NOISE_PATTERNS = [
    NoisePattern(
        pattern=re.compile(r"(?i)(chatgpt.*wrapper|openai.*api.*wrapper|gpt.*ui.*wrapper|ai.*chatbot.*template)"),
        signal_type=SignalType.WRAPPER_PROJECT,
        confidence=0.9,
        reason="套壳ChatGPT UI项目"
    ),
    NoisePattern(
        pattern=re.compile(r"(?i)(another.*ai.*tool|yet.*another|just.*another|simple.*ai.*chat|basic.*llm.*app)"),
        signal_type=SignalType.WRAPPER_PROJECT,
        confidence=0.75,
        reason="重复造轮子的基础项目"
    ),
    NoisePattern(
        pattern=re.compile(r"(?i)(launching.*today|introducing.*my|proud.*announce.*mvp|built.*weekend|hackathon.*project)"),
        signal_type=SignalType.MARKETING_HYPE,
        confidence=0.7,
        reason="个人MVP/黑客松项目，缺乏深度"
    ),
    NoisePattern(
        pattern=re.compile(r"(?i)(revolutionary.*ai|game.changer|world.first|breakthrough.*ai.*tool|paradigm.shift)"),
        signal_type=SignalType.MARKETING_HYPE,
        confidence=0.65,
        reason="过度营销用语，需验证实际价值"
    ),
    NoisePattern(
        pattern=re.compile(r"(?i)(top.*10.*ai|best.*ai.*tools.*202[56]|must.have.*ai|ultimate.*guide.*ai)"),
        signal_type=SignalType.MARKETING_HYPE,
        confidence=0.8,
        reason="清单体/SEO内容，非一手信息"
    ),
]

SIGNAL_PATTERNS = [
    NoisePattern(
        pattern=re.compile(r"(?i)(new.*architecture|novel.*approach|first.*of.*its.kind|state.of.the.art.*result|sota.*benchmark)"),
        signal_type=SignalType.ARCHITECTURE_INNOVATION,
        confidence=0.85,
        reason="架构创新信号"
    ),
    NoisePattern(
        pattern=re.compile(r"(?i)(gpt.*5|claude.*4|gemini.*2.*pro|llama.*4|new.*foundation.model|parameter.*trillion)"),
        signal_type=SignalType.MODEL_BREAKTHROUGH,
        confidence=0.9,
        reason="核心模型发布信号"
    ),
    NoisePattern(
        pattern=re.compile(r"(?i)(series.[bcd]|funding.*round|acquired.*by|valuation.*billion|unicorn)"),
        signal_type=SignalType.FUNDING_ACQUISITION,
        confidence=0.88,
        reason="融资/并购信号"
    ),
    NoisePattern(
        pattern=re.compile(r"(?i)(eu.*ai.*act|china.*ai.*regulation|executive.order.*ai|ai.*safety.*bill)"),
        signal_type=SignalType.POLICY_REGULATION,
        confidence=0.92,
        reason="政策法规信号"
    ),
    NoisePattern(
        pattern=re.compile(r"(?i)(open.source.*release|production.ready|enterprise.grade|integration.*with)"),
        signal_type=SignalType.PRACTICAL_TOOLCHAIN,
        confidence=0.78,
        reason="实用工具链信号"
    ),
]

SOURCE_AUTHORITY = {
    "tier_1_official": {
        "sources": ["openai.com", "blog.google", "deepmind.google", "anthropic.com", "meta.ai", "ai.meta.com"],
        "weight": 1.0,
        "label": "官方一手信源",
        "bonus": 1.5
    },
    "tier_1_research": {
        "sources": ["arxiv.org", "arxiv.org/abs", "bair.berkeley.edu", "intelligence.org"],
        "weight": 0.95,
        "label": "学术一手信源",
        "bonus": 1.2
    },
    "tier_2_media": {
        "sources": ["technologyreview.com", "wired.com", "theverge.com", "arstechnica.com", "venturebeat.com", "techcrunch.com", "the-decoder.com"],
        "weight": 0.85,
        "label": "权威科技媒体",
        "bonus": 0.8
    },
    "tier_2_cloud": {
        "sources": ["cloud.google.com", "aws.amazon.com", "azure.microsoft.com", "huggingface.co/blog"],
        "weight": 0.88,
        "label": "云厂商技术博客",
        "bonus": 0.9
    },
    "tier_3_aggregator": {
        "sources": ["bensbites.com", "producthunt.com", "news.ycombinator.com", "reddit.com"],
        "weight": 0.6,
        "label": "聚合站/社区",
        "bonus": 0.0
    },
    "tier_4_unknown": {
        "sources": [],
        "weight": 0.5,
        "label": "未知来源",
        "bonus": -0.3
    }
}

ENTITY_KEYWORDS = {
    "OpenAI": ["openai", "gpt", "chatgpt", "sora", "dall-e", "sam altman", "oai"],
    "Anthropic": ["anthropic", "claude", "dario amodei", "constitutional ai"],
    "Google DeepMind": ["deepmind", "google ai", "gemini", "alphafold", "demis hassabis", "sundar pichai"],
    "Meta AI": ["meta ai", "llama", "pytorch", "yann lecun", "mark zuckerberg", "facebook ai"],
    "NVIDIA": ["nvidia", "cuda", "gpu", "jensen huang", "blackwell", "hopper", "dgx"],
    "Hugging Face": ["hugging face", "transformers", "hf.co", "diffusers", "clement delangue"],
    "Mistral": ["mistral", "mistral ai", "arthur Mensch"],
    "Cohere": ["cohere", "command r", "embed", "aidan gomez"],
    "xAI": ["xai", "grok", "elon musk"],
    "Apple Intelligence": ["apple intelligence", "mlx", "ferret-ui", "tim cook"],
}

def get_source_tier(source_url: str, source_name: str = "") -> dict:
    combined = "%s %s" % (source_url.lower(), source_name.lower())
    
    for tier_name, tier_info in SOURCE_AUTHORITY.items():
        for domain in tier_info["sources"]:
            if domain in combined:
                return {**tier_info, "name": tier_name}
    
    return {**SOURCE_AUTHORITY["tier_4_unknown"], "name": "tier_4_unknown"}

def extract_entities(text: str) -> list[str]:
    text_lower = text.lower()
    found_entities = []
    
    for entity_name, keywords in ENTITY_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                found_entities.append(entity_name)
                break
    
    return list(set(found_entities))

def calculate_hotspot_burst(items: list[dict], current_item: dict, time_window_hours: float = 6.0) -> dict:
    now = datetime.now(timezone(timedelta(hours=8)))
    window_start = now - timedelta(hours=time_window_hours)
    
    current_title = current_item.get("title", "").lower()
    current_summary = (current_item.get("summary", "") or "").lower()[:200]
    current_entities = extract_entities("%s %s" % (current_title, current_summary))
    
    related_items = []
    source_domains = set()
    
    for item in items:
        if item.get("link") == current_item.get("link"):
            continue
        
        item_title = item.get("title", "").lower() or ""
        item_summary = (item.get("summary", "") or "").lower()[:200]
        item_time_str = item.get("time")
        
        try:
            if isinstance(item_time_str, str):
                item_time = datetime.fromisoformat(item_time_str.replace("Z", "+00:00"))
            else:
                continue
            
            if item_time < window_start:
                continue
                
        except:
            continue
        
        item_entities = extract_entities("%s %s" % (item_title, item_summary))
        
        shared_entities = set(current_entities) & set(item_entities)
        
        if len(shared_entities) >= 1 and (current_entities or item_entities):
            jaccard = len(shared_entities) / max(len(set(current_entities) | set(item_entities)), 1)
            
            title_words = set(current_title.split()) & set(item_title.split())
            title_overlap = len(title_words) / max(len(set(current_title.split()) | set(item_title.split())), 1)
            
            combined_score = (jaccard * 0.7 + title_overlap * 0.3)
            
            if combined_score > 0.15:
                source_domain = ""
                link = item.get("source", "") or item.get("link", "") or ""
                for part in link.split("/")[2:3]:
                    source_domain = part
                    break
                source_domains.add(source_domain)
                
                related_items.append({
                    "score": combined_score,
                    "source": item.get("source", ""),
                    "time_diff_hours": (now - item_time).total_seconds() / 3600,
                    "entities": list(shared_entities)
                })
    
    related_items.sort(key=lambda x: x["score"], reverse=True)
    
    burst_score = min(len(source_domains) * 0.8 + len(related_items) * 0.15, 5.0)
    
    is_bursting = len(source_domains) >= 3 or (len(related_items) >= 5 and burst_score >= 2.5)
    
    avg_time_diff = sum(r["time_diff_hours"] for r in related_items) / max(len(related_items), 1)
    
    return {
        "burst_score": round(burst_score, 2),
        "is_bursting": is_bursting,
        "related_count": len(related_items),
        "unique_sources": len(source_domains),
        "avg_time_diff_hours": round(avg_time_diff, 1),
        "top_related": related_items[:3],
        "entities_detected": current_entities,
        "hotspot_level": "EXPLODING" if is_bursting and len(source_domains) >= 5 else 
                         "VIRAL" if is_bursting and len(source_domains) >= 3 else
                         "TRENDING" if burst_score >= 1.5 else
                         "NORMAL"
    }


def _generate_id(title: str, source: str) -> str:
    raw = "%s|%s|%s" % (title, source, datetime.now().strftime("%Y%m%d"))
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def detect_signal_type(item: dict) -> tuple[SignalType, float, list[str]]:
    title = item.get("title", "")
    summary = item.get("summary", "")
    combined = "%s %s" % (title, summary)
    
    signals = []
    noise_reasons = []
    
    for p in NOISE_PATTERNS:
        if p.pattern.search(combined):
            if p.signal_type in [SignalType.WRAPPER_PROJECT, SignalType.MARKETING_HYPE, SignalType.NOISE]:
                noise_reasons.append(p.reason)
                signals.append((p.signal_type, p.confidence, p.reason))
    
    for p in SIGNAL_PATTERNS:
        if p.pattern.search(combined):
            signals.append((p.signal_type, p.confidence, p.reason))
    
    if not signals:
        signals.append((SignalType.NOISE, 0.5, "未识别到明确信号"))
    
    signals.sort(key=lambda x: x[1], reverse=True)
    best_signal = signals[0]
    
    return best_signal[0], best_signal[1], noise_reasons


def calculate_content_tier(signal_type: SignalType, confidence: float, 
                          resonance_count: int, source_quality: int,
                          hotspot_info: dict = None, source_authority: dict = None) -> tuple[ContentTier, float]:
    
    tier_scores = {
        SignalType.MODEL_BREAKTHROUGH: 9.0,
        SignalType.ARCHITECTURE_INNOVATION: 8.5,
        SignalType.POLICY_REGULATION: 8.0,
        SignalType.FUNDING_ACQUISITION: 7.5,
        SignalType.INDUSTRY_MILESTONE: 7.0,
        SignalType.PRACTICAL_TOOLCHAIN: 6.5,
        SignalType.MARKETING_HYPE: 4.0,
        SignalType.WRAPPER_PROJECT: 2.0,
        SignalType.REINVENTION: 2.5,
        SignalType.NOISE: 3.0,
    }
    
    base_score = tier_scores.get(signal_type, 3.0)
    
    resonance_bonus = min(resonance_count * 0.5, 2.0)
    source_bonus = source_quality * 0.3
    confidence_adj = (confidence - 0.5) * 2
    
    authority_bonus = 0.0
    if source_authority:
        authority_bonus = source_authority.get("bonus", 0.0) * 0.4
    
    hotspot_boost = 0.0
    if hotspot_info:
        burst_score = hotspot_info.get("burst_score", 0)
        is_bursting = hotspot_info.get("is_bursting", False)
        
        if is_bursting and base_score >= 6.0:
            hotspot_boost = min(burst_score * 0.3, 1.5)
        elif burst_score >= 1.5 and base_score >= 5.0:
            hotspot_boost = burst_score * 0.15
    
    final_score = base_score + resonance_bonus + source_bonus + confidence_adj + authority_bonus + hotspot_boost
    final_score = max(0.0, min(10.0, final_score))
    
    if final_score >= 7.5:
        tier = ContentTier.GOLD
    elif final_score >= 5.5:
        tier = ContentTier.SILVER
    elif final_score >= 3.5:
        tier = ContentTier.BRONZE
    else:
        tier = ContentTier.FILTER
    
    return tier, final_score


GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

if not GEMINI_KEY:
    try:
        key_file = project_root / ".env"
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

EDITOR_PROFILE = {
    "role": "AI科技媒体编辑",
    "focus_areas": ["大语言模型", "AI基础设施", "开源生态", "AI政策监管", "芯片算力"],
    "content_types": ["深度报道", "技术解析", "行业观察", "产品评测", "专访"],
    "audience": "科技从业者、开发者、投资人、政策制定者",
    "style_guide": {
        "tone": "专业但不晦涩，有观点但不偏激",
        "structure": "背景-现状-分析-影响-展望",
        "requirements": ["数据支撑", "多方信源", "避免营销话术", "提供独特视角"]
    },
    "watchlist": [
        {"entity": "OpenAI", "type": "公司", "priority": "critical"},
        {"entity": "Anthropic", "type": "公司", "priority": "high"},
        {"entity": "Google DeepMind", "type": "公司", "priority": "high"},
        {"entity": "Meta AI", "type": "公司", "priority": "medium"},
        {"entity": "NVIDIA", "type": "公司", "priority": "critical"},
        {"entity": "Hugging Face", "type": "公司", "priority": "medium"},
        {"entity": "GPT-5/Claude 4/Gemini 2", "type": "产品线", "priority": "critical"},
        {"entity": "Llama/Qwen/Mistral", "type": "开源模型", "priority": "high"},
        {"entity": "EU AI Act/中国AI监管", "type": "政策", "priority": "high"},
    ]
}


async def call_gemini_editor(prompt_text: str, max_retries: int = 3) -> tuple[str, bool]:
    if not GEMINI_KEY:
        print("[Editor] No GEMINI_API_KEY found.")
        return "", False
    
    cached = _check_cache(prompt_text)
    if cached:
        return cached["response"], cached["success"]
    
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "temperature": 0.25,
            "maxOutputTokens": 8000,
            "responseMimeType": "application/json"
        }
    }
    url = "%s?key=%s" % (GEMINI_URL, GEMINI_KEY)
    
    last_error = None
    for attempt in range(max_retries):
        try:
            wait_time = min(2 ** attempt * 2, 30)
            if attempt > 0:
                print("[Editor] Retry #%d after %ds..." % (attempt, wait_time))
                await asyncio.sleep(wait_time)
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, json=payload)
                
                if response.status_code == 200:
                    result = response.json()
                    text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                    print("[Editor] Gemini analysis complete (%d chars)" % len(text))
                    _store_in_cache(prompt_text, text, True)
                    return text, True
                    
                elif response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "")
                    wait_extra = int(retry_after) if retry_after.isdigit() else 10 + attempt * 5
                    print("[Editor] Rate limited (429), waiting %ds..." % wait_extra)
                    await asyncio.sleep(wait_extra)
                    last_error = "rate_limited"
                    continue
                    
                elif response.status_code in [500, 503]:
                    print("[Editor] Server error (%d), retrying..." % response.status_code)
                    last_error = "server_error_%d" % response.status_code
                    continue
                    
                else:
                    print("[Editor] Gemini error: %d" % response.status_code)
                    last_error = "http_%d" % response.status_code
                    break
                    
        except httpx.TimeoutException:
            print("[Editor] Timeout on attempt %d/%d" % (attempt + 1, max_retries))
            last_error = "timeout"
        except Exception as e:
            print("[Editor] Connection error: %s" % e)
            last_error = str(e)[:80]
    
    print("[Editor] All retries failed: %s" % (last_error or "unknown"))
    _store_in_cache(prompt_text, "", False)
    return "", False


def _check_cache(prompt: str) -> Optional[dict]:
    key = hashlib.md5(prompt.encode()).hexdigest()[:16]
    cached = _response_cache.get(key)
    if cached and time.time() - cached["timestamp"] < CACHE_TTL_SECONDS:
        return cached
    return None

def _store_in_cache(prompt: str, response: str, success: bool):
    key = hashlib.md5(prompt.encode()).hexdigest()[:16]
    _response_cache[key] = {
        "response": response,
        "success": success,
        "timestamp": time.time()
    }


def _build_editor_profile_str() -> str:
    watchlist_str = "\n".join([
        "    - ⭐%s [%s/%s]" % (w["entity"], w["type"], w["priority"])
        for w in EDITOR_PROFILE["watchlist"]
    ])
    
    return json.dumps(EDITOR_PROFILE, ensure_ascii=False, indent=2)


EDITOR_SYSTEM_PROMPT = """# OpenNews Editor Assistant v3.0 - 专业编辑分析引擎

## 角色定位
你是一位资深AI科技媒体编辑的智能助手。你的任务不是简单翻译新闻，而是为专业编辑提供**可直接用于写稿的结构化素材**。

## 用户画像
{user_profile_str}

## 核心能力要求

### 1. 深度降噪与信号识别
对每条新闻进行严格评估：
- **过滤对象**: 套壳UI项目、重复造轮子、纯营销MVP、SEO清单体
- **保留标准**: 原创架构突破、核心模型更新、重要融资并购、政策变化、实用工具链

### 2. 关联上下文分析
每条新闻必须包含：
- **核心亮点** (core_highlight): 一句话概括为什么这件事值得写
- **行业影响预测** (industry_impact): 对产业链各环节的影响（短期3个月/中期1年）
- **对比上下文** (comparison_context): 与现有主流方案的差异点

### 3. 写稿辅助
为编辑提供：
- **可操作建议** (actionable_for_editor): 下一步该做什么（测试API？联系PR？找专家评论？）
- **写稿角度** (draft_angles): 至少3个不同的切入角度（技术向/商业向/政策向）

### 4. 事实核查标记
对以下硬指标进行标注：
- 参数量、训练数据规模 → 标注[待验证]
- 性能基准分数 → 标注[官方数据]/[第三方验证]
- 融资金额 → 标注[官宣]/[传闻]
- 开源协议 → 明确标注具体协议

### 5. 内容分层标签
自动打标签：
- **技术层**: model_layer / infrastructure_layer / application_layer / toolchain
- **领域**: llm / multimodal / robotics / chip / policy / open_source
- **时效**: breaking / developing / ongoing / archived

## 输出格式

严格返回 JSON 数组：

```json
[{{
  "id": "abc123",
  "signal_type": "model_breakthrough",
  "content_tier": "gold",
  
  "who": "OpenAI团队",
  "what": "发布GPT-5预览版",
  "where": "美国旧金山",
  "when": "2026-04-08T10:00:00Z",
  "why": "应对竞争压力+满足企业需求",
  "how": "采用全新MoE架构，支持100万token上下文",
  "implications": "重塑AI应用开发范式，API价格战一触即发",
  
  "scores": {{
    "timeliness": 9.0,
    "importance": 9.0,
    "proximity": 9.0,
    "prominence": 8.0,
    "anomaly": 7.0
  }},
  "overall_score": 8.4,
  "tier": "CRITICAL",
  
  "tags": ["GPT-5", "OpenAI", "MoE", "百万上下文"],
  "categories": ["model_layer", "llm", "breaking"],
  
  "core_highlight": "首个支持百万级上下文的商业大模型，推理成本降低60%",
  "industry_impact": "短期：API定价体系重构；中期：企业级AI应用门槛大幅降低；长期：可能引发新一轮模型军备竞赛",
  "comparison_context": "vs GPT-4o：上下文提升20倍，推理速度提升3倍；vs Claude 4：多模态能力持平但价格更低",
  
  "fact_checks": [
    {{"claim": "100万token上下文", "status": "[官方数据]", "confidence": 0.95}},
    {{"claim": "推理成本降低60%", "status": "[待验证]", "confidence": 0.6}}
  ],
  "source_chain": ["OpenAI官方博客", "TechCrunch原始报道", "The Verge独立验证"],
  
  "actionable_for_editor": "建议立即申请API访问权限，准备对比评测稿，联系OpenAI PR获取技术细节",
  "draft_angles": [
    "技术向：GPT-5 MoE架构深度解析与技术评测",
    "商业向：百万上下文如何改变企业AI应用格局",
    "行业向：2026年大模型竞争格局重塑：OpenAI vs Anthropic vs Google"
  ],
  
  "is_wrapper": false,
  "is_reinvention": false,
  "noise_reasons": [],
  
  "editor_note": "这是本周最重要的AI新闻，建议作为头版头条，可配发深度技术解析"
}}]
```

## 分级标准
- **GOLD (overall >= 7.5)**: 头版素材，值得深度报道
- **SILVER (5.5-7.4)**: 重要资讯，适合简报或专题
- **BRONZE (3.5-5.4)**: 一般动态，可作为背景资料
- **FILTER (< 3.5)**: 噪音，直接丢弃

## 特别注意
1. 如果是套壳项目或重复造轮子，必须在 noise_reasons 中说明原因
2. 所有行业影响预测要有逻辑依据，不能空泛
3. 写稿角度要具体可执行，不能是"值得关注"这种废话
4. 事实核查要诚实标注不确定的信息
"""


def _build_analysis_prompt(items: list[dict], category: str = "tech") -> str:
    items_json = json.dumps(items, ensure_ascii=False, indent=2)
    
    prompt = EDITOR_SYSTEM_PROMPT.format(user_profile_str=_build_editor_profile_str())
    
    prompt += """

## 待分析新闻列表（共%d条）

%s

## 分析要求
请以上述格式返回完整的JSON数组，对所有新闻进行深度编辑分析。
重点关注：
1. 识别并过滤低价值内容（套壳/营销/重复）
2. 为高价值内容生成完整的编辑素材包
3. 提供具体的写稿角度和行动建议

""" % (len(items), items_json)
    
    return prompt


async def deep_curate(items: list[dict]) -> list[CuratedItem]:
    curated = []
    
    print("[DeepCuration] Starting v2.0 with hotspot detection + source authority...")
    
    for idx, item in enumerate(items):
        curated_item = CuratedItem()
        curated_item.id = _generate_id(item.get("title", ""), item.get("source", ""))
        curated_item.title = item.get("title", "")
        curated_item.summary = item.get("summary", "")[:300]
        curated_item.source = item.get("source", "")
        curated_item.link = item.get("link", "")
        
        pub_time = item.get("time")
        if pub_time:
            if isinstance(pub_time, str):
                curated_item.published_at = pub_time
            else:
                try:
                    curated_item.published_at = pub_time.isoformat()
                except:
                    curated_item.published_at = datetime.now(timezone(timedelta(hours=8))).isoformat()
        else:
            curated_item.published_at = datetime.now(timezone(timedelta(hours=8))).isoformat()
        
        signal_type, confidence, noise_reasons = detect_signal_type(item)
        curated_item.signal_type = signal_type
        curated_item.is_wrapper = signal_type == SignalType.WRAPPER_PROJECT
        curated_item.is_reinvention = signal_type == SignalType.REINVENTION
        curated_item.noise_reasons = noise_reasons
        
        source_url = item.get("link") or item.get("source") or ""
        source_name = item.get("source") or ""
        source_authority = get_source_tier(source_url, source_name)
        
        hotspot_info = calculate_hotspot_burst(items, item)
        
        resonance_count = item.get("resonance_count", 1) + hotspot_info.get("unique_sources", 0)
        
        source_rank = item.get("rank", 5)
        source_quality = max(1, int(source_authority.get("weight", 0.5) * 6))
        
        content_tier, score = calculate_content_tier(
            signal_type, confidence, resonance_count, source_quality,
            hotspot_info=hotspot_info, source_authority=source_authority
        )
        curated_item.content_tier = content_tier
        curated_item.overall_score = round(score, 2)
        
        if hotspot_info["is_bursting"] and score >= 7.0:
            curated_item.tier = "CRITICAL"
        elif score >= 8.0 or (hotspot_info["is_bursting"] and score >= 6.5):
            curated_item.tier = "HIGH"
        elif score >= 6.0 or hotspot_info["burst_score"] >= 2.0:
            curated_item.tier = "TRENDING"
        elif score >= 4.0:
            curated_item.tier = "NORMAL"
        else:
            curated_item.tier = "NOISE"
        
        entities = extract_entities("%s %s" % (curated_item.title, curated_item.summary))
        curated_item.tags.extend(entities)
        
        if hotspot_info.get("is_bursting"):
            curated_item.tags.append("[HOTSPOT:%s]" % hotspot_info["hotspot_level"])
        
        if source_authority.get("name", "").startswith("tier_1"):
            curated_item.tags.append("[OFFICIAL_SOURCE]")
        
        curated_item.scores = {
            "base": round(score - resonance_count * 0.5 - source_quality * 0.3, 2),
            "resonance_bonus": round(min(resonance_count * 0.5, 2.0), 2),
            "source_quality": round(source_quality * 0.3, 2),
            "authority_bonus": round(source_authority.get("bonus", 0) * 0.4, 2),
            "hotspot_boost": round(
                min(hotspot_info.get("burst_score", 0) * 0.3, 1.5) if hotspot_info.get("is_bursting") 
                else hotspot_info.get("burst_score", 0) * 0.15 if hotspot_info.get("burst_score", 0) >= 1.5
                else 0, 2),
            "final": round(score, 2)
        }
        
        curated.append(curated_item)
    
    curated.sort(key=lambda x: (x.overall_score, len(x.tags)), reverse=True)
    
    burst_items = [c for c in curated if c.tier in ["CRITICAL", "HIGH"]]
    normal_items = [c for c in curated if c.tier not in ["CRITICAL", "HIGH"]]
    
    curated = burst_items + normal_items
    
    tier_counts = {t.value: sum(1 for c in curated if c.content_tier.value == t.value) for t in ContentTier}
    burst_count = sum(1 for c in curated if "[HOTSPOT:" in str(c.tags))
    
    print("[DeepCuration] v2.0 Complete: %d items processed" % len(curated))
    print("  Tiers: GOLD=%d SILVER=%d BRONZE=%d FILTER=%d" % (
        tier_counts.get("gold", 0), tier_counts.get("silver", 0),
        tier_counts.get("bronze", 0), tier_counts.get("filter", 0)
    ))
    print("  Hotspots detected: %d items" % burst_count)
    
    return curated


async def gemini_deep_analyze(curated_items: list[CuratedItem]) -> list[CuratedItem]:
    high_value_items = [item for item in curated_items if item.content_tier in [ContentTier.GOLD, ContentTier.SILVER]]
    
    if not high_value_items:
        print("[Editor] No high-value items for deep analysis")
        return curated_items
    
    items_for_analysis = [
        {
            "title": item.title,
            "summary": item.summary,
            "source": item.source,
            "link": item.link,
            "resonance_count": 1,
            "signal_type": item.signal_type.value,
            "initial_tier": item.content_tier.value,
            "initial_score": item.overall_score
        }
        for item in high_value_items[:8]
    ]
    
    prompt = _build_analysis_prompt(items_for_analysis, "editor")
    
    raw_response, success = await call_gemini_editor(prompt)
    
    if success and raw_response:
        try:
            json_match = re.search(r'\[.*\]', raw_response, re.DOTALL)
            if json_match:
                analyzed = json.loads(json_match.group())
                
                analyzed_map = {a.get("id", ""): a for a in analyzed}
                
                for item in curated_items:
                    if item.id in analyzed_map:
                        a = analyzed_map[item.id]
                        
                        item.who = a.get("who", item.who)
                        item.what = a.get("what", item.what)
                        item.where = a.get("where", item.where)
                        item.when = a.get("when", item.when)
                        item.why = a.get("why", item.why)
                        item.how = a.get("how", item.how)
                        item.implications = a.get("implications", item.implications)
                        
                        item.scores = a.get("scores", item.scores)
                        item.overall_score = a.get("overall_score", item.overall_score)
                        item.tier = a.get("tier", item.tier)
                        
                        item.tags = a.get("tags", item.tags)
                        item.categories = a.get("categories", item.categories)
                        
                        item.core_highlight = a.get("core_highlight", "")
                        item.industry_impact = a.get("industry_impact", "")
                        item.comparison_context = a.get("comparison_context", "")
                        
                        item.fact_checks = a.get("fact_checks", [])
                        item.source_chain = a.get("source_chain", [])
                        
                        item.actionable_for_editor = a.get("actionable_for_editor", "")
                        item.draft_angles = a.get("draft_angles", [])
                        
                        item.editor_note = a.get("editor_note", "")
                
                print("[Editor] Deep analysis complete for %d items" % len(analyzed))
                
        except json.JSONDecodeError as e:
            print("[Editor] JSON parse error: %s" % e)
    else:
        print("[Editor] Gemini unavailable, using rule-based analysis")
        curated_items = _apply_rule_based_analysis(curated_items)
    
    return curated_items


def _apply_rule_based_analysis(items: list[CuratedItem]) -> list[CuratedItem]:
    for item in items:
        if item.content_tier in [ContentTier.GOLD, ContentTier.SILVER]:
            
            item.core_highlight = "[%s] %s" % (item.signal_type.value.replace("_", " ").title(), item.title[:80])
            
            item.industry_impact = (
                "短期：可能引发行业关注；"
                "中期：视具体落地情况而定；"
                "长期：需要持续观察"
            )
            
            item.comparison_context = "待Gemini分析后补充对比信息"
            
            item.actionable_for_editor = "建议跟进此事件发展，收集更多信息后决定是否撰写"
            
            item.draft_angles = [
                "事件概述：%s" % item.title[:50],
                "行业影响分析",
                "技术细节解读（如有）"
            ]
            
            item.fact_checks = [{
                "claim": item.title[:50],
                "status": "[待验证]",
                "confidence": 0.5
            }]
    
    return items


async def run_editor_report(category: str = "tech", chat_id: str = None, 
                           max_items: int = 30) -> dict:
    print("\n[Editor] === Starting Editor Assistant v3.0 ===")
    print("[Editor] Category: %s | Max items: %d" % (category, max_items))
    
    start_time = time.time()
    
    try:
        result = await rss_aggregate(
            None,  # ctx - not needed for standalone use
            max_items=max_items,
            send_to_telegram=False,
            category=category
        )
        
        if not result or "items" not in result:
            return {"count": 0, "report": "*[Editor] 无法获取新闻数据*", "items": []}
        
        items = result["items"]
        print("[Editor] Raw items collected: %d" % len(items))
        
        curated = await deep_curate(items)
        print("[Editor] After curation: %d items" % len(curated))
        
        gold_count = sum(1 for c in curated if c.content_tier == ContentTier.GOLD)
        silver_count = sum(1 for c in curated if c.content_tier == ContentTier.SILVER)
        bronze_count = sum(1 for c in curated if c.content_tier == ContentTier.BRONZE)
        filtered_count = sum(1 for c in curated if c.content_tier == ContentTier.FILTER)
        
        print("[Editor] Tier breakdown:")
        print("  GOLD:   %d (头版素材)" % gold_count)
        print("  SILVER: %d (重要资讯)" % silver_count)
        print("  BRONZE: %d (一般动态)" % bronze_count)
        print("  FILTER: %d (已过滤)" % filtered_count)
        
        analyzed = await gemini_deep_analyze(curated)
        
        display_items = [c for c in analyzed if c.content_tier != ContentTier.FILTER]
        
        report = _format_editor_report(display_items, category)
        
        elapsed = time.time() - start_time
        print("[Editor] Report generated in %.1fs" % elapsed)
        
        notion_sync_result = None
        try:
            from notion_sync import batch_create_pages
            items_for_notion = [asdict(c) for c in display_items if c.content_tier in [ContentTier.GOLD, ContentTier.SILVER]]
            if items_for_notion:
                print("[Editor] Syncing %d high-value items to Notion..." % len(items_for_notion))
                notion_sync_result = await batch_create_pages(items_for_notion, delay_seconds=0.5)
                print("[Editor] Notion sync: %d success, %d failed" % (
                    notion_sync_result.get("success", 0),
                    notion_sync_result.get("failed", 0)
                ))
        except Exception as e:
            print("[Editor] Notion sync skipped (optional): %s" % str(e)[:80])
            notion_sync_result = None
        
        return {
            "count": len(display_items),
            "tier_breakdown": {
                "gold": gold_count,
                "silver": silver_count,
                "bronze": bronze_count,
                "filtered": filtered_count
            },
            "report": report,
            "items": [asdict(c) for c in display_items],
            "notion_sync": notion_sync_result
        }
        
    except Exception as e:
        print("[Editor] Error generating report: %s" % e)
        import traceback
        traceback.print_exc()
        return {"count": 0, "report": "*[Editor] 生成失败: %s*" % str(e)[:100], "items": []}


def _format_editor_report(items: list[CuratedItem], category: str) -> str:
    now = datetime.now(timezone(timedelta(hours=8)))
    
    header = """**📝 Editor Assistant v3.0 — 专业编辑情报**
_%s | 分类: %s_

""" % (now.strftime("%Y-%m-%d %H:%M"), category.upper())
    
    sections = {
        ContentTier.GOLD: ("🥇 头版素材 (GOLD)", []),
        ContentTier.SILVER: ("🥈 重要资讯 (SILVER)", []),
        ContentTier.BRONZE: ("🥉 一般动态 (BRONZE)", []),
    }
    
    for item in items:
        if item.content_tier in sections:
            sections[item.content_tier][1].append(item)
    
    body = ""
    
    for tier_name, tier_items in sections.values():
        if not tier_items:
            continue
        
        body += "**%s** (%d条)\n\n" % (tier_name, len(tier_items))
        
        for i, item in enumerate(tier_items[:10], 1):
            
            star = "⭐" if any(w["entity"].lower() in item.title.lower() for w in EDITOR_PROFILE["watchlist"]) else ""
            
            body += "**%d. %s %s**\n" % (i, item.title[:80], star)
            body += "`[%s]` `%s`\n" % (item.signal_type.value.upper(), item.tier)
            
            if item.core_highlight:
                body += "_💡 %s_\n" % item.core_highlight[:120]
            
            if item.industry_impact:
                impact_short = item.industry_impact[:150] + "..." if len(item.industry_impact) > 150 else item.industry_impact
                body += "📊 行业影响: %s\n" % impact_short
            
            if item.draft_angles:
                angles_str = " | ".join(item.draft_angles[:2])
                body += "✍️ 写稿角度: %s\n" % angles_str
            
            if item.actionable_for_editor:
                action_short = item.actionable_for_editor[:100] + "..." if len(item.actionable_for_editor) > 100 else item.actionable_for_editor
                body += "▶️ 下一步: %s\n" % action_short
            
            if item.tags:
                tags_str = " ".join(["`%s`" % t for t in item.tags[:5]])
                body += "标签: %s\n" % tags_str
            
            if item.categories:
                cats_str = " ".join(["`%s`" % c for c in item.categories[:4]])
                body += "分类: %s\n" % cats_str
            
            if item.fact_checks:
                fc_summary = ", ".join([
                    "%s%s" % (fc.get("claim", "")[:30], fc.get("status", ""))
                    for fc in item.fact_checks[:2]
                ])
                body += "🔍 事实核查: %s\n" % fc_summary
            
            body += "🔗 [原文](%s)\n\n" % item.link
        
        body += "---\n\n"
    
    footer = """
_*Editor v3.0: 深度降噪 + 关联分析 + 写稿辅助*_
_信噪比优化: 已过滤噪音内容_"""
    
    return header + body + footer


async def send_to_telegram(message: str, chat_id: str = None, bot_token: str = None) -> bool:
    target_chat = chat_id or os.environ.get("CHAT_ID_G", "-1003590230315")
    token = bot_token or os.environ.get("BOT_TOKEN_G")
    
    if not token:
        print("[Send] No BOT_TOKEN found")
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
        chunks.append(current_chunk.strip())
    
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


async def export_material_library(items: list[CuratedItem], output_path: str = None) -> str:
    if output_path is None:
        output_path = project_root / "data" / "material_library.json"
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    export_data = {
        "exported_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "version": "3.0",
        "total_items": len(items),
        "by_tier": {
            "gold": sum(1 for i in items if i.content_tier == ContentTier.GOLD),
            "silver": sum(1 for i in items if i.content_tier == ContentTier.SILVER),
            "bronze": sum(1 for i in items if i.content_tier == ContentTier.BRONZE),
        },
        "items": [asdict(i) for i in items if i.content_tier != ContentTier.FILTER]
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    
    print("[Editor] Material library exported to: %s" % output_path)
    print("[Editor] Total items: %d" % export_data["total_items"])
    
    return str(output_path)


if __name__ == "__main__":
    import asyncio
    
    async def test():
        result = await run_editor_report(category="tech", max_items=15)
        print("\n=== RESULT ===")
        print("Count:", result["count"])
        print("Tier breakdown:", result.get("tier_breakdown", {}))
        print("\nReport preview (500 chars):")
        print(result["report"][:500])
        
        if result.get("items"):
            await export_material_library(
                [CuratedItem(**i) for i in result["items"]],
                "data/test_material_library.json"
            )
    
    asyncio.run(test())
