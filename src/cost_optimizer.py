import asyncio
import time
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from enum import Enum
from dataclasses import dataclass

try:
    from editor_assistant import (
        CuratedItem, ContentTier, SignalType,
        detect_signal_type, calculate_content_tier,
        call_gemini_editor, _check_cache, _store_in_cache
    )
except ImportError:
    from src.editor_assistant import (
        CuratedItem, ContentTier, SignalType,
        detect_signal_type, calculate_content_tier,
        call_gemini_editor, _check_cache, _store_in_cache
    )


class ProcessingLevel(Enum):
    RULE_BASED = "rule_based"      # 纯规则，零成本
    LIGHTWEIGHT = "lightweight"     # 轻量规则+简单模板
    STANDARD = "standard"           # 标准Gemini调用（缓存优先）
    DEEP = "deep"                   # 深度分析（高价值内容）


@dataclass
class CostMetrics:
    total_items: int = 0
    rule_based_count: int = 0
    lightweight_count: int = 0
    standard_count: int = 0
    deep_count: int = 0
    
    gemini_calls: int = 0
    cache_hits: int = 0
    estimated_tokens: int = 0
    
    processing_time_ms: float = 0.0
    cost_savings_percent: float = 0.0


LIGHTWEIGHT_TEMPLATES = {
    SignalType.MODEL_BREAKTHROUGH: {
        "core_highlight_template": "核心模型发布：{entity}推出{model}，{key_feature}",
        "industry_impact_template": "短期：市场竞争加剧；中期：API定价可能调整；长期：可能改变{domain}格局",
        "draft_angles": [
            "技术向：{model}架构解析与性能评测",
            "商业向：{model}对{domain}市场的冲击分析",
            "行业向：2026年{domain}竞争格局展望"
        ]
    },
    SignalType.FUNDING_ACQUISITION: {
        "core_highlight_template": "融资/并购：{company}完成{round}，估值达{valuation}",
        "industry_impact_template": "短期：资本加速流入{sector}；中期：可能引发整合潮；长期：头部效应加剧",
        "draft_angles": [
            "数据向：{company}融资历程与业务布局梳理",
            "分析向：{sector}赛道投资热度与趋势判断",
            "深度向：从{round}看{sector}的下一个增长点"
        ]
    },
    SignalType.POLICY_REGULATION: {
        "core_highlight_template": "政策动态：{region}发布{policy}，影响{scope}",
        "industry_impact_template": "短期：企业合规成本上升；中期：市场格局重塑；长期：可能形成新的准入壁垒",
        "draft_angles": [
            "政策向：{policy}核心条款解读与合规要点",
            "行业向：对国内外AI企业的差异化影响",
            "前瞻向：全球AI监管趋势对比与中国应对"
        ]
    },
    SignalType.ARCHITECTURE_INNOVATION: {
        "core_highlight_template": "架构创新：{team}提出{innovation}，解决{problem}",
        "industry_impact_template": "短期：学术界关注；中期：工业界跟进落地；长期：可能成为新范式",
        "draft_angles": [
            "技术向：{innovation}原理解析与技术细节",
            "应用向：从论文到产品的落地路径分析",
            "对比向：与现有主流方案({existing})的优劣比较"
        ]
    },
}


def route_processing_level(item: dict, curated_item: CuratedItem) -> ProcessingLevel:
    
    signal_type = curated_item.signal_type
    content_tier = curated_item.content_tier
    confidence = 0.7
    resonance = item.get("resonance_count", 1)
    
    if signal_type in [SignalType.WRAPPER_PROJECT, SignalType.MARKETING_HYPE, SignalType.NOISE]:
        if content_tier == ContentTier.FILTER:
            return ProcessingLevel.RULE_BASED
        return ProcessingLevel.LIGHTWEIGHT
    
    if content_tier == ContentTier.GOLD:
        if resonance >= 3 or signal_type == SignalType.MODEL_BREAKTHROUGH:
            return ProcessingLevel.DEEP
        return ProcessingLevel.STANDARD
    
    if content_tier == ContentTier.SILVER:
        if resonance >= 2:
            return ProcessingLevel.STANDARD
        return ProcessingLevel.LIGHTWEIGHT
    
    if content_tier == ContentTier.BRONZE:
        return ProcessingLevel.LIGHTWEIGHT
    
    return ProcessingLevel.RULE_BASED


