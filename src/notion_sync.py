import os
import json
import time
import httpx
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent

NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")

if not NOTION_API_KEY:
    try:
        env_file = project_root / ".env"
        if env_file.exists():
            content = env_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("NOTION_API_KEY=") and not line.startswith("#"):
                    NOTION_API_KEY = line.split("=", 1)[1].strip().strip("'\"")
                if line.startswith("NOTION_DATABASE_ID=") and not line.startswith("#"):
                    NOTION_DATABASE_ID = line.split("=", 1)[1].strip().strip("'\"")
    except Exception:
        pass

NOTION_BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


@dataclass
class NotionPage:
    id: str = ""
    title: str = ""
    tier: str = "BRONZE"
    url: str = ""
    core_insight: str = ""
    tags: list[str] = None
    signal_type: str = ""
    source: str = ""
    published_at: str = ""
    industry_impact: str = ""
    draft_angles: list[str] = None
    actionable_for_editor: str = ""
    fact_checks: list[dict] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.draft_angles is None:
            self.draft_angles = []
        if self.fact_checks is None:
            self.fact_checks = []


def get_headers() -> dict:
    return {
        "Authorization": "Bearer %s" % NOTION_API_KEY,
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION
    }


async def search_databases(query: str = "") -> Optional[list[dict]]:
    if not NOTION_API_KEY:
        print("[Notion] No API key configured")
        return None
    
    url = "%s/search" % NOTION_BASE_URL
    
    payload = {
        "query": query,
        "filter": {"property": "object", "value": "database"}
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=get_headers(), json=payload)
            
            if response.status_code == 200:
                result = response.json()
                databases = result.get("results", [])
                
                print("[Notion] Found %d database(s)" % len(databases))
                for db in databases:
                    title = ""
                    title_obj = db.get("title", [])
                    if title_obj:
                        title = "".join([t["plain_text"] for t in title_obj])
                    
                    db_id = db.get("id", "")
                    print("  - [%s] %s" % (db_id[:8], title))
                
                return databases
                
            else:
                print("[Notion] Search error: %d - %s" % (response.status_code, response.text[:200]))
                return None
                
    except Exception as e:
        print("[Notion] Connection error: %s" % e)
        return None


async def get_database_schema(database_id: str = None) -> Optional[dict]:
    db_id = database_id or NOTION_DATABASE_ID
    
    if not db_id or not NOTION_API_KEY:
        print("[Notion] Missing database ID or API key")
        return None
    
    url = "%s/databases/%s" % (NOTION_BASE_URL, db_id)
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=get_headers())
            
            if response.status_code == 200:
                result = response.json()
                
                title = ""
                title_obj = result.get("title", [])
                if title_obj:
                    title = "".join([t["plain_text"] for t in title_obj])
                
                properties = result.get("properties", {})
                
                print("\n[Notion] Database: %s" % title)
                print("[Notion] ID: %s" % db_id)
                print("[Notion] Properties (%d):" % len(properties))
                
                for prop_name, prop_info in properties.items():
                    prop_type = prop_info.get("type", "unknown")
                    print("  - %s (%s)" % (prop_name, prop_type))
                
                return result
                
            else:
                print("[Notion] Get database error: %d - %s" % (response.status_code, response.text[:200]))
                return None
                
    except Exception as e:
        print("[Notion] Connection error: %s" % e)
        return None


def _sanitize_text(text: str, max_length: int = 2000) -> str:
    if not text:
        return ""
    text = text.replace("\n", " ").replace("\r", " ")
    text = " ".join(text.split())
    if len(text) > max_length:
        text = text[:max_length-3] + "..."
    return text


