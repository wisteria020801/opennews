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
    
    historical_context: str = ""
    competitor_reactions: dict = field(default_factory=dict)
    industry_chain_position: str = ""
    
    fact_checks: list[dict] = field(default_factory=list)
    source_chain: list[str] = field(default_factory=list)
    
    actionable_for_editor: str = ""
    draft_angles: list[str] = field(default_factory=list)
    
    is_wrapper: bool = False
    is_reinvention: bool = False
    noise_reasons: list[str] = field(default_factory=list)
    
    source_tier: str = ""
    source_credibility: float = 0.0
    cross_source_count: int = 0
    fact_parts: list[str] = field(default_factory=list)
    inference_parts: list[str] = field(default_factory=list)
    single_source_warning: bool = False
    unverified_claims: list[str] = field(default_factory=list)
    
    publish_time: str = ""
    is_official_source: bool = False
    is_repost: bool = False
    original_domain: str = ""
    conflicting_info: list[dict] = field(default_factory=list)
    source_freshness: str = ""
    
    # ══════════════════════════════════════
    # 5-Layer Intelligence Workstation (v3.0)
    # ══════════════════════════════════════
    
    # Layer 2: Event Dedup (去重层)
    event_id: str = ""
    merged_sources: list[str] = field(default_factory=list)
    merged_links: list[str] = field(default_factory=list)
    is_merged_event: bool = False
    dedup_confidence: float = 0.0
    
    # Layer 3: 3-Dimension Scoring (重要性评分层)
    attention_score: float = 0.0
    tech_depth_score: float = 0.0
    industry_impact_score: float = 0.0
    intelligence_grade: str = ""  # S/A/B/C/D
    
    # Layer 4: Why It Matters (解释层)
    why_it_matters: str = ""
    significance_level: str = ""  # TRANSFORMATIVE / MAJOR / MODERATE / MINOR
    key_takeaways: list[str] = field(default_factory=list)
    context_gap: str = ""  # What most people miss about this
    
    # Layer 5: Action Plan (行动层)
    action_plan: dict = field(default_factory=dict)
    next_steps: list[str] = field(default_factory=list)
    people_to_follow: list[str] = field(default_factory=list)
    directions_to_watch: list[str] = field(default_factory=list)
    time_sensitivity: str = ""  # NOW / THIS_WEEK / THIS_MONTH / MONITOR


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