async def lightweight_analyze(item: CuratedItem) -> CuratedItem:
    
    template = LIGHTWEIGHT_TEMPLATES.get(item.signal_type)
    
    if template:
        
        title_parts = item.title.split()
        entity = title_parts[0] if title_parts else "某公司"
        model_match = __import__('re').search(r'(GPT-\d|Claude \d|Llama \d|Gemini \d\.\d|Qwen)', item.title)
        model = model_match.group(0) if model_match else "新模型"
        
        item.core_highlight = template["core_highlight_template"].format(
            entity=entity,
            model=model,
            key_feature="关键特性待补充",
            company=entity,
            round="新一轮融资",
            valuation="未披露",
            sector="相关",
            region="某地区",
            policy="新政策",
            scope="相关领域",
            team=entity,
            innovation="新技术",
            problem="核心问题",
            existing="现有方案"
        )
        
        item.industry_impact = template["industry_impact_template"].format(
            domain="相关",
            sector="相关",
            scope="相关领域"
        )
        
        item.draft_angles = [angle.format(
            model=model,
            domain="相关",
            sector="相关",
            company=entity,
            round="融资轮次",
            policy="政策名称",
            innovation="技术创新",
            existing="现有方案"
        ) for angle in template["draft_angles"]]
    
    else:
        
        item.core_highlight = "[%s] %s" % (item.signal_type.value.replace("_", " ").title(), item.title[:80])
        item.industry_impact = "待深度分析后补充"
        item.draft_angles = [
            "事件概述：%s" % item.title[:50],
            "行业影响分析",
            "技术/商业角度解读"
        ]
    
    item.actionable_for_editor = "建议关注此事件发展，如需深度分析请使用 /editor 命令"
    
    item.fact_checks = [{
        "claim": item.title[:50],
        "status": "[待验证]",
        "confidence": 0.5
    }]
    
    return item


async def cost_optimized_process(items: list[dict]) -> tuple[list[CuratedItem], CostMetrics]:
    
    start_time = time.time()
    metrics = CostMetrics(total_items=len(items))
    
    from editor_assistant import deep_curate
    curated = await deep_curate(items)
    
    routing_stats = {
        ProcessingLevel.RULE_BASED: [],
        ProcessingLevel.LIGHTWEIGHT: [],
        ProcessingLevel.STANDARD: [],
        ProcessingLevel.DEEP: []
    }
    
    for i, item in enumerate(curated):
        level = route_processing_level(items[i], item)
        routing_stats[level].append((i, item))
    
    metrics.rule_based_count = len(routing_stats[ProcessingLevel.RULE_BASED])
    metrics.lightweight_count = len(routing_stats[ProcessingLevel.LIGHTWEIGHT])
    metrics.standard_count = len(routing_stats[ProcessingLevel.STANDARD])
    metrics.deep_count = len(routing_stats[ProcessingLevel.DEEP])
    
    print("\n[CostOptimizer] Routing Results:")
    print("  Rule-Based (零成本):   %d items" % metrics.rule_based_count)
    print("  Lightweight (模板):    %d items" % metrics.lightweight_count)
    print("  Standard (Gemini):     %d items" % metrics.standard_count)
    print("  Deep (深度分析):       %d items" % metrics.deep_count)
    
    for idx, item in routing_stats[ProcessingLevel.LIGHTWEIGHT]:
        curated[idx] = await lightweight_analyze(item)
    
    standard_and_deep_items = (
        routing_stats[ProcessingLevel.STANDARD] + 
        routing_stats[ProcessingLevel.DEEP]
    )
    
    if standard_and_deep_items:
        high_value_items = [curated[idx] for idx, _ in standard_and_deep_items]
        
        from editor_assistant import gemini_deep_analyze
        analyzed = await gemini_deep_analyze(high_value_items)
        
        analyzed_map = {c.id: c for c in analyzed}
        
        for idx, _ in standard_and_deep_items:
            if curated[idx].id in analyzed_map:
                curated[idx] = analyzed_map[curated[idx].id]
        
        metrics.gemini_calls += 1
        metrics.estimated_tokens += len(str(standard_and_deep_items)) * 2
    
    elapsed_ms = (time.time() - start_time) * 1000
    metrics.processing_time_ms = elapsed_ms
    
    total_possible_gemini_calls = len(items)
    actual_gemini_calls = metrics.gemini_calls
    if total_possible_gemini_calls > 0:
        metrics.cost_savings_percent = ((total_possible_gemini_calls - actual_gemini_calls) / total_possible_gemini_calls) * 100
    
    print("[CostOptimizer] Performance:")
    print("  Total time: %.1fms" % elapsed_ms)
    print("  Gemini calls saved: %d/%d (%.1f%% savings)" % (
        total_possible_gemini_calls - actual_gemini_calls,
        total_possible_gemini_calls,
        metrics.cost_savings_percent
    ))
    
    return curated, metrics