def _build_page_properties(item: dict) -> dict:
    
    title = item.get("title", "")[:100]
    tier = item.get("tier", "BRONZE").upper()
    if tier not in ["GOLD", "SILVER", "BRONZE"]:
        tier = "BRONZE"
    
    url = item.get("link", "")
    
    core_insight = item.get("core_highlight", "") or item.get("what", "")
    core_insight = _sanitize_text(core_insight, 2000)
    
    tags = item.get("tags", []) or []
    tags = [str(t) for t in tags if t]
    tags = tags[:10]
    
    categories = item.get("categories", []) or []
    all_tags = list(set(tags + categories))[:15]
    
    raw_signal = item.get("signal_type", "")
    if hasattr(raw_signal, 'value'):
        signal_type = raw_signal.value.replace("_", " ").title()
    else:
        signal_type = str(raw_signal).replace("_", " ").title()
    source = item.get("source", "")
    
    published_at = item.get("published_at", "")
    industry_impact = _sanitize_text(item.get("industry_impact", ""), 1500)
    
    draft_angles = item.get("draft_angles", []) or []
    angles_str = "\n".join(["• %s" % a for a in draft_angles[:3]]) if draft_angles else ""
    
    actionable = _sanitize_text(item.get("actionable_for_editor", ""), 500)
    
    fact_checks = item.get("fact_checks", []) or []
    fc_str = "\n".join([
        "- %s [%s]" % (fc.get("claim", "")[:50], fc.get("status", "[待验证]"))
        for fc in fact_checks[:5]
    ]) if fact_checks else ""
    
    who = _sanitize_text(item.get("who", ""), 300)
    what = _sanitize_text(item.get("what", ""), 500)
    why = _sanitize_text(item.get("why", ""), 500)
    how = _sanitize_text(item.get("how", ""), 500)
    implications = _sanitize_text(item.get("implications", ""), 500)
    
    overall_score = item.get("overall_score", 0)
    
    now_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    insight_full = """**核心洞察**: %s

**Who**: %s
**What**: %s  
**Why**: %s
**How**: %s
**Implications**: %s

**信号类型**: %s | **来源**: %s | **评分**: %.1f/10

---
**行业影响**:
%s

**写稿角度**:
%s

**下一步行动**:
%s

**事实核查**:
%s

---
_由 OpenNews Editor v3.0 自动生成 | %s_""" % (
        core_insight or "待补充",
        who, what, why, how, implications,
        signal_type, source, overall_score,
        industry_impact or "待分析",
        angles_str or "待生成",
        actionable or "待建议",
        fc_str or "暂无",
        now_str
    )
    
    properties = {
        "NAME": {
            "title": [{"text": {"content": title}}]
        },
        "等级": {
            "select": {"name": tier}
        }
    }
    
    if url:
        properties["URL"] = {
            "rich_text": [{"text": {"content": url[:500]}}]
        }
    
    properties["TEXT"] = {
        "rich_text": [{"text": {"content": insight_full[:1900]}}]
    }
    
    if all_tags:
        properties["分类"] = {
            "multi_select": [{"name": tag[:40]} for tag in all_tags]
        }
    
    properties["DATE"] = {
        "date": {"start": now_str[:10]}
    }
    
    children = []
    
    if core_insight:
        children.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": "💡"},
                "rich_text": [{"type": "text", "text": {"content": core_insight[:1900]}}]
            }
        })
    
    if industry_impact:
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Industry Impact Analysis"}}]
            }
        })
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": industry_impact[:1900]}}]
            }
        })
    
    if draft_angles:
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Draft Angles"}}]
            }
        })
        for angle in draft_angles[:3]:
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": angle[:900]}}]
                }
            })
    
    if actionable:
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Next Actions"}}]
            }
        })
        children.append({
            "object": "block",
            "type": "to_do",
            "to_do": {
                "rich_text": [{"type": "text", "text": {"content": actionable[:900]}}],
                "checked": False
            }
        })
    
    if fact_checks:
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Fact Check"}}]
            }
        })
        for fc in fact_checks[:5]:
            status_icon = "[Verified]" if "官方" in fc.get("status", "") else "[Pending]"
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{
                        "type": "text",
                        "text": {
                            "content": "%s %s %s" % (
                                status_icon,
                                fc.get("claim", "")[:80],
                                fc.get("status", "[待验证]")
                            )
                        }
                    }]
                }
            })
    
    children.append({
        "object": "block",
        "type": "divider",
        "divider": {}
    })
    
    children.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{
                "type": "text",
                "text": {
                    "content": "[Auto-generated by OpenNews Editor v3.0 | %s]" % now_str
                }
            }]
        }
    })
    
    return {
        "properties": properties,
        "children": children
    }


