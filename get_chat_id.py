import asyncio
import httpx
import sys

def _default_token() -> str:
    return (
        sys.argv[1]
        if len(sys.argv) > 1
        else (os.environ.get("BOT_TOKEN_A") or os.environ.get("OPENNEWS_TELEGRAM_BOT_TOKEN") or "")
    )

async def get_updates(token):
    print(f"🔍 正在检查机器人收到的最新消息 (Token: {token[:5]}***)...")
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            data = resp.json()
            
            if not data.get("ok"):
                print(f"❌ 请求失败: {data}")
                return

            results = data.get("result", [])
            if not results:
                print("⚠️  没有收到任何新消息。")
                print("💡 请现在往群里发一句话（比如 'test'），然后立刻重新运行此脚本！")
                return

            print(f"\n✅ 成功获取 {len(results)} 条消息。正在解析群 ID...")
            print("-" * 40)
            
            found_groups = set()
            for update in results:
                # 检查群消息
                if "message" in update and "chat" in update["message"]:
                    chat = update["message"]["chat"]
                    if chat["type"] in ["group", "supergroup", "channel"]:
                        chat_id = chat["id"]
                        title = chat.get("title", "No Title")
                        if chat_id not in found_groups:
                            print(f"🎯 发现群组: {title}")
                            print(f"🆔 Chat ID: {chat_id}")
                            print("-" * 40)
                            found_groups.add(chat_id)
            
            if not found_groups:
                print("⚠️  收到了消息，但似乎都是私聊 (Private)，没看到群消息。")
                print("💡 请确保机器人已经被拉进群，并且你在群里发了言。")

    except Exception as e:
        print(f"❌ 连接错误: {e}")

if __name__ == "__main__":
    import os

    token = _default_token()
    if not token:
        print("❌ 缺少 Bot Token。用法：python get_chat_id.py <BOT_TOKEN> 或设置 BOT_TOKEN_A / OPENNEWS_TELEGRAM_BOT_TOKEN")
        raise SystemExit(2)
    asyncio.run(get_updates(token))