def build_evidence_chain(item: CuratedItem, all_items: list[CuratedItem] = None) -> dict:
    source = item.source or ""
    title = item.title or ""
    summary = item.summary or ""
    link = item.link or ""
    
    source_info = get_source_tier(source)
    item.source_tier = source_info.get("name", "tier_4_unknown")
    item.source_credibility = source_info.get("weight", 0.5) * 100
    
    domain_match = re.search(r'https?://(?:www\.)?([^/]+)', link)
    if domain_match:
        item.original_domain = domain_match.group(1).lower()
    
    official_domains_patterns = [
        r'openai\.com', r'anthropic\.com', r'deepmind\.google',
        r'meta\.ai', r'nvidia\.com', r'google\.com/research',
        r'microsoft\.com/research', r'arxiv\.org',
        r'\.gov/', r'\.edu/',
        r'apple\.com/newsroom', r'amazon\.science'
    ]
    if any(re.search(p, link, re.I) for p in official_domains_patterns):
        item.is_official_source = True
        item.source_credibility = min(100, item.source_credibility + 15)
    
    repost_indicators = [
        (r'reuters|bloomberg|apnews|afp', "一线通讯社转载"),
        (r'techcrunch|theverge|wired|arstechnica', "科技媒体二次报道"),
        (r'36kr|ifeng|sina|qq\.com', "国内门户转载"),
        (r'medium\.com|substack|zhihu', "个人/社区转发"),
    ]
    for pattern, label in repost_indicators:
        if re.search(pattern, link, re.I):
            item.is_repost = True
            break
    
    time_patterns = [
        (r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', "%Y-%m-%d"),
        (r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})', "%d %b %Y"),
        (r'(?:published|posted|updated)\s*(\d+)\s*(?:hours?|minutes?)?\s*ago', "recent"),
        (r'(\d+)\s*分钟前|\d+\s*小时前|\d+\s*天前', "recent_cn"),
    ]
    import time as _time
    now_ts = _time.time()
    for pattern, fmt in time_patterns:
        match = re.search(pattern, summary[:200], re.I)
        if match and fmt in ["recent", "recent_cn"]:
            time_str = match.group(0).strip()
            num_match = re.search(r'(\d+)', time_str)
            if num_match:
                hours_ago = int(num_match.group(1))
                if '小时' in time_str or 'hour' in time_str.lower():
                    hours_ago = hours_ago
                elif '天' in time_str or 'day' in time_str.lower():
                    hours_ago = hours_ago * 24
                elif '分钟' in time_str or 'minute' in time_str.lower():
                    hours_ago = hours_ago / 60
                
                if hours_ago < 6:
                    item.publish_time = "<6h"
                    item.source_freshness = "FRESH"
                    item.source_credibility = min(100, item.source_credibility + 5)
                elif hours_ago < 24:
                    item.publish_time = "<24h"
                    item.source_freshness = "RECENT"
                elif hours_ago < 72:
                    item.publish_time = "<72h"
                    item.source_freshness = "STALE"
                else:
                    item.publish_time = ">72h"
                    item.source_freshness = "OLD"
            break
        elif match:
            try:
                from datetime import datetime
                pub_date = datetime.strptime(match.group(1), fmt)
                age_hours = (now_ts - pub_date.timestamp()) / 3600
                if age_hours < 6:
                    item.publish_time = "<6h"
                    item.source_freshness = "FRESH"
                elif age_hours < 24:
                    item.publish_time = "<24h"
                    item.source_freshness = "RECENT"
                else:
                    item.publish_time = ">24h"
                    item.source_freshness = "STALE"
            except:
                pass
            break
    
    if not item.publish_time:
        item.publish_time = "unknown"
        item.source_freshness = "UNKNOWN"
    
    if all_items:
        title_lower = title.lower()
        cross_count = 0
        conflicting_items = []
        
        for other in all_items:
            if other.link and other.link != item.link:
                other_title = (other.title or "").lower()
                shared_words = set(title_lower.split()) & set(other_title.split())
                
                if len(shared_words) >= 3:
                    cross_count += 1
                    
                    negation_patterns = [r'not|rul|false|denied|否认|辟谣|取消|推迟']
                    has_negation = any(re.search(p, other_title, re.I) for p in negation_patterns)
                    
                    if has_negation:
                        conflicting_items.append({
                            "source": other.source,
                            "title": (other.title or "")[:60],
                            "conflict_type": "negation"
                        })
                    elif abs(len(other.summary or "") - len(summary)) > 100:
                        detail_diff = True
                        conflicting_items.append({
                            "source": other.source,
                            "title": (other.title or "")[:60],
                            "conflict_type": "detail_discrepancy"
                        })
        
        item.cross_source_count = cross_count
        item.single_source_warning = cross_count == 0
        item.conflicting_info = conflicting_items[:3]
        
        if conflicting_items:
            item.source_credibility = max(20, item.source_credibility - 10)
    
    inference_keywords = [
        "可能", "或许", "预计", "推测", "暗示", "预示", "潜在", 
        "可能引发", "或将", "有望", "预期", "could", "might", "likely",
        "potentially", "expected", "suggests", "indicates", "may"
    ]
    
    combined_text = "%s %s" % (title, summary)
    sentences = re.split(r'[。！？.!?\n]', combined_text)
    
    fact_parts = []
    inference_parts = []
    unverified = []
    
    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 10:
            continue
        
        has_inference = any(kw in sent.lower() for kw in inference_keywords)
        
        number_pattern = re.compile(r'\d+[%。，.]?|\$\d+[\d,.]*|%\d+')
        has_numbers = bool(number_pattern.search(sent))
        
        quote_pattern = re.compile(r'["\"].*?["\"]|said|表示|称|宣布|透露')
        has_quote = bool(quote_pattern.search(sent))
        
        official_patterns = [
            r'(?:released|announced|published|launched|发布|宣布|推出)',
            r'(?:research|study|paper|report|研究|报告|论文)',
            r'\$(?:\d+[\d,.]*|\d+\s*(?:million|billion|M|B))',
        ]
        has_official_signal = any(re.search(p, sent, re.I) for p in official_patterns)
        
        if has_inference and not (has_numbers or has_quote):
            inference_parts.append(sent)
            
            vague_words = ["all", "every", "none", "never", "always", "完全", "所有", "从未"]
            is_absolute = any(v in sent.lower() for v in vague_words)
            if is_absolute:
                unverified.append("[绝对化表述] %s" % sent[:80])
        elif has_official_signal or has_quote or has_numbers:
            fact_parts.append(sent)
        else:
            neutral_score = 0
            if len(sent) > 50:
                neutral_score += 1
            entity_count = sum(1 for e in ENTITY_KEYWORDS.values() if any(kw in sent.lower() for kw in e))
            neutral_score += entity_count
            
            if neutral_score >= 2:
                fact_parts.append(sent)
            else:
                inference_parts.append(sent)
    
    item.fact_parts = fact_parts[:5]
    item.inference_parts = inference_parts[:5]
    item.unverified_claims = unverified[:3]
    
    credibility_level = ""
    cred_score = item.source_credibility
    
    if item.single_source_warning:
        cred_score -= 20
    
    if item.unverified_claims:
        cred_score -= 10
    
    if item.is_repost and not item.is_official_source:
        cred_score -= 5
    
    if item.source_freshness == "OLD":
        cred_score -= 5
    elif item.source_freshness == "FRESH":
        cred_score += 3
    
    if item.conflicting_info:
        cred_score -= 8
    
    cred_score = max(0, min(100, cred_score))
    
    if cred_score >= 75:
        credibility_level = "HIGH"
    elif cred_score >= 50:
        credibility_level = "MEDIUM"
    else:
        credibility_level = "LOW"
    
    return {
        "source_tier": item.source_tier,
        "source_label": source_info.get("label", "Unknown"),
        "credibility_score": round(cred_score, 1),
        "credibility_level": credibility_level,
        "cross_source_count": item.cross_source_count,
        "single_source_warning": item.single_source_warning,
        "fact_count": len(item.fact_parts),
        "inference_count": len(item.inference_parts),
        "unverified_count": len(item.unverified_claims),
        "fact_samples": item.fact_parts[:3],
        "inference_samples": item.inference_parts[:3],
        "unverified_samples": item.unverified_claims[:2],
        "publish_time": item.publish_time,
        "source_freshness": item.source_freshness,
        "is_official_source": item.is_official_source,
        "is_repost": item.is_repost,
        "original_domain": item.original_domain,
        "conflicting_info": item.conflicting_info
    }


def _extract_event_signature(title: str, summary: str = "") -> str:
    import re
    text = (title + " " + summary).lower()
    
    entities = re.findall(r'(openai|anthropic|deepmind|google|meta|mistral|xai|nvidia|apple|microsoft|amazon|tesla|spacex)', text)
    actions = re.findall(r'(release|launch|announce|acquire|fund|invest|ban|regulate|sue|hire|fire|quit|merge|ipo|raise|cut|delay|recall)', text)
    objects = re.findall(r'(gpt|claude|gemini|llama|model|api|chip|gpu|robot|agent|dataset|benchmark|paper|patent|license|policy|law|bill)', text)
    
    sig_parts = sorted(set(entities))[:3] + sorted(set(actions))[:2] + sorted(set(objects))[:2]
    return "|".join(sig_parts) if sig_parts else title[:40].replace(" ", "_")