async def create_page(item: dict, database_id: str = None) -> Optional[NotionPage]:
    db_id = database_id or NOTION_DATABASE_ID
    
    if not db_id or not NOTION_API_KEY:
        print("[Notion] Missing database ID or API key")
        return None
    
    url = "%s/pages" % NOTION_BASE_URL
    
    page_data = _build_page_properties(item)
    
    payload = {
        "parent": {"database_id": db_id},
        "properties": page_data["properties"],
        "children": page_data["children"]
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=get_headers(), json=payload)
            
            if response.status_code == 200:
                result = response.json()
                page_id = result.get("id", "")
                page_url = result.get("url", "")
                
                print("[Notion] Page created: %s" % item.get("title", "")[:50])
                print("[Notion] URL: %s" % page_url)
                
                return NotionPage(
                    id=page_id,
                    title=item.get("title", ""),
                    tier=item.get("tier", "BRONZE"),
                    url=page_url,
                    core_insight=item.get("core_highlight", ""),
                    tags=item.get("tags", []),
                    signal_type=item.get("signal_type", ""),
                    source=item.get("source", ""),
                    published_at=item.get("published_at", "")
                )
                
            elif response.status_code == 404:
                print("[Notion] Database not found (404). Check NOTION_DATABASE_ID")
                return None
                
            elif response.status_code == 401 or response.status_code == 403:
                print("[Notion] Auth error (%d). Check NOTION_API_KEY permissions" % response.status_code)
                return None
                
            else:
                print("[Notion] Create page error: %d" % response.status_code)
                print("[Notion] Response: %s" % response.text[:300])
                return None
                
    except httpx.TimeoutException:
        print("[Notion] Timeout creating page")
        return None
    except Exception as e:
        print("[Notion] Error creating page: %s" % e)
        return None


async def batch_create_pages(items: list[dict], database_id: str = None, 
                             delay_seconds: float = 0.5) -> dict:
    
    db_id = database_id or NOTION_DATABASE_ID
    
    if not items:
        return {"success": 0, "failed": 0, "pages": [], "error": "No items to sync"}
    
    results = {
        "success": 0,
        "failed": 0,
        "pages": [],
        "errors": []
    }
    
    total = len(items)
    print("\n[Notion] Starting batch sync: %d items → Database: %s..." % (total, (db_id or "None")[:12]))
    
    for i, item in enumerate(items, 1):
        print("[Notion] Syncing %d/%d: %s" % (i, total, item.get("title", "")[:40]))
        
        page = await create_page(item, db_id)
        
        if page:
            results["success"] += 1
            results["pages"].append(asdict(page))
        else:
            results["failed"] += 1
            results["errors"].append({
                "item": item.get("title", "")[:50],
                "reason": "API error or auth failure"
            })
        
        if i < total and delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
    
    print("\n[Notion] Batch sync complete:")
    print("  Success: %d/%d" % (results["success"], total))
    print("  Failed: %d/%d" % (results["failed"], total))
    
    return results


import asyncio


async def setup_notion_database():
    print("\n=== Notion Setup Tool ===\n")
    
    if not NOTION_API_KEY:
        print("[FAIL] NOTION_API_KEY not configured")
        print("   Add it to .env file:")
        print("   NOTION_API_KEY=ntn_your_key_here")
        return
    
    print("[OK] API Key configured: %s...%s" % (NOTION_API_KEY[:8], NOTION_API_KEY[-4:]))
    
    if NOTION_DATABASE_ID:
        print("[OK] Database ID configured: %s" % NOTION_DATABASE_ID)
        print("\nFetching database schema...")
        schema = await get_database_schema(NOTION_DATABASE_ID)
        if schema:
            print("\n[OK] Database accessible! Ready to sync.")
        return
    
    print("\n[FAIL] NOTION_DATABASE_ID not set")
    print("\nSearching for your databases...")
    
    dbs = await search_databases("")
    
    if dbs:
        print("\n[DB] Available databases:")
        for db in dbs:
            title = ""
            title_obj = db.get("title", [])
            if title_obj:
                title = "".join([t["plain_text"] for t in title_obj])
            db_id = db.get("id", "")
            print("  - [%s] %s" % (db_id, title))
        
        print("\n-> Copy the database ID and add to .env:")
        print("   NOTION_DATABASE_ID=<your-database-id>")
    else:
        print("\nNo databases found.")
        print("Make sure you've shared your database with the 'AI NEWS' integration.")


