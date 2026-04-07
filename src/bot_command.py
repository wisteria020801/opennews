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
    from opennews_mcp.tools.aggregator_rss import aggregate_free_news
except ImportError:
    from src.opennews_mcp.tools.aggregator_rss import aggregate_free_news

BOT_TOKEN = os.environ.get("BOT_TOKEN_G") or os.environ.get("TECHBOTTOKEN")
DEFAULT_CHAT_ID = os.environ.get("CHAT_ID_G", "-1003590230315")

COMMANDS = {
    "/new": "📰 获取最新全领域新闻 (Top 10)",
    "/tech": "🤖 获取 AI/科技前沿新闻",
    "/finance": "💹 获取金融/加密市场动态",
    "/world": "🌍 获取全球突发新闻",
    "/military": "⚔️ 获取军事冲突动态",
    "/politics": "🏛️ 获取政治博弈新闻",
    "/oracle": "🔮 触发 Oracle 深度分析 (5W1H+I)",
    "/status": "📊 查看系统状态和源统计",
    "/help": "❓ 显示帮助信息",
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
        print(f"[Telegram API] {method} error: {e}")
        return {}


async def send_message(chat_id: str, text: str, parse_mode: str = "Markdown") -> bool:
    result = await call_telegram_api(
        "sendMessage",
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode,
        disable_web_page_preview=True,
    )
    return result.get("ok", False)


def format_news_message(items: list[dict], category: str, total_fetched: int) -> str:
    emoji = EMOJI_MAP.get(category, "📰")
    now_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    
    category_names = {
        "all": "全领域", "tech": "AI/科技前沿", "finance": "金融/加密市场",
        "world": "全球突发", "military": "军事冲突", "politics": "政治博弈"
    }
    
    lines = [
        f"{emoji} **OpenNews Matrix | {category_names.get(category, category)}**",
        f"⏰ `{now_str}` | 📡 源抓取: {total_fetched} | 📬 筛选: {len(items)}",
        ""
    ]
    
    critical_items = [it for it in items if it.get('overall_score', 0) >= 8 or it.get('resonance_count', 1) >= 3]
    high_items = [it for it in items if it not in critical_items]
    
    if critical_items:
        lines.append("🔴 **━━━ CRITICAL ━━━**")
        for it in critical_items[:3]:
            score = it.get('overall_score', 0)
            src = it.get('source', '?')
            title = it.get('title', '')[:120]
            res = it.get('resonance_count', 1)
            res_tag = f" x{res}" if res > 1 else ""
            lines.append(f"\n⚡ *[{score:.1f}]* [{src}{res_tag}]")
            lines.append(f"  {title}")
        lines.append("")
    
    lines.append("**━━━ 最新动态 ━━━**")
    display_items = critical_items + high_items
    for i, it in enumerate(display_items[:15]):
        score = it.get('overall_score', 0)
        src = it.get('source', '?')
        title = it.get('title', '')[:110]
        tim = it.get('raw_timeliness', 0)
        pro = it.get('raw_prominence', 0)
        lines.append(f"{i+1}. *[{score:.1f}|T:{tim:.0f}]* **{src}**: {title}")
    
    lines.append(f"\n━━━━━━━━━━━━━━━━━━")
    lines.append(f"_输入 /help 查看所有命令_")
    return "\n".join(lines)


def build_help_message() -> str:
    lines = [
        "📋 **OpenNews Matrix 命令列表**\n",
        "**新闻查询:**",
    ]
    for cmd, desc in COMMANDS.items():
        if cmd != "/help":
            lines.append(f"  `{cmd}` — {desc}")
    
    lines.extend([
        "",
        "**使用示例:**",
        "  `/tech` — 获取最新AI科技新闻",
        "  `/finance` — 获取金融市场动态",
        "  `/oracle` — 触发深度情报分析",
        "",
        "**提示:** 直接发送关键词也可搜索相关新闻",
        "",
        "_OpenNews Matrix v2.1 | Powered by RSS + AI_"
    ])
    return "\n".join(lines)


async def handle_command(command: str, chat_id: str) -> str:
    command = command.strip().lower()
    
    if command == "/help" or command == "/start":
        return build_help_message()
    
    if command == "/status":
        from opennews_mcp.tools.aggregator_rss import SOURCES
        tech_count = sum(1 for n, _ in SOURCES if any(k in n for k in [
            "MIT Technology", "Ars Technica", "VentureBeat", "TechCrunch",
            "The Verge", "Wired", "OpenAI", "DeepMind", "Google Research",
            "Hugging Face", "KDnuggets", "BAIR", "The Decoder", "Ben's Bites",
            "arXiv", "MIRI", "AWS", "Google Cloud"
        ]))
        return (
            f"📊 **系统状态报告**\n\n"
            f"**Bot Token:** {'✅ 已配置' if BOT_TOKEN else '❌ 未配置'}\n"
            f"**总信息源:** {len(SOURCES)} 个\n"
            f"**AI/科技源:** {tech_count} 个\n"
            f"**分类:** all/tech/finance/world/military/politics\n"
            f"**版本:** v2.1\n"
            f"**状态:** 🟢 运行中\n"
            f"\n_最后更新: {datetime.now(timezone(timedelta(hours=8))).strftime('%H:%M:%S')}_"
        )
    
    if command == "/oracle":
        from bot_f_oracle import run_oracle
        asyncio.create_task(run_oracle())
        return "🔮 **Oracle 分析已触发**\n\n深度情报分析正在进行中，请稍候...结果将自动推送。"
    
    if command in CATEGORY_MAP:
        category = CATEGORY_MAP[command]
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
                f"{EMOJI_MAP.get(category, '📰')} **暂无{category}新闻**\n\n"
                f"当前时段没有检测到相关的{category}类别新闻。\n"
                f"系统将继续监控，有新消息时自动推送。\n\n"
                f"_尝试 /new 查看全领域新闻_"
            )
        
        return format_news_message(items, category, fetched)
    
    return (
        "❓ *未知命令: `" + command + "`*\n\n"
        "可用命令:\n" +
        "\n".join("  " + cmd + " — " + desc for cmd, desc in COMMANDS.items()) +
        "\n\n_输入 /help 查看完整帮助_"
    )