async def run_cost_optimized_report(category: str = "tech", chat_id: str = None,
                                    max_items: int = 30) -> dict:
    print("\n[CostOptimizer] === Starting Cost-Optimized Analysis ===")
    
    try:
        from aggregator_rss import aggregate as rss_aggregate
        result = await rss_aggregate(
            category=category,
            max_items=max_items,
            enable_resonance=True
        )
        
        if not result or "items" not in result:
            return {"count": 0, "report": "*无法获取新闻数据*", "items": [], "metrics": {}}
        
        items = result["items"]
        print("[CostOptimizer] Raw items: %d" % len(items))
        
        curated, metrics = await cost_optimized_process(items)
        
        display_items = [c for c in curated if c.content_tier != ContentTier.FILTER]
        
        from editor_assistant import _format_editor_report
        report = _format_editor_report(display_items, category)
        
        return {
            "count": len(display_items),
            "report": report,
            "items": [__import__('dataclasses').asdict(c) for c in display_items],
            "metrics": {
                "total_items": metrics.total_items,
                "routing": {
                    "rule_based": metrics.rule_based_count,
                    "lightweight": metrics.lightweight_count,
                    "standard": metrics.standard_count,
                    "deep": metrics.deep_count
                },
                "gemini_calls": metrics.gemini_calls,
                "cost_savings": "%.1f%%" % metrics.cost_savings_percent,
                "processing_time": "%.1fms" % metrics.processing_time_ms
            }
        }
        
    except Exception as e:
        print("[CostOptimizer] Error: %s" % e)
        import traceback
        traceback.print_exc()
        return {"count": 0, "report": "*生成失败: %s*" % str(e)[:100], "items": [], "metrics": {}}


if __name__ == "__main__":
    import asyncio
    
    async def test():
        from aggregator_rss import aggregate as rss_aggregate
        
        result = await rss_aggregate(category="tech", max_items=20, enable_resonance=True)
        items = result.get("items", [])
        
        print("\n=== Cost Optimizer Test ===")
        print("Input items: %d" % len(items))
        
        curated, metrics = await cost_optimized_process(items)
        
        print("\n=== Metrics ===")
        print("Total items:", metrics.total_items)
        print("Rule-based:", metrics.rule_based_count)
        print("Lightweight:", metrics.lightweight_count)
        print("Standard:", metrics.standard_count)
        print("Deep:", metrics.deep_count)
        print("Cost savings: %.1f%%" % metrics.cost_savings_percent)
        print("Processing time: %.1fms" % metrics.processing_time_ms)
    
    asyncio.run(test())
