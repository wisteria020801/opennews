
import asyncio
import sys
import os

# Add the src directory to sys.path so we can import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from opennews_mcp.tools.telegram import send_telegram_notification

async def main():
    print("Testing Telegram notification...")
    try:
        # Context is not used in the function implementation, so we can pass None
        result = await send_telegram_notification("Hello from OpenNews MCP! Telegram integration test successful. 🚀", None)
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