async def test_sync_sample():
    from editor_assistant import CuratedItem, ContentTier, SignalType
    
    sample_items = [
        {
            "id": "test001",
            "title": "OpenAI发布GPT-5预览版，支持百万级上下文窗口",
            "tier": "GOLD",
            "signal_type": "model_breakthrough",
            "source": "OpenAI官方博客",
            "link": "https://openai.com/blog/gpt-5",
            "published_at": "2026-04-08T10:00:00Z",
            "who": "OpenAI团队",
            "what": "发布GPT-5预览版，采用全新MoE架构",
            "why": "应对竞争压力+满足企业级需求",
            "how": "推理成本降低60%，支持100万token上下文",
            "implications": "重塑AI应用开发范式",
            "overall_score": 8.4,
            "core_highlight": "首个支持百万级上下文的商业大模型",
            "industry_impact": "短期：API价格战；中期：企业门槛降低；长期：模型军备竞赛",
            "tags": ["GPT-5", "OpenAI", "MoE", "LLM"],
            "categories": ["model_layer", "llm", "breaking"],
            "draft_angles": [
                "技术向：GPT-5 MoE架构深度解析",
                "商业向：百万上下文如何改变企业AI格局",
                "行业向：2026年大模型竞争格局展望"
            ],
            "actionable_for_editor": "申请API访问权限，准备对比评测稿",
            "fact_checks": [
                {"claim": "100万token上下文", "status": "[官方数据]", "confidence": 0.95},
                {"claim": "推理成本降低60%", "status": "[待验证]", "confidence": 0.6}
            ]
        },
        {
            "id": "test002",
            "title": "Anthropic完成20亿美元B轮融资，估值达600亿",
            "tier": "SILVER",
            "signal_type": "funding_acquisition",
            "source": "TechCrunch",
            "link": "https://techcrunch.com/anthropic-funding",
            "published_at": "2026-04-08T09:00:00Z",
            "who": "Anthropic",
            "what": "完成B轮融资",
            "why": "加速Claude 4研发+扩展企业服务",
            "how": "由a16z和Durable Capital领投",
            "implications": "AI赛道竞争白热化",
            "overall_score": 7.2,
            "core_highlight": "Anthropic融资20亿美元，估值突破600亿",
            "industry_impact": "资本加速流入AI赛道，头部效应加剧",
            "tags": ["Anthropic", "融资", "Claude"],
            "categories": ["funding", "business"],
            "draft_angles": [
                "数据向：Anthropic融资历程与业务布局",
                "分析向：AI赛道投资热度判断"
            ],
            "actionable_for_editor": "关注资金用途，对比OpenAI估值",
            "fact_checks": [
                {"claim": "20亿美元融资", "status": "[官宣]", "confidence": 0.9}
            ]
        }
    ]
    
    print("\n=== Test Sync: 2 sample items ===")
    result = await batch_create_pages(sample_items, delay_seconds=1.0)
    
    print("\nResult:")
    print("  Success:", result["success"])
    print("  Failed:", result["failed"])
    
    if result["pages"]:
        print("\nCreated pages:")
        for p in result["pages"]:
            print("  -", p.get("url", "No URL"))


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        asyncio.run(setup_notion_database())
    elif len(sys.argv) > 1 and sys.argv[1] == "test":
        asyncio.run(test_sync_sample())
    else:
        print("Usage:")
        print("  python notion_sync.py setup   # Check connection & find databases")
        print("  python notion_sync.py test    # Sync 2 sample items")
