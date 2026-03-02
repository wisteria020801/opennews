import httpx
import asyncio
import os

# 使用你提供的 Key
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyDP3V2Lgh4N2BRIyzvN9y_VAEGcL69GfOQ")

async def test_gemini():
    print(f"🔑 Testing Gemini API Key: {GEMINI_KEY[:6]}...{GEMINI_KEY[-4:]}")
    
    # Try gemini-2.0-flash-lite (Should be cheaper/faster)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={GEMINI_KEY}"
    
    # 极简 Prompt，只消耗极少 Token
    payload = {
        "contents": [{"parts": [{"text": "Reply with 'Hello from Gemini!' only."}]}]
    }
    
    print("🚀 Sending request to Google Cloud...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                print(f"✅ Success! Response: {text}")
                print("✨ Verification Passed: Your Oracle is now powered by Google Gemini.")
            else:
                print(f"❌ Failed. Status: {response.status_code}")
                print(f"Error: {response.text}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_gemini())
