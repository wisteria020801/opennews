import httpx
import asyncio
import os

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyDP3V2Lgh4N2BRIyzvN9y_VAEGcL69GfOQ")

async def list_models():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_KEY}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        print(resp.text)

if __name__ == "__main__":
    asyncio.run(list_models())
