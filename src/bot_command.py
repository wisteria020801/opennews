import asyncio
import os
import sys
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from opennews_mcp.tools.aggregator_rss import aggregate_free_news, SOURCES
except ImportError:
    from src.opennews_mcp.tools.aggregator_rss import aggregate_free_news, SOURCES

BOT_TOKEN = os.environ.get("BOT_TOKEN_G") or os.environ.get("TECHBOTTOKEN")
DEFAULT_CHAT_ID = os.environ.get("CHAT_ID_G", "-1003590230315")

COMMANDS = {
    "/new": "📰 全领域新闻 Top 10",
    "/tech": "🤖 AI/科技前沿 (情报引擎)",
    "/editor": "✍️ 编辑助理 (深度降噪+写稿辅助)",
    "/write": "📝 写稿素材 (选题+角度)",
    "/draft": "📋 三段式速写 (事实+来源+判断)",
    "/finance": "💹 金融/加密市场",
    "/world": "🌍 全球突发新闻",
    "/military": "⚔️ 军事冲突动态",
    "/politics": "🏛️ 政治博弈新闻",
    "/oracle": "🔮 Oracle 深度分析 (5W1H+I)",
    "/search": "🔍 关键词搜索新闻",
    "/digest": "📋 今日情报摘要",
    "/status": "📊 系统状态",
    "/help": "❓ 帮助与命令列表",
}

CATEGORY_MAP = {
    "/new": "all",
    "/tech": "tech",
    "/finance": "finance",
    "/world": "world",
    "/military": "military",
    "/politics": "politics",
}

EMOJI_MAP = {
    "all": "📰", "tech": "🤖", "finance": "💹",
    "world": "🌍", "military": "⚔️", "politics": "🏛️"
}


async def call_telegram_api(method: str, **kwargs) -> dict:
    if not BOT_TOKEN:
        return {}
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=kwargs, timeout=15.0)
            return resp.json()
    except Exception as e:
        print("[Telegram API] %s error: %s" % (method, e))
        return {}


async def send_message(chat_id: str, text: str, parse_mode: str = "Markdown",
                       reply_markup: dict = None) -> bool:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    result = await call_telegram_api("sendMessage", **payload)
    return result.get("ok", False)


def build_inline_keyboard(rows: list[list[dict]]) -> dict:
    return {"inline_keyboard": rows}


def build_main_menu_keyboard() -> dict:
    return build_inline_keyboard([
        [
            {"text": "🤖 AI科技", "callback_data": "/tech"},
            {"text": "💹 金融动态", "callback_data": "/finance"},
            {"text": "🌍 全球新闻", "callback_data": "/world"},
        ],
        [
            {"text": "⚔️ 军事", "callback_data": "/military"},
            {"text": "🏛️ 政治", "callback_data": "/politics"},
            {"text": "📰 全部", "callback_data": "/new"},
        ],
        [
            {"text": "🔮 Oracle深度分析", "callback_data": "/oracle"},
            {"text": "🔍 关键词搜索", "callback_data": "/search "},
        ],
        [
            {"text": "📊 系统状态", "callback_data": "/status"},
            {"text": "📋 今日摘要", "callback_data": "/digest"},
        ],
    ])


def build_help_message() -> str:
    return (
        "📋 *OpenNews Matrix v2.2 — 命令面板*\n\n"
        "*━━━ 📡 新闻查询 ━━━*\n"
        "`/new`     全领域最新新闻\n"
        "`/tech`    AI/科技前沿 ⭐(情报引擎)\n"
        "`/finance` 金融/加密市场\n"
        "`/world`   全球突发新闻\n"
        "`/military` 军事冲突动态\n"
        "`/politics` 政治博弈新闻\n\n"
        "*━━━ 🧠 深度分析 ━━━*\n"
        "`/oracle`  Oracle 5W1H+I 深度情报\n"
        "`/search`  🔍 关键词搜索 (例: /search GPT)\n"
        "`/digest`  📋 今日情报摘要\n\n"
        "*━━━ ⚙️ 系统 ━━━*\n"
        "`/status`  系统状态和源统计\n"
        "`/help`    显示此帮助\n\n"
        "_55个信息源 | 18个AI源 | Gemini+Keyword双引擎_"
    )


def build_start_message() -> str:
    return (
        "👋 *欢迎使用 OpenNews Matrix v2.2*\n\n"
        "🤖 *AI驱动的结构化情报平台*\n"
        "从「新闻堆叠」进化为「5W1H+I情报简报」\n\n"
        "*快速开始：点击下方按钮或输入命令*\n\n"
        "_55源 | 18AI源 | 双引擎分析_"
    )


async def handle_callback_query(callback_data: str, chat_id: str):
    cmd = callback_data.strip()
    
    if cmd.startswith("/search ") or cmd == "/search ":
        await send_message(
            chat_id,
            "🔍 *关键词搜索*\n\n"
            "用法: `/search <关键词>`\n"
            "示例:\n"
            "• `/search GPT`\n"
            "• `/search 芯片`\n"
            "• `/search OpenAI`\n\n"
            "_支持中英文搜索_"
        )
        return
    
    if cmd == "/search":
        await send_message(
            chat_id,
            "🔍 *关键词搜索*\n\n用法: `/search <关键词>`\n示例: `/search GPT` 或 `搜索 芯片`"
        )
        return
    
    response = await handle_command(cmd, chat_id)
    await send_message(chat_id, response)


