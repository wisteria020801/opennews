import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from opennews_mcp.tools.newsletter_scraper import fetch_all_newsletters, NEWSLETTER_SOURCES

async def main():
    print("=" * 60)
    print("  Newsletter Scraper Test v1.0")
    print("=" * 60)

    all_items = await fetch_all_newsletters()
    
    print(f"\n[Results] Total items: {len(all_items)}")
    
    sources_count = {}
    for i, it in enumerate(all_items):
        src = it.get('source', '?')
        title = it.get('title', '')[:80]
        sources_count[src] = sources_count.get(src, 0) + 1
        print(f"  [{i+1}] [{src}] {title}")
    
    print(f"\n[Source Distribution]:")
    for src, cnt in sorted(sources_count.items(), key=lambda x: -x[1]):
        print(f"   {src}: {cnt}")

if __name__ == "__main__":
    asyncio.run(main())