def _event_similarity(item_a: CuratedItem, item_b: CuratedItem) -> float:
    import re
    from difflib import SequenceMatcher
    
    sig_a = _extract_event_signature(item_a.title, item_a.summary)
    sig_b = _extract_event_signature(item_b.title, item_b.summary)
    
    if not sig_a or not sig_b:
        return 0.0
    
    if sig_a == sig_b:
        base_sim = 0.9
    else:
        shared = set(sig_a.split("|")) & set(sig_b.split("|"))
        union = set(sig_a.split("|")) | set(sig_b.split("|"))
        base_sim = len(shared) / len(union) if union else 0.0
    
    title_sim = SequenceMatcher(None, item_a.title.lower(), item_b.title.lower).ratio()
    
    entity_a = set(re.findall(r'[A-Z][a-z]+|[A-Z]{2,}', item_a.title))
    entity_b = set(re.findall(r'[A-Z][a-z]+|[A-Z]{2,}', item_b.title))
    entity_overlap = len(entity_a & entity_b) / max(len(entity_a | entity_b), 1)
    
    return 0.4 * base_sim + 0.35 * title_sim + 0.25 * entity_overlap


def event_dedup(items: list[CuratedItem], threshold: float = 0.55) -> list[CuratedItem]:
    if len(items) <= 1:
        return items
    
    n = len(items)
    parent_map = {}
    
    for i in range(n):
        for j in range(i + 1, n):
            sim = _event_similarity(items[i], items[j])
            
            if sim >= threshold:
                score_i = items[i].overall_score or items[i].source_credibility or 0.5
                score_j = items[j].overall_score or items[j].source_credibility or 0.5
                
                if score_i >= score_j:
                    parent_map[j] = i
                else:
                    parent_map[i] = j
    
    result = []
    used_children = set()
    
    for idx, item in enumerate(items):
        if idx in parent_map and idx not in used_children:
            continue
        
        if idx in used_children:
            continue
        
        children = [c for c, p in parent_map.items() if p == idx]
        
        if children:
            merged_item = item
            
            all_sources = [item.source] + [items[c].source for c in children]
            all_links = [item.link] + [items[c].link for c in children if items[c].link and items[c].link != item.link]
            
            merged_item.event_id = "evt_%s" % _extract_event_signature(item.title)[:20]
            merged_item.merged_sources = list(set(all_sources))
            merged_item.merged_links = all_links[:10]
            merged_item.is_merged_event = True
            merged_item.dedup_confidence = min(0.95, 0.7 + 0.05 * len(children))
            merged_item.cross_source_count = max(merged_item.cross_source_count, len(all_sources))
            
            summaries = [s for s in [item.summary] + [items[c].summary for c in children] if s]
            if len(summaries) > 1:
                merged_item.summary = summaries[0]
                merged_item.core_highlight = " [%d源验证: %s]" % (len(all_sources), ", ".join(set(all_sources)))
            
            used_children.update(children)
            result.append(merged_item)
        else:
            result.append(item)
    
    print("[Dedup] %d items → %d events (%d merged)" % (n, len(result), n - len(result)))
    return result

def generate_quick_template(item: dict) -> str:
    title = item.get("title", "Untitled")
    summary = item.get("summary", "")
    link = item.get("link", "")
    source = item.get("source", "")
    tier_raw = item.get("content_tier", ContentTier.FILTER)
    tier = str(tier_raw).upper() if tier_raw else "UNKNOWN"
    evidence = item.get("evidence_chain") or {}
    
    cred_score = evidence.get("credibility_score", 0) if evidence else 0
    cred_level = evidence.get("credibility_level", "UNKNOWN") if evidence else "UNKNOWN"
    is_official = evidence.get("is_official_source", False) if evidence else False
    is_repost = evidence.get("is_repost", False) if evidence else False
    freshness = evidence.get("source_freshness", "UNKNOWN") if evidence else "UNKNOWN"
    cross_count = evidence.get("cross_source_count", 0) if evidence else 0
    single_warn = evidence.get("single_source_warning", True) if evidence else True
    conflicts = evidence.get("conflicting_info", [])
    pub_time = evidence.get("publish_time", "unknown")
    original_domain = evidence.get("original_domain", "")
    
    fact_count = evidence.get("fact_count", 0)
    inference_count = evidence.get("inference_count", 0)
    unverified_count = evidence.get("unverified_count", 0)
    
    source_tag = ""
    if is_official:
        source_tag = "[官方一手]"
    elif is_repost:
        source_tag = "[二手转载]"
    else:
        source_tag = "[未知来源]"
    
    freshness_tag = {"FRESH": "🟢新", "RECENT": "🟡较新", "STALE": "🟠较旧", "OLD": "🔴旧", "UNKNOWN": "⚪未知"}.get(freshness, "⚪")
    
    cross_tag = ""
    if cross_count >= 3:
        cross_tag = "✅多源验证(%d)" % cross_count
    elif cross_count > 0:
        cross_tag = "⚠️部分验证(%d)" % cross_count
    else:
        cross_tag = "❌单一来源"
    
    conflict_tag = ""
    if conflicts:
        conflict_tag = " ⚠️有冲突报道"
    
    verdict_options = (
        "A) 高价值 - 值得立刻写，信息差大\n"
        "   → 时效新 + 来源可靠 + 别人还没覆盖\n\n"
        "B) 中等价值 - 可以写，但需要找角度\n"
        "   → 信息已扩散，但你有独特视角\n\n"
        "C) 低价值/噪音 - 跳过或仅记录\n"
        "   → 不重要 / 已被过度报道 / 无法验证"
    )
    
    template = (
        "═══════════════════════════════════════\n"
        "   三段式速写模板 | Information Arbitrage\n"
        "═══════════════════════════════════════\n\n"
        
        "【标题】\n"
        "%s\n\n"
        
        "───────────────────────────────────────\n"
        "第一段：事实（发生了什么）\n"
        "───────────────────────────────────────\n\n"
        "原始素材：\n"
        "%s\n\n"
        "你整理后的事实（1-3句话）：\n"
        "_\n"
        "在这里写：谁、做了什么、什么时候、结果是什么\n"
        "_\n\n"
        
        "───────────────────────────────────────\n"
        "第二段：来源（可信不可信）\n"
        "───────────────────────────────────────\n\n"
        "| 项目 | 状态 |\n"
        "|------|------|\n"
        "| 来源类型 | %s%s |\n"
        "| 可信度 | %s (%.0f%%) |\n"
        "| 时效性 | %s (%s) |\n"
        "| 验证状态 | %s%s |\n"
        
    ) % (
        title,
        summary[:200] + ("..." if len(summary) > 200 else ""),
        source_tag, " %s" % original_domain if original_domain else "",
        cred_level, cred_score,
        freshness_tag, pub_time,
        cross_tag, conflict_tag
    )
    
    if fact_count > 0 or inference_count > 0:
        template += "\n| 事实/推断 | 事实%d条 / 推断%d条" % (fact_count, inference_count)
        if unverified_count > 0:
            template += " / 待验%d条" % unverified_count
        template += " |\n"
    
    template += (
        "\n你的核验结论（1句话）：\n"
        "_\n"
        "这里写：这个来源能不能信，为什么\n"
        "_\n\n"
        
        "───────────────────────────────────────\n"
        "第三段：判断（值不值得写）\n"
        "───────────────────────────────────────\n\n"
        "【强制选择】这件事的价值等级：\n\n"
        "%s\n\n"
        "你的选择：_____\n\n"
        "一句话理由：\n"
        "_\n"
        "这里写：为什么选这个等级，你的依据是什么\n"
        "_\n\n"
        
        "如果选A，补充：\n"
        "  你的角度/切入点：___________________\n"
        "  预计产出形式：快讯 / 短文 / 深度\n\n"
        "如果选B，补充：\n"
        "  你能加什么别人没有的：______________\n\n"
        "如果选C，原因：\n"
        "  _________________________________\n\n"
        
        "───────────────────────────────────────\n"
        "原文链接: %s\n"
        "═══════════════════════════════════════\n"
    ) % (verdict_options, link)
    
    return template