async def handle_command(command: str, chat_id: str) -> str:
    command = command.strip()
    # 移除 @botname 后缀
    if '@' in command:
        command = command.split('@')[0].strip()
    raw_command = command.lower()
    
    if raw_command in ("/help", "/start"):
        if raw_command == "/start":
            msg = build_start_message()
        else:
            msg = build_help_message()
        
        keyboard = build_main_menu_keyboard()
        await send_message(chat_id, msg, reply_markup=keyboard)
        return ""
    
    if raw_command == "/status":
        tech_count = sum(1 for n, _ in SOURCES if any(k in n for k in [
            "MIT Technology", "Ars Technica", "VentureBeat", "TechCrunch",
            "The Verge", "Wired", "OpenAI", "DeepMind", "Google Research",
            "Hugging Face", "KDnuggets", "BAIR", "The Decoder", "Ben's Bites",
            "arXiv", "MIRI", "AWS", "Google Cloud"
        ]))
        finance_count = sum(1 for n, _ in SOURCES if any(k in n for k in [
            "Yahoo Finance", "Investing", "CoinDesk", "Cointelegraph",
            "Kraken", "Coinbase", "Foresight", "Wallstreet", "SEC", "CFTC"
        ]))
        world_count = sum(1 for n, _ in SOURCES if any(k in n for k in [
            "Reuters", "AP News", "BBC", "CNN", "Al Jazeera", "Guardian"
        ]))
        
        status_text = (
            "📊 *OpenNews Matrix 系统状态*\n\n"
            "*━━━ 📡 信息源统计 ━━━*\n"
            "• 总计: *%d* 个源\n"
            "• 🤖 AI/科技: *%d* 个\n"
            "• 💹 金融/加密: *%d* 个\n"
            "• 🌍 全球: *%d* 个\n"
            "• ⚔️ + 🏛️ 其他: *%d* 个\n\n"
            "*━━━ ⚙️ 引擎状态 ━━━*\n"
            "• 版本: *v2.2*\n"
            "• Bot: *🟢 在线*\n"
            "• 情报引擎: *Gemini-Deep + Keyword-Smart*\n"
            "• RSS聚合器: *🟢 正常*\n\n"
            "_更新于: %s_" 
            % (
                len(SOURCES), tech_count, finance_count, world_count,
                len(SOURCES) - tech_count - finance_count - world_count,
                datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        
        keyboard = build_inline_keyboard([
            [{"text": "🔄 刷新", "callback_data": "/status"}],
            [{"text": "🤖 测试AI源", "callback_data": "/tech"}, {"text": "🔮 Oracle分析", "callback_data": "/oracle"}],
        ])
        await send_message(chat_id, status_text, reply_markup=keyboard)
        return ""
    
    if raw_command == "/oracle":
        from intelligence_engine import run_intelligence_report, send_to_telegram
        result = await run_intelligence_report(category="oracle", chat_id=chat_id)
        report = result["report"]
        sent = await send_to_telegram(report, chat_id)
        
        keyboard = build_inline_keyboard([
            [{"text": "🔄 重新分析", "callback_data": "/oracle"}, {"text": "🤖 AI科技", "callback_data": "/tech"}],
        ])
        summary = (
            "🔮 *Oracle 情报分析完成*\n\n"
            "引擎: `%s`\n"
            "分析: *%d* 条情报\n"
            "%s" 
            % (result["engine"], result["count"],
               "_完整报告已推送_" if sent else "_推送失败_")
        )
        await send_message(chat_id, summary, reply_markup=keyboard)
        return ""
    
    if raw_command == "/editor":
        from editor_assistant import run_editor_report, send_to_telegram as editor_send
        await send_message(chat_id, "*Editor Assistant v3.1 Starting...*\n\n_Running deep curation + contextual analysis_")
        
        result = await run_editor_report(category="tech", chat_id=chat_id)
        report = result["report"]
        sent = await editor_send(report, chat_id)
        
        tier_info = result.get("tier_breakdown", {})
        
        hotspot_items = []
        for item_data in result.get("items", []):
            tags = item_data.get("tags", [])
            if any("[HOTSPOT:" in str(t) for t in tags):
                hotspot_items.append(item_data)
        
        if hotspot_items:
            alert_msg = "\n\n*HOTSPOT ALERT - %d Breaking Items Detected:*\n" % len(hotspot_items)
            for idx, h_item in enumerate(hotspot_items[:5], 1):
                score = h_item.get("overall_score", 0)
                source = h_item.get("source", "")[:30]
                alert_msg += "%d. [%s] %s\n   _Source: %s | Score: %.1f_\n" % (
                    idx,
                    h_item.get("tier", "HIGH"),
                    h_item.get("title", "")[:60],
                    source,
                    score
                )
            await send_message(chat_id, alert_msg)
        
        keyboard = build_inline_keyboard([
            [{"text": "Re-analyze", "callback_data": "/editor"}, {"text": "AI Tech", "callback_data": "/tech"}],
            [{"text": "Export to Notion", "callback_data": "/export"}, {"text": "Writing Help", "callback_data": "/write"}],
            [{"text": "Daily Digest", "callback_data": "/digest"}],
        ])
        
        notion_info = result.get("notion_sync")
        notion_status = ""
        if notion_info:
            n_success = notion_info.get("success", 0)
            n_failed = notion_info.get("failed", 0)
            if n_success > 0:
                notion_status = "\n\n_[Notion] Synced %d items to material library_" % n_success
            else:
                notion_status = "\n\n_[Notion] Sync: 0 items (all BRONZE or below)_"
        else:
            notion_status = "\n\n_[Notion] Not configured or sync skipped_"
        
        summary = (
            "*Editor v3.1 Analysis Complete*\n\n"
            "Engine: `Deep Curation v2.0 + Contextual Analysis`\n"
            "Total Items: *%d*\n\n"
            "*Content Tiers:*\n"
            "- GOLD: *%d* (Headline Material)\n"
            "- SILVER: *%d* (Important News)\n"
            "- BRONZE: *%d* (General Updates)\n"
            "- FILTERED: *%d* (Noise Removed)\n"
            "- HOTSPOTS: *%d* (Breaking)\n\n"
            "%s%s"
            % (
                result["count"],
                tier_info.get("gold", 0),
                tier_info.get("silver", 0),
                tier_info.get("bronze", 0),
                tier_info.get("filtered", 0),
                len(hotspot_items),
                "_Report sent_" if sent else "_Send failed_",
                notion_status
            )
        )
        await send_message(chat_id, summary, reply_markup=keyboard)
        return ""
    
    if raw_command == "/write" or raw_command.startswith("/write "):
        from editor_assistant import run_editor_report
        
        write_arg = ""
        if raw_command.startswith("/write "):
            write_arg = command[len("/write "):].strip()
        
        await send_message(chat_id, "*Writing Assistant v2.0*\n\n_Generating writing materials..._")
        
        result = await run_editor_report(category="tech", chat_id=chat_id, max_items=20)
        
        items = result.get("items", [])
        
        if items:
            print("[Draft] Total items: %d" % len(items))
            sample_tiers = set(i.get("content_tier", "NONE") for i in items[:5])
            print("[Draft] Sample tiers: %s" % sample_tiers)
            for idx, i in enumerate(items[:3]):
                print("[Draft] Item %d: tier=%s title=%s" % (idx, i.get("content_tier"), (i.get("title") or "")[:50]))
        
        gold_items = [i for i in items if i.get("content_tier") == "gold"]
        silver_items = [i for i in items if i.get("content_tier") == "silver"]
        all_high_value = gold_items + silver_items
        
        if not all_high_value and items:
            print("[Draft] No gold/silver found, trying case-insensitive match...")
            gold_items = [i for i in items if str(i.get("content_tier", "")).lower() == "gold"]
            silver_items = [i for i in items if str(i.get("content_tier", "")).lower() == "silver"]
            all_high_value = gold_items + silver_items
            if all_high_value:
                print("[Draft] Found %d items with case-insensitive match" % len(all_high_value))
        
        if not all_high_value and items:
            print("[Draft] Still no matches. Using top items by tier order...")
            tier_order = {"gold": 0, "silver": 1, "bronze": 2, "filter": 3}
            sorted_items = sorted(items, key=lambda x: tier_order.get(str(x.get("content_tier", "")).lower(), 99))
            all_high_value = sorted_items[:3]
            print("[Draft] Fallback: using top %d items" % len(all_high_value))
        
        if not all_high_value:
            return "_No high-value material available. Try /editor first._"
        
        best_item = None
        selection_mode = "auto"
        
        if write_arg:
            try:
                item_num = int(write_arg)
                if 1 <= item_num <= len(all_high_value):
                    best_item = all_high_value[item_num - 1]
                    selection_mode = "number_%d" % item_num
                else:
                    return "_Invalid number. Available: 1-%d\nUse /write to see the list, or /write <number>_" % len(all_high_value)
            except ValueError:
                keyword_lower = write_arg.lower()
                matched_items = []
                
                for item in all_high_value:
                    title_lower = (item.get("title", "") or "").lower()
                    summary_lower = (item.get("summary", "") or "").lower()
                    tags_str = " ".join(str(t) for t in item.get("tags", []))
                    combined = "%s %s %s" % (title_lower, summary_lower, tags_str)
                    
                    if keyword_lower in combined:
                        score = 0
                        if keyword_lower in title_lower:
                            score += 10
                        if keyword_lower in summary_lower:
                            score += 5
                        for tag in item.get("tags", []):
                            if keyword_lower in str(tag).lower():
                                score += 3
                        
                        matched_items.append((item, score))
                
                matched_items.sort(key=lambda x: x[1], reverse=True)
                
                if matched_items:
                    best_item = matched_items[0][0]
                    selection_mode = "keyword:%s" % write_arg
                    
                    if len(matched_items) > 1:
                        match_list = "\n*Other matches:*\n"
                        for idx, (m_item, m_score) in enumerate(matched_items[1:5], 1):
                            match_list += "%d. %s (relevance: %d)\n" % (
                                idx + 1,
                                m_item.get("title", "")[:50],
                                m_score
                            )
                        await send_message(chat_id, match_list)
                else:
                    suggest_keywords = []
                    for item in all_high_value[:5]:
                        entities = item.get("tags", [])[:3]
                        suggest_keywords.extend([str(e) for e in entities])
                    
                    suggest_unique = list(set(suggest_keywords))[:8]
                    
                    return (
                        "_No items matched '%s'_\n\n"
                        "*Try these keywords:*\n%s\n\n"
                        "_Or use /write alone for auto-selection_"
                    ) % (
                        write_arg,
                        ", ".join(suggest_unique) if suggest_unique else "_Run /editor first_"
                    )
        else:
            best_item = all_high_value[0]
            selection_mode = "auto_top"
        
        if not best_item:
            return "_Could not select item. Try /write without arguments._"
        
        title = best_item.get("title", "Untitled")
        entities = best_item.get("tags", [])
        core_highlight = best_item.get("core_highlight", "")
        angles = best_item.get("draft_angles", [])
        historical = best_item.get("historical_context", "")
        reactions = best_item.get("competitor_reactions", {})
        chain_pos = best_item.get("industry_chain_position", "")
        actionable = best_item.get("actionable_for_editor", "")
        source = best_item.get("source", "")
        link = best_item.get("link", "")
        tier = best_item.get("content_tier", "").upper()
        score = best_item.get("overall_score", 0)
        
        item_index = -1
        for idx, item in enumerate(all_high_value):
            if item.get("title") == title:
                item_index = idx + 1
                break
        
        write_guide = (
            "*Writing Guide [%s]*\n" % tier +
            "*Item #%d of %d high-value materials*\n\n" % (item_index, len(all_high_value)) +
            "=" * 30 + "\n\n" +
            "*Title:*\n%s\n\n" % title +
            "*Source:* %s | *Score:* %.1f\n\n" % (source[:40], score) +
            "---\n\n" +
            "*Core Insight:*\n%s\n\n" % (core_highlight or "_Pending analysis_") +
            "*Entities:*\n%s\n\n" % (", ".join(entities[:5]) if entities else "_Detected after analysis_") +
            "*Historical Context:*\n%s\n\n" % (historical or "_Pending analysis_") +
            "*Industry Chain Position:*\n%s\n\n" % (chain_pos or "_Pending analysis_") +
            "*Suggested Angles:*\n"
        )
        
        for idx, angle in enumerate(angles[:4], 1):
            write_guide += "%d. %s\n" % (idx, angle)
        
        if reactions:
            write_guide += "\n*Competitor Reactions:*\n"
            for comp, reaction in list(reactions.items())[:3]:
                write_guide += "- %s: %s\n" % (comp, reaction)
        
        write_guide += (
            "\n*Action Items:*\n%s\n\n" % (actionable or "_See full report_") +
            "*Original Link:*\n%s\n\n" % (link or "_Not available_") +
            "_Mode: %s | Use /write <number> for other items_" % selection_mode
        )
        
        keyboard_buttons = []
        row1 = [{"text": "Full Analysis", "callback_data": "/editor"}]
        if item_index > 1:
            row1.append({"text": "Prev Item", "callback_data": "/write %d" % (item_index - 1)})
        if item_index < len(all_high_value):
            row1.append({"text": "Next Item", "callback_data": "/write %d" % (item_index + 1)}) if len(row1) < 3 else None
        keyboard_buttons.append(row1)
        
        keyboard_buttons.append([
            {"text": "Export to Notion", "callback_data": "/export"}
        ])
        
        keyboard = build_inline_keyboard(keyboard_buttons)
        
        await send_message(chat_id, write_guide, reply_markup=keyboard)
        return ""
    
    if raw_command == "/draft" or raw_command.startswith("/draft "):
        from editor_assistant import run_editor_report, generate_draft_framework, generate_quick_template
        
        draft_arg = ""
        draft_mode = "quick"
        
        if raw_command.startswith("/draft "):
            arg_part = command[len("/draft "):].strip()
            parts = arg_part.split()
            
            mode_keywords = ["short", "deep", "long", "quick", "fast", "q", "s", "d", "l"]
            if parts and parts[-1].lower() in mode_keywords:
                last = parts[-1].lower()
                if last in ["deep", "long", "d", "l"]:
                    draft_mode = "deep"
                elif last in ["short", "s"]:
                    draft_mode = "short"
                else:
                    draft_mode = "quick"
                draft_arg = " ".join(parts[:-1])
            else:
                draft_arg = arg_part
        
        await send_message(chat_id, "*Draft Workstation v1.0*\n\n_Building semi-automatic draft framework..._")
        
        result = await run_editor_report(category="tech", chat_id=chat_id, max_items=20)
        
        items = result.get("items", [])
        gold_items = [i for i in items if i.get("content_tier") == "gold"]
        silver_items = [i for i in items if i.get("content_tier") == "silver"]
        all_high_value = gold_items + silver_items
        
        if not all_high_value and items:
            gold_items = [i for i in items if str(i.get("content_tier", "")).lower() == "gold"]
            silver_items = [i for i in items if str(i.get("content_tier", "")).lower() == "silver"]
            all_high_value = gold_items + silver_items
        
        if not all_high_value and items:
            tier_order = {"gold": 0, "silver": 1, "bronze": 2, "filter": 3}
            sorted_items = sorted(items, key=lambda x: tier_order.get(str(x.get("content_tier", "")).lower(), 99))
            all_high_value = sorted_items[:3]
        
        if not all_high_value:
            return "_No high-value material for drafting. Run /editor first._"
        
        target_item = None
        selection_info = ""
        
        if draft_arg:
            try:
                item_num = int(draft_arg)
                if 1 <= item_num <= len(all_high_value):
                    target_item = all_high_value[item_num - 1]
                    selection_info = "Item #%d selected" % item_num
                else:
                    return "_Invalid number. Available: 1-%d_\n_Use: /draft <number> [short|deep]_" % len(all_high_value)
            except ValueError:
                keyword_lower = draft_arg.lower()
                matched_items = []
                
                for item in all_high_value:
                    title_lower = (item.get("title", "") or "").lower()
                    summary_lower = (item.get("summary", "") or "").lower()
                    tags_str = " ".join(str(t) for t in item.get("tags", []))
                    combined = "%s %s %s" % (title_lower, summary_lower, tags_str)
                    
                    if keyword_lower in combined:
                        score = 0
                        if keyword_lower in title_lower:
                            score += 10
                        if keyword_lower in summary_lower:
                            score += 5
                        matched_items.append((item, score))
                
                matched_items.sort(key=lambda x: x[1], reverse=True)
                
                if matched_items:
                    target_item = matched_items[0][0]
                    selection_info = "Matched: '%s'" % draft_arg
                    
                    if len(matched_items) > 1:
                        match_list = "*Other matches:*\n"
                        for idx, (m_item, m_score) in enumerate(matched_items[1:4], 1):
                            match_list += "%d. %s\n" % (idx + 1, (m_item.get("title", "") or "")[:50])
                        await send_message(chat_id, match_list)
                else:
                    suggest = []
                    for item in all_high_value[:5]:
                        suggest.extend([str(t) for t in item.get("tags", [])[:2]])
                    return (
                        "_No match for '%s'_\n\n"
                        "*Try:*\n%s\n\n"
                        "_Or: /draft [for auto-select]_"
                    ) % (draft_arg, ", ".join(list(set(suggest))[:6]) if suggest else "_Run /editor first_")
        else:
            target_item = all_high_value[0]
            selection_info = "Auto-selected top item"
        
        if not target_item:
            return "_Could not select item. Try /draft without arguments._"
        
        if draft_mode == "quick":
            mode_label = "QUICK (三段式速写)"
            draft_output = generate_quick_template(target_item)
            
            header = (
                "*Quick Template [%s]*\n"
                "%s\n"
                "%s\n\n"
                "=== 信息套利模式 ===\n"
                "事实 + 来源 + 判断\n"
                "目标: 快速决策，值不值得写\n\n"
            ) % (mode_label, selection_info, "=" * 30)
            
            keyboard_buttons = []
            row1 = [{"text": "→ 完整初稿 (Short)", "callback_data": "/draft %s short" % (draft_arg or "")}]
            row2 = [{"text": "→ 深度分析 (Deep)", "callback_data": "/draft %s deep" % (draft_arg or "")}]
            row3 = [{"text": "Back to Editor", "callback_data": "/editor"}]
            keyboard_buttons.append(row1)
            keyboard_buttons.append(row2)
            keyboard_buttons.append(row3)
        else:
            mode_label = "SHORT (~500 words)" if draft_mode == "short" else "DEEP DIVE (~1500 words)"
            draft_output = generate_draft_framework(target_item, mode=draft_mode)
            
            header = (
                "*Draft Framework [%s]*\n"
                "%s\n"
                "%s\n\n"
                "=== SEMI-AUTOMATIC WORKSTATION ===\n"
                "Bot provides: Skeleton + Evidence + Context\n"
                "YOU provide: Judgment + Angle + Voice\n\n"
            ) % (mode_label, selection_info, "=" * 35)
            
            keyboard_buttons = []
            row1 = [{"text": "Re-draft (Deep)", "callback_data": "/draft %s deep" % (draft_arg or "")}]
            row2 = [{"text": "Back to Write", "callback_data": "/write"}, {"text": "Editor Analysis", "callback_data": "/editor"}]
            keyboard_buttons.append(row1)
            keyboard_buttons.append(row2)
        
        full_draft = header + draft_output
        
        keyboard = build_inline_keyboard(keyboard_buttons)
        
        await send_message(chat_id, full_draft, reply_markup=keyboard)
        return ""
    
    if raw_command.startswith("/search "):
        keyword = command[len("/search "):].strip()
        if not keyword:
            return "🔍 *用法*: `/search <关键词>`\n\n示例: `/search GPT` 或 `/search 芯片`"
        
        return await handle_search(keyword, chat_id)
    
    if raw_command == "/digest":
        return await handle_digest(chat_id)
    
    if raw_command in CATEGORY_MAP:
        category = CATEGORY_MAP[raw_command]
        
        if raw_command in ("/tech", "/new"):
            from intelligence_engine import run_intelligence_report, send_to_telegram
            intel_cat = category if category != "all" else "tech"
            result = await run_intelligence_report(category=intel_cat, chat_id=chat_id)
            
            if result.get("count", 0) > 0:
                sent = await send_to_telegram(result["report"], chat_id)
                
                nav_buttons = []
                if raw_command == "/tech":
                    nav_buttons = [
                        {"text": "Finance", "callback_data": "/finance"},
                        {"text": "World", "callback_data": "/world"},
                        {"text": "Oracle", "callback_data": "/oracle"},
                    ]
                else:
                    nav_buttons = [
                        {"text": "AI Tech", "callback_data": "/tech"},
                        {"text": "Oracle", "callback_data": "/oracle"},
                    ]
                
                keyboard_rows = []
                if len(nav_buttons) >= 2:
                    keyboard_rows.append([nav_buttons[0], nav_buttons[1]])
                if len(nav_buttons) >= 3:
                    keyboard_rows.append([nav_buttons[2]])
                
                keyboard = build_inline_keyboard(keyboard_rows)
                
                summary = (
                    "🔍 *%s 情报报告*\n\n"
                    "引擎: `%s`\n"
                    "分析: *%d* 条\n"
                    "%s"
                    % (
                        EMOJI_MAP.get(category, '📰'),
                        result["engine"],
                        result["count"],
                        "_完整报告已推送_" if sent else "_推送失败_"
                    )
                )
                await send_message(chat_id, summary, reply_markup=keyboard)
                return ""
        
        max_items = 15 if category == "all" else 10
        
        result = await aggregate_free_news(
            None,
            max_items=max_items,
            send_to_telegram=False,
            category=category
        )
        
        items = result.get("items", [])
        fetched = result.get("total_fetched", 0)
        
        if not items:
            return (
                "%s *暂无%s新闻*\n\n"
                "当前时段没有检测到相关的%s类别新闻。\n"
                "系统将继续监控，有新消息时自动推送。\n\n"
                "_尝试 /new 查看全领域新闻_"
                % (EMOJI_MAP.get(category, '📰'), category, category)
            )
        
        msg = format_news_message(items, category, fetched)
        await send_message(chat_id, msg)
        return ""
    
    return (
        "❓ *未知命令: `" + raw_command + "`*\n\n"
        "可用命令:\n" +
        "\n".join("  `" + cmd + "` — " + desc for cmd, desc in COMMANDS.items()) +
        "\n\n_输入 /help 查看完整帮助_"
    )


async def handle_search(keyword: str, chat_id: str) -> str:
    max_items = 20
    
    result = await aggregate_free_news(
        None,
        max_items=max_items,
        send_to_telegram=False,
        category="all"
    )
    
    items = result.get("items", [])
    
    keyword_lower = keyword.lower()
    matched = []
    
    for item in items:
        title = item.get("title", "").lower()
        source = item.get("source", "").lower()
        summary = item.get("summary", "").lower()
        
        score = 0
        if keyword_lower in title:
            score += 3
            if title.index(keyword_lower) < 20:
                score += 1
        if keyword_lower in source:
            score += 1
        if keyword_lower in summary:
            score += 1
        
        if score > 0:
            item["_search_score"] = score
            matched.append(item)
    
    matched.sort(key=lambda x: x.get("_search_score", 0), reverse=True)
    matched = matched[:10]
    
    now_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    if not matched:
        return (
            "🔍 *搜索结果: 「%s」*\n\n"
            "未找到匹配的新闻。\n\n"
            "*建议:*\n"
            "• 尝试英文关键词 (如 GPT, NVIDIA)\n"
            "• 尝试更短的关键词\n"
            "• 使用 `/new` 查看所有最新新闻\n\n"
            "_扫描了 %d 条新闻_" % (keyword, len(items))
        )
    
    lines = [
        "🔍 *搜索结果: 「%s」*" % keyword,
        "找到 *%d* 条匹配 | `%s`" % (len(matched), now_str),
        "",
    ]
    
    for i, it in enumerate(matched):
        src = it.get("source", "?")
        title = it.get("title", "")[:110]
        score = it.get("_search_score", 0)
        link = it.get("link", "")
        
        match_marker = "🎯" if score >= 4 else "📌" if score >= 3 else "📄"
        lines.append(
            "%s *[%d]* **%s**: %s" % (match_marker, i+1, src, title)
        )
        if link:
            lines.append("   [查看原文](%s)" % link)
    
    lines.append("\n_输入 /help 查看所有命令_")
    
    msg = "\n".join(lines)
    await send_message(chat_id, msg)
    return ""


async def handle_digest(chat_id: str) -> str:
    categories_to_check = ["tech", "finance", "world"]
    digest_parts = ["📋 *OpenNews 今日情报摘要*\n"]
    total_found = 0
    
    for cat in categories_to_check:
        try:
            result = await aggregate_free_news(
                None, max_items=5, send_to_telegram=False, category=cat
            )
            items = result.get("items", [])[:3]
            
            if not items:
                continue
            
            total_found += len(items)
            cat_names = {
                "tech": "🤖 AI/科技", "finance": "💹 金融",
                "world": "🌍 全球", "military": "⚔️ 军事", "politics": "🏛️ 政治"
            }
            cat_name = cat_names.get(cat, cat)
            
            digest_parts.append("*%s*" % cat_name)
            for i, it in enumerate(items):
                title = it.get("title", "")[:90]
                src = it.get("source", "?")
                res = it.get("resonance_count", 1)
                res_tag = " 🔥x%d" % res if res > 1 else ""
                digest_parts.append("  %d. [%s]%s %s" % (i+1, src, res_tag, title))
            digest_parts.append("")
        except Exception as e:
            print("[Digest] Error fetching %s: %s" % (cat, e))
    
    now_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    if total_found == 0:
        digest_parts.append("_暂无今日新闻数据_")
    else:
        digest_parts.append("—\n_*共 %d 条要闻 | %s*_" % (total_found, now_str))
    
    digest_parts.append("\n_详细报告: /tech /finance /oracle_")
    
    keyboard = build_inline_keyboard([
        [{"text": "🤖 AI详情", "callback_data": "/tech"},
         {"text": "💹 金融详情", "callback_data": "/finance"},
         {"text": "🔮 Oracle全析", "callback_data": "/oracle"}],
        [{"text": "🔄 刷新摘要", "callback_data": "/digest"}],
    ])
    
    await send_message(chat_id, "\n".join(digest_parts), reply_markup=keyboard)
    return ""


def format_news_message(items: list[dict], category: str, total_fetched: int) -> str:
    emoji = EMOJI_MAP.get(category, "📰")
    now_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    category_names = {
        "all": "全领域", "tech": "AI/科技前沿", "finance": "金融/加密市场",
        "world": "全球突发", "military": "军事冲突", "politics": "政治博弈"
    }
    
    lines = [
        "%s *OpenNews Matrix | %s*" % (emoji, category_names.get(category, category)),
        "⏰ `%s` | 📡 抓取: %d | 📬 筛选: %d" % (now_str, total_fetched, len(items)),
        "",
    ]
    
    critical_items = [it for it in items if it.get('overall_score', 0) >= 8 or it.get('resonance_count', 1) >= 3]
    high_items = [it for it in items if it not in critical_items]
    
    if critical_items:
        lines.append("🔴 *━━━ CRITICAL ━━━*")
        for it in critical_items[:3]:
            score = it.get('overall_score', 0)
            src = it.get('source', '?')
            title = it.get('title', '')[:120]
            res = it.get('resonance_count', 1)
            res_tag = " x%d" % res if res > 1 else ""
            lines.append("")
            lines.append("⚡ *[%0.1f]* [%s%s]" % (score, src, res_tag))
            lines.append("  %s" % title)
        lines.append("")
    
    lines.append("*━━━ 最新动态 ━━━*")
    display_items = critical_items + high_items
    for i, it in enumerate(display_items[:15]):
        score = it.get('overall_score', 0)
        src = it.get('source', '?')
        title = it.get('title', '')[:110]
        tim = it.get('raw_timeliness', 0)
        pro = it.get('raw_prominence', 0)
        lines.append("%d. *[%0.1f|T:%.0f]* **%s**: %s" % (i+1, score, tim, src, title))
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("_输入 /help 查看所有命令_")
    return "\n".join(lines)


async def get_updates(offset: int = 0, timeout: int = 30) -> tuple[list[dict], int]:
    result = await call_telegram_api(
        "getUpdates",
        offset=offset,
        timeout=timeout,
        allowed_updates=["message", "callback_query"]
    )
    
    if not result.get("ok"):
        return [], offset
    
    updates = result.get("result", [])
    new_offset = offset
    if updates:
        new_offset = updates[-1]["update_id"] + 1
    
    return updates, new_offset


async def process_update(update: dict):
    if "callback_query" in update:
        cb = update["callback_query"]
        data = cb.get("data", "")
        chat_id = str(cb["message"]["chat"]["id"])
        user = cb.get("from", {})
        username = user.get("username") or user.get("first_name", "?")
        
        print("[Callback] @%s: %s" % (username, data))
        
        await call_telegram_api("answerCallbackQuery", callback_query_id=cb["id"])
        
        await handle_callback_query(data, chat_id)
        return
    
    if "message" not in update:
        return
    
    message = update["message"]
    text = message.get("text", "").strip()
    chat_id = str(message["chat"]["id"])
    user = message.get("from", {})
    username = user.get("username") or user.get("first_name", "Unknown")
    
    if not text.startswith("/"):
        return
    
    print("[Command] @%s: %s (chat: %s)" % (username, text, chat_id))
    
    response = await handle_command(text, chat_id)
    
    if response:
        success = await send_message(chat_id, response)
        if success:
            print("  [OK] Response sent (%d chars)" % len(response))
        else:
            print("  [FAIL] Failed to send")


async def register_bot_commands():
    commands = [
        {"command": "new", "description": "📰 全领域新闻 Top 10"},
        {"command": "tech", "description": "🤖 AI/科技前沿 (情报引擎)"},
        {"command": "editor", "description": "✍️ 编辑助理 (深度降噪+写稿辅助)"},
        {"command": "write", "description": "📝 写稿素材 (选题+角度)"},
        {"command": "draft", "description": "📋 三段式速写 (事实+来源+判断)"},
        {"command": "finance", "description": "💹 金融/加密市场"},
        {"command": "world", "description": "🌍 全球突发新闻"},
        {"command": "military", "description": "⚔️ 军事冲突动态"},
        {"command": "politics", "description": "🏛️ 政治博弈新闻"},
        {"command": "oracle", "description": "🔮 Oracle 深度分析 (5W1H+I)"},
        {"command": "search", "description": "🔍 关键词搜索新闻"},
        {"command": "digest", "description": "📋 今日情报摘要"},
        {"command": "status", "description": "📊 系统状态"},
        {"command": "help", "description": "❓ 帮助与命令列表"},
    ]
    
    result = await call_telegram_api("setMyCommands", commands=commands)
    if result.get("ok"):
        print("  [OK] Commands registered (default scope)")
    else:
        safe_msg = str(result)[:200]
        try:
            print("  [WARN] Failed: %s" % safe_msg)
        except UnicodeEncodeError:
            print("  [WARN] Failed: %s" % safe_msg.encode('ascii', errors='replace').decode())
    
    chat_commands = [
        {"command": "new", "description": "📰 最新全领域新闻"},
        {"command": "tech", "description": "🤖 AI/科技情报报告"},
        {"command": "editor", "description": "✍️ 编辑助理分析"},
        {"command": "write", "description": "📝 写稿素材库"},
        {"command": "draft", "description": "📋 三段式速写模板"},
        {"command": "finance", "description": "💹 金融市场动态"},
        {"command": "search", "description": "🔍 搜索关键词"},
        {"command": "digest", "description": "📋 今日摘要"},
        {"command": "status", "description": "📊 系统状态"},
        {"command": "help", "description": "❓ 帮助"},
    ]
    
    result2 = await call_telegram_api(
        "setMyCommands",
        commands=chat_commands,
        scope={"type": "chat", "chat_id": DEFAULT_CHAT_ID}
    )
    if result2.get("ok"):
        print("  [OK] Chat group menu registered")
    else:
        try:
            print("  [INFO] Chat scope: %s" % str(result2.get("description", ""))[:80])
        except Exception:
            pass


async def run_bot():
    if not BOT_TOKEN:
        print("[ERROR] BOT_TOKEN_G / TECHBOTTOKEN not set.")
        print("   Set it with: $env:BOT_TOKEN_G='your-token'")
        return
    
    me = await call_telegram_api("getMe")
    if me.get("ok"):
        bot_info = me["result"]
        try:
            print("🤖 Bot started: @%s (%s)" % (
                bot_info.get('username', '?'),
                bot_info.get('first_name', '?')
            ))
        except UnicodeEncodeError:
            print("[OK] Bot started: @%s (%s)" % (
                bot_info.get('username', '?'),
                bot_info.get('first_name', '?')
            ))
        try:
            print("   ID: %d" % bot_info.get('id'))
        except UnicodeEncodeError:
            print("   ID: %d" % bot_info.get('id'))
    else:
        print("[WARN] Failed to get bot info, but continuing...")
    
    print("\n[INFO] Registering command menu...")
    await register_bot_commands()
    
    print("\n[LISTEN] Polling for commands... (Ctrl+C to stop)")
    print("\nAvailable commands:")
    for cmd, desc in COMMANDS.items():
        safe_desc = desc
        try:
            print("  %-12s %s" % (cmd, safe_desc))
        except UnicodeEncodeError:
            safe_desc = safe_desc.encode('ascii', errors='replace').decode('ascii')
            print("  %-12s %s" % (cmd, safe_desc))
    print("")
    
    offset = 0
    while True:
        try:
            updates, offset = await get_updates(offset, timeout=30)
            
            for update in updates:
                await process_update(update)
                    
        except KeyboardInterrupt:
            print("\n[STOP] Bot stopped by user.")
            break
        except Exception as e:
            print("[Error] %s" % e)
            await asyncio.sleep(5)


async def test_single_command(command: str, chat_id: str = None):
    target_chat = chat_id or DEFAULT_CHAT_ID
    print("\n[Test] Command: %s → Chat: %s" % (command, target_chat))
    
    response = await handle_command(command, target_chat)
    
    if response:
        print("[Response] (%d chars)" % len(response))
        print("---")
        safe_response = response[:1500].replace('\U0001f4ca', '[chart]').replace('\U0001f4c8', '[graph]').replace('\u2705', '[OK]').replace('\u274c', '[X]').replace('\U0001f680', '[rocket]').replace('\U0001f4e1', '[broadcast]').replace('\U0001f504', '[settings]').replace('\U0001f4dd', '[memo]').replace('\U0001f514', '[bell]')
        try:
            print(safe_response)
        except UnicodeEncodeError:
            print(safe_response.encode('ascii', errors='replace').decode('ascii'))
        print("---")
        
        if BOT_TOKEN and target_chat:
            sent = await send_message(target_chat, response)
            print("[Telegram] %s" % ('Sent OK' if sent else 'Failed'))
    else:
        print("[Response] (inline keyboard sent)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="OpenNews Matrix Bot v2.2")
    parser.add_argument("--test", help="Test a single command (e.g., /tech)")
    parser.add_argument("--chat-id", help="Target chat ID for test mode")
    parser.add_argument("--run", action="store_true", help="Run bot in polling mode")
    parser.add_argument("--menu", action="store_true", help="Register command menu only")
    args = parser.parse_args()
    
    if args.test:
        asyncio.run(test_single_command(args.test, args.chat_id))
    elif args.run:
        asyncio.run(run_bot())
    elif args.menu:
        asyncio.run(register_bot_commands())
    else:
        print("OpenNews Matrix Bot v2.2")
        print("=" * 40)
        print("Usage:")
        print("  python bot_command.py --run           Start bot (polling mode)")
        print("  python bot_command.py --test /tech     Test single command")
        print("  python bot_command.py --menu           Register Telegram menu")
        print("")
        print("Commands:")
        for cmd, desc in COMMANDS.items():
            print("  %-12s %s" % (cmd, desc))
