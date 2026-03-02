import httpx
import asyncio

# 将你的机器人 Token 填在这里，或者运行时传入
# 示例：你可以用刚才申请的任何一个 Bot Token，因为它们都在同一个群里
TEST_BOT_TOKEN = "8779113331:AAFcreicqAYw3o1kpXuM0tg18_M9OK5BwYc" # Bot A

async def get_updates():
    print(f"正在查询 Bot ({TEST_BOT_TOKEN[:10]}...) 的更新...")
    url = f"https://api.telegram.org/bot{TEST_BOT_TOKEN}/getUpdates"
    
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