def generate_draft_framework(item: dict, mode: str = "short") -> str:
    title = item.get("title", "Untitled")
    summary = item.get("summary", "")
    entities = item.get("tags", [])
    core_highlight = item.get("core_highlight", "")
    angles = item.get("draft_angles", [])
    historical = item.get("historical_context", "")
    reactions = item.get("competitor_reactions", {})
    chain_pos = item.get("industry_chain_position", "")
    source = item.get("source", "")
    link = item.get("link", "")
    tier_raw = item.get("content_tier", ContentTier.FILTER)
    tier = str(tier_raw).upper() if tier_raw else "UNKNOWN"
    evidence = item.get("evidence_chain") or {}
    
    credibility_block = ""
    if evidence:
        cred_level = evidence.get("credibility_level", "MEDIUM")
        cred_score = evidence.get("credibility_score", 0)
        source_label = evidence.get("source_label", "")
        cross_count = evidence.get("cross_source_count", 0)
        single_warn = evidence.get("single_source_warning", False)
        is_official = evidence.get("is_official_source", False)
        is_repost = evidence.get("is_repost", False)
        original_domain = evidence.get("original_domain", "")
        freshness = evidence.get("source_freshness", "UNKNOWN")
        pub_time = evidence.get("publish_time", "unknown")
        conflicts = evidence.get("conflicting_info", [])
        
        warning_icon = "[!]" if single_warn else "[OK]"
        official_tag = " [OFFICIAL]" if is_official else ""
        repost_tag = " [REPOST]" if is_repost else ""
        freshness_icon = {"FRESH": "🟢", "RECENT": "🟡", "STALE": "🟠", "OLD": "🔴", "UNKNOWN": "⚪"}.get(freshness, "⚪")
        
        source_status = (
            "%s Source: %s%s%s (%.0f%%)\n"
            "Domain: %s | Age: %s %s"
        ) % (
            warning_icon, source_label, official_tag, repost_tag, cred_score,
            original_domain or "N/A", pub_time, freshness_icon
        )
        
        if single_warn:
            source_status += "\n[WARNING] Single source - not cross-verified"
        elif cross_count >= 3:
            source_status += "\n[CONFIRMED] %d sources reporting" % cross_count
        elif cross_count > 0:
            source_status += "\n[PARTIAL] %d related sources found" % cross_count
        
        if conflicts:
            source_status += "\n[CONFLICT] Found conflicting reports:"
            for c in conflicts[:2]:
                c_type = c.get("conflict_type", "")
                c_label = "[DENIED]" if c_type == "negation" else "[DIFFERS]"
                source_status += "\n  %s %s: %s..." % (c_label, c.get("source", ""), (c.get("title", "") or "")[:40])
        
        credibility_block = (
            "\n[EVIDENCE CHAIN v2.0]\n%s\n" % source_status
        )
        
        fact_samples = evidence.get("fact_samples", [])
        inf_samples = evidence.get("inference_samples", [])
        unv_samples = evidence.get("unverified_samples", [])
        
        if fact_samples:
            credibility_block += "\n*Verified Facts (%d):*\n" % len(fact_samples)
            for f in fact_samples[:2]:
                credibility_block += "  + %s...\n" % f[:60]
        
        if inf_samples:
            credibility_block += "\n*Model Inferences - NOT facts (%d):*\n" % len(inf_samples)
            for i in inf_samples[:2]:
                credibility_block += "  ~ %s...\n" % i[:60]
        
        if unv_samples:
            credibility_block += "\n*Needs Verification (%d):*\n" % len(unv_samples)
            for u in unv_samples:
                credibility_block += "  ? %s\n" % u
        
        if not fact_samples and not inf_samples:
            credibility_block += "\n_[Insufficient text for analysis - verify manually]_"
    
    if mode == "short":
        draft = (
            "[DRAFT MODE: Short Article (~500 words)]\n"
            "=========================================\n\n"
            "*Working Title:*\n%s\n\n"
            "*Selected Angle:*\n%s\n\n"
            "---\n\n"
            "%s"
            "[SECTION 1: Hook / Opening]\n"
            "(Target: 1-2 sentences to grab attention)\n"
            "Context: %s\n"
            "Draft opening:\n"
            "_\n"
            "[YOUR HOOK HERE - Why should reader care about THIS specific news?]\n"
            "_\n\n"
            "[SECTION 2: Core Facts]\n"
            "(Target: 2-3 bullet points of verifiable information)\n"
            "Source: %s | Tier: %s\n"
            "Key facts from material:\n"
            "- %s\n\n"
            "[SECTION 3: YOUR JUDGMENT] ***REQUIRED***\n"
            "(This is where YOUR value lives - NOT the bot's analysis)\n\n"
            "Question 1: How important is this news REALLY?\n"
            "Options:\n"
            "  A) Critical breakthrough - industry will change\n"
            "  B) Important evolution - significant but expected\n"
            "  C) Notable but incremental - worth watching\n"
            "  D) Noise - skip it\n"
            "Your choice: _____\n"
            "Your reason (2-3 sentences): _________________________________\n\n"
            "Question 2: What's your UNIQUE take?\n"
            "(What are others missing? What's your angle?)\n"
            "Your take: ___________________________________________________\n\n"
            "[SECTION 4: Industry Impact]\n"
            "Chain position: %s\n"
            "Who's affected:\n"
            "- Upstream: ___\n"
            "- Midstream: ___\n"
            "- Downstream: ___\n"
            "(Fill based on YOUR understanding, not just bot output)\n\n"
            "[SECTION 5: Closing / CTA]\n"
            "(End with question or actionable insight for readers)\n"
            "Draft closing:\n"
            "_\n"
            "[YOUR CLOSING THOUGHT - What should reader DO with this info?]\n"
            "_\n\n"
            "---\n"
            "[WORD COUNT TARGET: ~500 | ESTIMATED TIME TO FINALIZE: 15-20 min]\n"
            "[ORIGINAL LINK: %s]\n"
        ) % (
            title[:60],
            angles[0] if angles else "To be determined",
            credibility_block,
            historical[:100] if historical else "Context needed",
            source[:30], tier,
            summary[:120] if summary else "Facts to be extracted",
            chain_pos if chain_pos else "Position to be determined",
            link or "Not available"
        )
    else:
        draft = (
            "[DRAFT MODE: Deep Dive Article (~1500 words)]\n"
            "=================================================\n\n"
            "*Working Title:*\n%s\n\n"
            "*Subtitle/Teaser:*\n_\n"
            "[YOUR COMPELLING TEASER - Make them want to read]\n"
            "_\n\n"
            "%s"
            "---\n\n"
            "[PART 1: Background & Context (~200 words)]\n"
            "Historical context provided:\n"
            "> %s\n\n"
            "Your framing:\n"
            "_\n"
            "[How does this event FIT into the bigger picture? Your narrative, not bot's timeline]\n"
            "_\n\n"
            "[PART 2: The Event - What Happened (~300 words)]\n"
            "Core facts from sources:\n"
            "- Source: %s (Tier: %s)\n"
            "- Summary: %s\n\n"
            "Detailed breakdown:\n"
            "1. [Official announcement key points]\n"
            "2. [Numbers/data if available]\n"
            "3. [Official statements vs reality check]\n\n"
            "[PART 3: DEEP ANALYSIS - YOUR CORE VALUE (~400 words)]\n"
            "*** THIS IS THE MOST IMPORTANT SECTION ***\n\n"
            "3A. Your JUDGMENT on significance:\n"
            "_\n"
            "[Is this a real breakthrough or marketing? Why? Use evidence.]\n"
            "_\n\n"
            "3B. What others are MISSING:\n"
            "_\n"
            "[What angle hasn't been covered? What's your unique insight?]\n"
            "_\n\n"
            "3C. Comparison to similar events:\n"
            "_\n"
            "[Connect to past events. Show you understand the PATTERN, not just this one news.]\n"
            "_\n\n"
            "[PART 4: Industry Chain Impact (~300 words)]\n"
            "Position: %s\n\n"
            "Upstream effects (chips/infra):\n"
            "_[Your analysis, not template]_\n\n"
            "Midstream effects (models/tools):\n"
            "_[Your analysis]_\n\n"
            "Downstream effects (apps/users):\n"
            "_[Your analysis]_\n\n"
            "[PART 5: Competitor Reactions (~200 words)]\n"
            "Predicted responses:\n"
        ) % (
            title[:60],
            credibility_block,
            historical[:150] if historical else "Historical context needed",
            source[:30], tier,
            summary[:150] if summary else "Event details to be extracted",
            chain_pos if chain_pos else "Chain position to be analyzed"
        )
        
        if reactions:
            draft += "\n"
            for comp, reaction in list(reactions.items())[:4]:
                draft += "- %s: %s\n" % (comp, reaction)
            draft += "\nYour analysis of these predictions:\n"
            draft += "_[Which will happen? Which won't? Why?]_\n\n"
        else:
            draft += "\n_[Competitor reactions to be researched]_\n\n"
        
        draft += (
            "[PART 6: Future Outlook (~100 words)]\n"
            "Short-term (1-3 months): _______________________\n"
            "Medium-term (6-12 months): _____________________\n"
            "Long-term implications: ________________________\n\n"
            "[PART 7: Sources & References]\n"
            "- Primary: %s\n"
            "- Additional sources to verify:\n"
            "  1. _____________\n"
            "  2. _____________\n"
            "  3. _____________\n\n"
            "---\n"
            "[WORD COUNT TARGET: ~1500-1800 | ESTIMATED TIME TO FINALIZE: 40-60 min]\n"
            "[REMEMBER: The value is in YOUR judgment, not the structure]\n"
        ) % (link or "Primary source link needed")
    
    return draft

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

