import asyncio
import os
import sys
import httpx

def _get_chat_id() -> str:
    return (
        os.environ.get("OPENNEWS_TELEGRAM_CHAT_ID")
        or os.environ.get("CHAT_ID_A")
        or os.environ.get("CHAT_ID_F")
        or ""
    )


def _load_bots(chat_id: str) -> list[dict]:
    specs = [
        ("Bot A (World)", "BOT_TOKEN_A"),
        ("Bot B (Finance)", "BOT_TOKEN_B"),
        ("Bot C (Politics)", "BOT_TOKEN_C"),
        ("Bot D (Ent)", "BOT_TOKEN_D"),
        ("Bot E (Military)", "BOT_TOKEN_E"),
        ("Bot F (Oracle)", "BOT_TOKEN_F"),
    ]
    bots: list[dict] = []
    for name, env_key in specs:
        token = os.environ.get(env_key, "")
        if token:
            bots.append({"name": name, "token": token, "chat_id": chat_id})
    return bots

async def test_bot(bot):
    print(f"\nTesting {bot['name']}...")
    print(f"Token: {bot['token'][:5]}*** | Chat ID: {bot['chat_id']}")
    
    url = f"https://api.telegram.org/bot{bot['token']}/sendMessage"
    payload = {
        "chat_id": bot['chat_id'],
        "text": f"✅ **Ping!**\n我是 {bot['name']}，我还能说话！\n(调试时间: {os.times().elapsed})",
        "parse_mode": "Markdown"
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                print("   ✅ 成功发送！")
            else:
                print(f"   ❌ 发送失败: {resp.status_code}")
                print(f"   🔍 错误详情: {resp.text}")
    except Exception as e:
        print(f"   ❌ 连接错误: {e}")

async def main():
    print("🚀 开始全矩阵连通性测试 (Debug Mode)...")
    print("此脚本不抓取新闻，仅测试机器人能否在群里说话。")

    chat_id = _get_chat_id()
    if not chat_id:
        print("❌ 缺少 Chat ID。请设置 OPENNEWS_TELEGRAM_CHAT_ID 或 CHAT_ID_A/CHAT_ID_F。")
        return

    bots = _load_bots(chat_id)
    if not bots:
        print("❌ 缺少 Bot Token。请设置 BOT_TOKEN_A/B/C/D/E/F 环境变量后再运行。")
        return

    tasks = [test_bot(bot) for bot in bots]
    await asyncio.gather(*tasks)
    
    print("\n🏁 测试结束。如果你收到了消息，说明机器人是好的。")
    print("如果没收到，请检查上方报错的 '错误详情'。")

if __name__ == "__main__":
    asyncio.run(main())