async def get_updates(offset: int = 0, timeout: int = 30) -> tuple[list[dict], int]:
    result = await call_telegram_api(
        "getUpdates",
        offset=offset,
        timeout=timeout,
        allowed_updates=["message"]
    )
    
    if not result.get("ok"):
        return [], offset
    
    updates = result.get("result", [])
    new_offset = offset
    if updates:
        new_offset = updates[-1]["update_id"] + 1
    
    return updates, new_offset


async def process_message(message: dict):
    text = message.get("text", "").strip()
    chat_id = str(message["chat"]["id"])
    user = message.get("from", {})
    username = user.get("username") or user.get("first_name", "Unknown")
    
    if not text.startswith("/"):
        return
    
    print(f"[Command] @{username}: {text} (chat: {chat_id})")
    
    response = await handle_command(text, chat_id)
    success = await send_message(chat_id, response)
    
    if success:
        print(f"  ✅ Response sent ({len(response)} chars)")
    else:
        print(f"  ❌ Failed to send response")


async def run_bot():
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN_G / TECHBOTTOKEN not set.")
        print("   Set it with: $env:BOT_TOKEN_G='your-token'")
        return
    
    me = await call_telegram_api("getMe")
    if me.get("ok"):
        bot_info = me["result"]
        print(f"🤖 Bot started: @{bot_info.get('username', '?')} ({bot_info.get('first_name', '?')})")
        print(f"   ID: {bot_info.get('id')}")
    else:
        print("⚠️ Failed to get bot info, but continuing...")
    
    await call_telegram_api("setMyCommands", commands=[
        {"command": "/new", "description": "获取最新全领域新闻"},
        {"command": "/tech", "description": "获取AI/科技前沿"},
        {"command": "/finance", "description": "获取金融/加密动态"},
        {"command": "/world", "description": "获取全球突发"},
        {"command": "/military", "description": "获取军事冲突"},
        {"command": "/politics", "description": "获取政治博弈"},
        {"command": "/oracle", "description": "触发Oracle深度分析"},
        {"command": "/status", "description": "查看系统状态"},
        {"command": "/help", "description": "显示帮助"},
    ])
    
    print("\n📡 Listening for commands... (Ctrl+C to stop)\n")
    print("Available commands:")
    for cmd, desc in COMMANDS.items():
        print(f"  {cmd} — {desc}")
    print("")
    
    offset = 0
    while True:
        try:
            updates, offset = await get_updates(offset, timeout=30)
            
            for update in updates:
                if "message" in update:
                    await process_message(update["message"])
                    
        except KeyboardInterrupt:
            print("\n🛑 Bot stopped by user.")
            break
        except Exception as e:
            print(f"[Error] {e}")
            await asyncio.sleep(5)


async def test_single_command(command: str, chat_id: str = None):
    target_chat = chat_id or DEFAULT_CHAT_ID
    print(f"\n[Test] Command: {command} → Chat: {target_chat}")
    
    response = await handle_command(command, target_chat)
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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="OpenNews Matrix Bot")
    parser.add_argument("--test", help="Test a single command (e.g., /tech)")
    parser.add_argument("--chat-id", help="Target chat ID for test mode")
    parser.add_argument("--run", action="store_true", help="Run bot in polling mode")
    args = parser.parse_args()
    
    if args.test:
        asyncio.run(test_single_command(args.test, args.chat_id))
    elif args.run:
        asyncio.run(run_bot())
    else:
        print("Usage:")
        print("  python bot_command.py --run           # Start bot (polling mode)")
        print("  python bot_command.py --test /tech     # Test single command")
        print("  python bot_command.py --test /status   # Test status command")
        print("")
        print("Commands:", ", ".join(COMMANDS.keys()))
