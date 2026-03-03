import asyncio
import os
import httpx

# --- 你的配置 (从代码中提取的默认值) ---
# 如果这些 Token 是旧的，请直接在这里修改测试！
BOTS = [
    {"name": "Bot A (World)", "token": "8779113331:AAFcreicqAYw3o1kpXuM0tg18_M9OK5BwYc", "chat_id": "-1003590230315"},
    {"name": "Bot B (Finance)", "token": "8620644736:AAEbQO4Pyd85DSnl9sWeNarvFoE_eHJi6Wc", "chat_id": "-1003590230315"},
    {"name": "Bot C (Politics)", "token": "8796569408:AAF92dVSIpePhNah-_9oSiQrN336LeuehKY", "chat_id": "-1003590230315"},
    {"name": "Bot D (Ent)", "token": "8761221962:AAH30LkK8w3_0MYskER1SEHOFKkKZm1gDWE", "chat_id": "-1003590230315"},
    {"name": "Bot E (Military)", "token": "8522929670:AAEsHh99W4M_erlW5vgsymJFDlqTmJpRHSY", "chat_id": "-1003590230315"},
    {"name": "Bot F (Oracle)", "token": "8779113331:AAFcreicqAYw3o1kpXuM0tg18_M9OK5BwYc", "chat_id": "-1003590230315"}, # 默认复用 A
]

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
    
    tasks = [test_bot(bot) for bot in BOTS]
    await asyncio.gather(*tasks)
    
    print("\n🏁 测试结束。如果你收到了消息，说明机器人是好的。")
    print("如果没收到，请检查上方报错的 '错误详情'。")

if __name__ == "__main__":
    asyncio.run(main())