## 关联分析知识库

### 1. AI行业关键历史事件（用于历史对比）
- **2022.11** OpenAI发布ChatGPT → 引发全球AI竞赛
- **2023.03** GPT-4发布 → 多模态能力突破，企业应用加速
- **2023.07** Meta发布Llama 2开源 → 开源模型商用化转折点
- **2023.11** OpenAI政变（Altman被罢免又回归） → AI治理关注度飙升
- **2024.02** Sora视频生成发布 → 多模态竞争白热化
- **2024.05** GPT-4o发布 → 实时语音交互新时代
- **2024.09** OpenAI完成最新融资（估值超1500亿）→ 资本市场信心
- **2024.10** Anthropic发布Claude 3.5 Sonnet → 编程能力大幅提升
- **2024.12** Google Gemini 2.0发布 → 多智能体能力
- **2025.01** DeepSeek-R1发布 → 开源推理模型突破
- **2025.03** GPT-5预览/ Claude 4发布预期 → 新一轮模型军备竞赛

### 2. 竞品反应预测矩阵
当某公司发布重大更新时，竞争对手的典型反应模式：
| 触发事件 | OpenAI | Anthropic | Google | Meta | 其他 |
|---------|--------|-----------|--------|------|------|
| 模型发布 | 加速自家节奏 | 强调安全差异 | 对标参数 | 开源对冲 | 集成适配 |
| 融资消息 | 不回应或低调 | 可能跟进融资 | 加大投入 | 独立发展 | 寻求合作 |
| 开源动作 | 部分开放API | 坚持闭源 | 全面开源 | 继续开源 | 拥抱生态 |
| 政策监管 | 主动合规 | 安全优先 | 游说影响 | 自律框架 | 等待观望 |
| 价格调整 | 跟进降价 | 维持高端 | 免费策略 | 免费增值 | 差异化 |

