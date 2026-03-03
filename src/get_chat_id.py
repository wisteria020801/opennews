import httpx
import asyncio
import os
import sys

def _get_token() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    return os.environ.get("BOT_TOKEN_A") or os.environ.get("OPENNEWS_TELEGRAM_BOT_TOKEN") or ""

async def get_updates():
    token = _get_token()
    if not token:
        print("❌ 缺少 Bot Token。用法：python src/get_chat_id.py <BOT_TOKEN> 或设置 BOT_TOKEN_A / OPENNEWS_TELEGRAM_BOT_TOKEN")
        return

    print(f"正在查询 Bot ({token[:10]}...) 的更新...")
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            
            if not data.get("ok"):
                print(f"❌ API 错误: {data}")
                return

            results = data.get("result", [])
            if not results:
                print("⚠️  没有收到消息。请确保：")
                print("   1. 你已经把这个机器人拉进了群")
                print("   2. 机器人在群里是管理员（或者你刚刚在群里发了一条消息）")
                print("   3. 在群里随便发一条消息（比如 'hello'），然后再运行此脚本")
                return

            print("\n✅ 收到以下消息更新：")
            found_groups = set()
            
            for update in results:
                msg = update.get("message") or update.get("my_chat_member")
                if not msg: continue
                
                chat = msg.get("chat", {})
                chat_id = chat.get("id")
                chat_title = chat.get("title", "Private/Unknown")
                chat_type = chat.get("type")
                
                print(f"   - Chat ID: {chat_id} | Title: {chat_title} | Type: {chat_type}")
                
                if chat_type in ["group", "supergroup"]:
                    found_groups.add((chat_id, chat_title))

            if found_groups:
                print("\n🎉 发现群组 ID (请复制这个 ID 到 run_multibot_matrix.py):")
                for gid, gtitle in found_groups:
                    print(f"   👉 {gid}  (群名: {gtitle})")
            else:
                print("\n⚠️  未发现群组消息。请在群里发一条消息再试。")

        except Exception as e:
            print(f"❌ 请求失败: {e}")

if __name__ == "__main__":
    asyncio.run(get_updates())
