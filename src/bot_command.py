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
                        {"text": "💹 金融", "callback_data": "/finance"},
                        {"text": "🌍 全球", "callback_data": "/world"},
                        {"text": "🔮 Oracle", "callback_data": "/oracle"},
                    ]
                else:
                    nav_buttons = [
                        {"text": "🤖 AI科技", "callback_data": "/tech"},
                        {"text": "🔮 Oracle", "callback_data": "/oracle"},
                    ]
                
                keyboard = build_inline_keyboard([
                    [nav_buttons[0], nav_buttons[1]],
                    [nav_buttons[2]],
                ])
                
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
        {"command": "finance", "description": "💹 金融市场动态"},
        {"command": "oracle", "description": "🔮 Oracle深度分析"},
        {"command": "search", "description": "🔍 搜索关键词"},
        {"command": "digest", "description": "📋 今日摘要"},
        {"command": "status", "description": "📊 系统状态"},
        {"command": "help", "description": "❓ 帮助"},
    ]
    
    result2 = await call_telegram_api(
        "setMyCommands",
        commands=chat_commands,
        scope={"type": "chat"}
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