### 3. AI产业链图谱定位
```
[上游：基础设施层]
├── 芯片算力: NVIDIA, AMD, TPU(Google), 昇腾(华为)
├── 云服务: AWS(Azure), GCP, Azure, 阿里云
└── 数据中心: Equinix, Digital Realty

[中游：模型与平台层]
├── 闭源模型: OpenAI(GPT), Anthropic(Claude), Google(Gemini)
├── 开源模型: Meta(Llama), Mistral, Qwen(阿里), DeepSeek
├── 训练框架: PyTorch(Meta), JAX(Google), TensorFlow
└── 推理优化: vLLM, TensorRT-LLM, ONNX Runtime

[下游：应用与服务层]
├── 企业应用: Microsoft(Copilot), Salesforce(Einstein)
├── 开发工具: GitHub Copilot, Cursor, Replit
├── 内容创作: Midjourney, Runway, Suno
├── 搜索与信息: Perplexity, You.com, New Bing
└── 垂直领域: 医疗(Hippocratic), 法律(Harvey), 金融(BloombergGPT)

[横向：安全与治理]
├── AI安全: Anthropic, ARC, MIRI
├── 合规工具: Arthur.ai, CalypsoAI
└── 标准组织: ISO/IEC, NIST, IEEE
```

### 4. 分析要求（升级版）
请对所有新闻进行深度关联分析，返回完整JSON数组。每条新闻必须包含：

**基础字段**（必填）：
- title, summary, source, signal_type, content_tier, overall_score
- who, what, where, when, why, how, implications

**关联分析字段**（新增重点）：
1. **historical_context**: 与上述历史事件的关联
   - 格式: "这与[事件]类似，当时[结果]，本次可能[预测]"
   
2. **competitor_reactions**: 预测竞品反应
   - 格式: {"OpenAI": "可能反应", "Anthropic": "可能反应", ...}
   
3. **industry_chain_position**: 在产业链中的位置
   - 格式: "上游/中游/下游 - [具体环节] - 影响[上下游]"
   
4. **write_angles**: 3个写稿角度（更具体）
   - 数据向、分析向、人物向、趋势向、对比向
   
5. **actionable_for_editor**: 编辑行动建议
   - 需要补充的数据源、可以采访的对象、关注的时间节点

6. **core_highlight**: 一句话核心洞察（用于Notion素材库）
   - 格式: "[实体] [动作] + [意义/影响]"

**评分标准**：
- GOLD (8.0+): 官方一手信源 + 模型突破/架构创新 + 多源共振
- SILVER (6.0+): 权威媒体 + 行业里程碑/融资 + 有一定热度
- BRONZE (4.0+): 一般资讯但有参考价值
- FILTER (<4.0): 噪音/营销/套壳内容

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
                        
                        item.historical_context = a.get("historical_context", "")
                        item.competitor_reactions = a.get("competitor_reactions", {})
                        item.industry_chain_position = a.get("industry_chain_position", "")
                        
                        item.fact_checks = a.get("fact_checks", [])
                        item.source_chain = a.get("source_chain", [])
                        
                        item.actionable_for_editor = a.get("actionable_for_editor", "")
                        item.draft_angles = a.get("draft_angles", [])
                        
                        item.editor_note = a.get("editor_note", "")
                        
                        scores = a.get("scores", {})
                        if isinstance(scores, dict):
                            item.attention_score = float(scores.get("attention_score", 0))
                            item.tech_depth_score = float(scores.get("tech_depth_score", 0))
                            item.industry_impact_score = float(scores.get("industry_impact_score", 0))
                        
                        item.intelligence_grade = a.get("intelligence_grade", "")
                        
                        item.why_it_matters = a.get("why_it_matters", "")
                        item.significance_level = a.get("significance_level", "")
                        item.key_takeaways = a.get("key_takeaways", [])
                        item.context_gap = a.get("context_gap", "")
                        
                        item.action_plan = a.get("action_plan", {})
                        item.next_steps = a.get("next_steps", [])
                        item.people_to_follow = a.get("people_to_follow", [])
                        item.directions_to_watch = a.get("directions_to_watch", [])
                        item.time_sensitivity = a.get("time_sensitivity", "")
                
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
            
            entities = extract_entities("%s %s" % (item.title, item.summary))
            
            item.core_highlight = "[%s] %s" % (item.signal_type.value.replace("_", " ").title(), item.title[:80])
            
            historical = ""
            if "OpenAI" in entities and item.signal_type == SignalType.MODEL_BREAKTHROUGH:
                historical = "类似2023年3月GPT-4发布时的行业震动，当时引发多模态竞赛。本次可能触发新一轮模型能力对标。"
            elif "Anthropic" in entities and "funding" in (item.title + item.summary).lower():
                historical = "类似OpenAI 2024年9月融资潮（估值1500亿+），显示资本市场对AI安全赛道的持续信心。"
            elif "NVIDIA" in entities:
                historical = "类似2024年GTC大会Blackwell发布，每次GPU架构更新都影响整个AI训练成本曲线。"
            else:
                historical = "需结合历史事件库进一步分析关联性"
            item.historical_context = historical
            
            reactions = {}
            if entities:
                primary_entity = entities[0] if entities else ""
                
                if primary_entity == "OpenAI":
                    reactions = {
                        "Anthropic": "可能强调Claude的安全优势或发布对标功能",
                        "Google": "可能加速Gemini更新节奏或在Google I/O上重点展示",
                        "Meta": "可能推进Llama开源版本以保持生态竞争力",
                        "其他": "集成商将快速适配新API"
                    }
                elif primary_entity == "Anthropic":
                    reactions = {
                        "OpenAI": "可能低调回应或强调用户规模优势",
                        "Google": "可能突出Gemini的多模态整合",
                        "Meta": "继续开源差异化策略"
                    }
                elif primary_entity == "Google DeepMind":
                    reactions = {
                        "OpenAI": "可能发布对比基准测试",
                        "Anthropic": "可能强调研究方法的差异",
                        "Meta": "可能加速开源模型迭代"
                    }
                elif "funding" in (item.title + item.summary).lower() or "融资" in item.title:
                    reactions = {
                        "同行": "可能引发新一轮融资竞赛",
                        "投资人": "关注点转向商业化落地能力",
                        "监管": "大型AI公司可能面临更多审查"
                    }
                else:
                    reactions = {"待分析": "需要更多上下文来预测竞品反应"}
            item.competitor_reactions = reactions
            
            chain_pos = ""
            if item.signal_type in [SignalType.MODEL_BREAKTHROUGH, SignalType.ARCHITECTURE_INNOVATION]:
                chain_pos = "中游(模型层) - 基础模型突破 - 影响下游所有应用场景"
            elif item.signal_type == SignalType.PRACTICAL_TOOLCHAIN:
                chain_pos = "中下游(工具层) - 开发/部署工具 - 降低应用门槛"
            elif item.signal_type == SignalType.FUNDING_ACQUISITION:
                chain_pos = "横向(资本层) - 融资/并购 - 影响全产业链资源配置"
            elif item.signal_type == SignalType.POLICY_REGULATION:
                chain_pos = "横向(治理层) - 政策/合规 - 影响所有市场参与者"
            elif "chip" in (item.title + item.summary).lower() or "gpu" in (item.title + item.summary).lower() or "NVIDIA" in entities:
                chain_pos = "上游(算力层) - 芯片/基础设施 - 制约模型训练规模和成本"
            else:
                chain_pos = "待定位 - 需要更多信息确定产业链位置"
            item.industry_chain_position = chain_pos
            
            item.industry_impact = (
                "短期：可能引发行业关注；"
                "中期：视具体落地情况而定；"
                "长期：需要持续观察"
            )
            
            item.comparison_context = "待Gemini分析后补充对比信息"
            
            item.actionable_for_editor = (
                "1. 追踪此事件的后续发展\n"
                "2. 收集官方公告和第三方分析\n"
                "3. 关注竞品在48-72小时内的反应\n"
                "4. 准备采访相关领域的专家意见"
            )
            
            item.draft_angles = [
                "事件概述与核心事实梳理: %s" % item.title[:50],
                "%s视角的深度分析" % (entities[0] if entities else "行业"),
                "产业链影响评估与趋势预判",
                "竞品反应追踪与市场格局变化"
            ]
            
            item.fact_checks = [{
                "claim": item.title[:50],
                "status": "[待验证]",
                "confidence": 0.5
            }]
            
            build_evidence_chain(item, items)
    
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
        
        curated = event_dedup(curated)
        
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
        brief_report = _format_brief_report(display_items, category)
        action_report = _format_action_plan(display_items, category)
        
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
        
        items_with_evidence = []
        for c in display_items:
            item_dict = asdict(c)
            if c.source_tier:
                item_dict["evidence_chain"] = {
                    "source_tier": c.source_tier,
                    "source_credibility": c.source_credibility,
                    "cross_source_count": c.cross_source_count,
                    "single_source_warning": c.single_source_warning,
                    "fact_count": len(c.fact_parts),
                    "inference_count": len(c.inference_parts),
                    "fact_samples": c.fact_parts[:3],
                    "inference_samples": c.inference_parts[:3],
                    "unverified_samples": c.unverified_claims[:2],
                    "publish_time": c.publish_time,
                    "source_freshness": c.source_freshness,
                    "is_official_source": c.is_official_source,
                    "is_repost": c.is_repost,
                    "original_domain": c.original_domain,
                    "conflicting_info": c.conflicting_info
                }
            else:
                item_dict["evidence_chain"] = None
            items_with_evidence.append(item_dict)
        
        return {
            "count": len(display_items),
            "tier_breakdown": {
                "gold": gold_count,
                "silver": silver_count,
                "bronze": bronze_count,
                "filtered": filtered_count
            },
            "report": report,
            "brief_report": brief_report,
            "action_report": action_report,
            "items": items_with_evidence,
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
            
            if item.source_tier:
                tier_icon = "[OK]" if not item.single_source_warning else "[!]"
                cred_label = "HIGH" if item.source_credibility >= 75 else ("MEDIUM" if item.source_credibility >= 50 else "LOW")
                official_tag = " [官方]" if item.is_official_source else ""
                repost_tag = " [转载]" if item.is_repost else ""
                freshness_icon = {"FRESH": "🟢", "RECENT": "🟡", "STALE": "🟠", "OLD": "🔴"}.get(item.source_freshness, "")
                
                body += "📎 可信度: %s %s%s%s (%.0f%%)" % (tier_icon, cred_label, official_tag, repost_tag, item.source_credibility)
                if freshness_icon:
                    body += " %s" % freshness_icon
                if item.cross_source_count > 0:
                    body += " | 交叉验证: %d源" % item.cross_source_count
                elif item.single_source_warning:
                    body += " | [单一来源警告]"
                if item.publish_time and item.publish_time != "unknown":
                    body += " | 时效: %s" % item.publish_time
                if item.conflicting_info:
                    body += " | ⚠️ 冲突%d条" % len(item.conflicting_info)
                body += "\n"
            
            body += "🔗 [原文](%s)\n\n" % item.link
        
        body += "---\n\n"
    
    footer = """
_*Editor v3.0: 深度降噪 + 关联分析 + 写稿辅助*_
_信噪比优化: 已过滤噪音内容_"""
    
    return header + body + footer


def _format_brief_report(items: list[CuratedItem], category: str) -> str:
    now = datetime.now(timezone(timedelta(hours=8)))
    
    s_items = sorted(items, key=lambda x: (
        x.attention_score or x.overall_score or 0
    ), reverse=True)
    
    top_items = [i for i in s_items if i.intelligence_grade in ("S", "A")][:8]
    other_items = [i for i in s_items if i.intelligence_grade not in ("S", "A")][:10]
    
    header = """**⚡ 今日速报 — OpenNews Intelligence v3.0**
_%s | %s | %d条情报_

━━━ 🚨 S/A级 变局/重大 ━━━
""" % (now.strftime("%Y-%m-%d %H:%M"), category.upper(), len(items))
    
    body = ""
    
    for i, item in enumerate(top_items, 1):
        grade_icon = {"S": "🔴", "A": "🟠"}.get(item.intelligence_grade, "⚪")
        attn = item.attention_score or item.overall_score or 0
        
        body += "%s **%d.** %s `%.1f`\n" % (grade_icon, i, item.title[:70], attn)
        
        if item.what:
            body += "   %s\n" % item.what[:100]
        
        if item.key_takeaways:
            tk_str = " · ".join(item.key_takeaways[:3])
            body += "   💡 %s\n" % tk_str
        
        if item.merged_sources:
            src_tag = "[%d源]" % len(item.merged_sources)
            body += "   📎 %s %s\n" % (item.source, src_tag)
        
        body += "\n"
    
    if other_items:
        body += """━━━ 📋 值得了解 ━━━\n"""
        for item in other_items[:8]:
            grade_icon = {"B": "🟡", "C": "⚪", "D": "⚫"}.get(item.intelligence_grade, "·")
            body += "%s %s `%s`\n" % (grade_icon, item.title[:60], item.signal_type.value.upper()[:4])
        body += "\n"
    
    s_count = sum(1 for i in items if i.intelligence_grade == "S")
    a_count = sum(1 for i in items if i.intelligence_grade == "A")
    merged_count = sum(1 for i in items if i.is_merged_event)
    
    footer = (
        "_S:%d A:%d | 去重合并: %d事件_"
        "_数据源: 55+ RSS | Engine: Gemini v3.0_"
        % (s_count, a_count, merged_count)
    )
    
    return header + body + footer


def _format_action_plan(items: list[CuratedItem], category: str) -> str:
    now = datetime.now(timezone(timedelta(hours=8)))
    
    now_actions = []
    week_actions = []
    month_actions = []
    monitor_actions = []
    
    all_people = set()
    all_directions = set()
    
    for item in items:
        if not item.next_steps and not item.time_sensitivity:
            continue
        
        ts = item.time_sensitivity or "MONITOR"
        
        entry = {
            "title": item.title,
            "grade": item.intelligence_grade or "?",
            "steps": item.next_steps or [],
            "people": item.people_to_follow or [],
            "directions": item.directions_to_watch or [],
            "why": item.why_it_matters or "",
            "time_sensitivity": ts,
            "attention": item.attention_score or 0
        }
        
        if ts == "NOW":
            now_actions.append(entry)
        elif ts == "THIS_WEEK":
            week_actions.append(entry)
        elif ts == "THIS_MONTH":
            month_actions.append(entry)
        else:
            monitor_actions.append(entry)
        
        for p in entry["people"]:
            all_people.add(p)
        for d in entry["directions"]:
            all_directions.add(d)
    
    now_actions.sort(key=lambda x: x["attention"], reverse=True)
    week_actions.sort(key=lambda x: x["attention"], reverse=True)
    
    header = """**🎯 行动建议 — OpenNews Intelligence v3.0**
_%s | %s_

""" % (now.strftime("%Y-%m-%d %H:%M"), category.upper())
    
    body = ""
    
    if now_actions:
        body += "**🔥 立即行动 (NOW)**\n\n"
        for i, action in enumerate(now_actions[:5], 1):
            grade_icon = {"S": "🔴", "A": "🟠", "B": "🟡"}.get(action["grade"], "⚪")
            body += "%s **%d.** %s\n" % (grade_icon, i, action["title"][:65])
            
            for step in action["steps"][:3]:
                body += "   ▶️ %s\n" % step
            
            if action["people"]:
                body += "   👤 跟踪: %s\n" % ", ".join(action["people"][:2])
            
            if action["directions"]:
                body += "   🔭 关注: %s\n" % "; ".join(action["directions"][:2])
            
            body += "\n"
    
    if week_actions:
        body += "**📅 本周内完成 (THIS WEEK)**\n\n"
        for action in week_actions[:4]:
            body += "• **%s** [%s]\n" % (action["title"][:55], action["grade"])
            for step in action["steps"][:2]:
                body += "  ▶️ %s\n" % step
            body += "\n"
    
    if month_actions:
        body += "**📆 本月跟踪 (THIS_MONTH)**\n\n"
        for action in month_actions[:3]:
            body += "• %s [%s]\n" % (action["title"][:50], action["grade"])
        body += "\n"
    
    if monitor_actions:
        body += "**👁 长期监控 (MONITOR)**\n\n"
        monitored_titles = [a["title"][:50] for a in monitor_actions[:6]]
        body += "• " + "\n• ".join(monitored_titles) + "\n\n"
    
    body += "**━━ 跟踪清单 ━─**\n\n"
    
    if all_people:
        body += "**👤 关键人物/账号:**\n"
        for p in sorted(all_people)[:8]:
            body += "  • %s\n" % p
        body += "\n"
    
    if all_directions:
        body += "**🔭 关注方向:**\n"
        for d in sorted(all_directions)[:6]:
            body += "  • %s\n" % d
        body += "\n"
    
    total_actions = len(now_actions) + len(week_actions) + len(month_actions)
    footer = "_共 %d 条行动建议 | NOW: %d | WEEK: %d | MONTH: %d_" % (
        total_actions, len(now_actions), len(week_actions), len(month_actions)
    )
    
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
