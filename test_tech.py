import asyncio
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
os.environ['BOT_TOKEN_G'] = '8467815691:AAEzA9Jx7a9cjbeUnTOoNefPNwRz6gZDfPQ'

from opennews_mcp.tools.aggregator_rss import aggregate_free_news, SOURCES, TECH_KEYWORDS

async def main():
    print("=" * 60)
    print("  Testing AI/Tech Category Aggregation v2.1")
    print("=" * 60)

    tech_keywords = ["MIT Technology", "Ars Technica", "VentureBeat", "TechCrunch",
                     "The Verge", "Wired", "OpenAI", "DeepMind", "Google Research",
                     "Hugging Face", "KDnuggets", "BAIR", "TLDR AI", "The Decoder",
                     "Ben's Bites", "AlphaSignal", "Maginative", "Papers with Code",
                     "36kr AI"]
    
    tech_sources = [(n, u) for n, u in SOURCES if any(k in n for k in tech_keywords)]
    print(f"\n[Config] Tech sources matched: {len(tech_sources)}/{len(SOURCES)}")
    for name, url in tech_sources:
        print(f"   + {name}")

    result = await aggregate_free_news(
        None, max_items=20, send_to_telegram=False, category='tech'
    )

    fetched = result.get('total_fetched', 0)
    filtered = result.get('count', 0)
    print(f"\n[Results] Fetched: {fetched} | Filtered: {filtered}")
    print(f"[Category] {result.get('category', '?')}")

    items = result.get('items', [])
    errors = result.get('errors', [])

    if errors:
        print(f"\n[Errors] ({len(errors)}):")
        for e in errors[:20]:
            src = e.get('source', '?')
            err = str(e.get('error', 'unknown'))[:80]
            status = "OK" if "200" in err or "302" in err or "301" in err else "FAIL"
            print(f"   [{status}] {src}: {err}")

    print(f"\n[News Items] ({len(items)}):")
    sources_count = {}
    for i, it in enumerate(items):
        res = it.get('resonance_count', 1)
        res_tag = f" x{res}" if res > 1 else ""
        tim = it.get('raw_timeliness', 0)
        pro = it.get('raw_prominence', 0)
        src = it.get('source', '?')
        title = it.get('title', '').replace('\xa0', ' ')[:100]
        sources_count[src] = sources_count.get(src, 0) + 1
        print(f"  [{i+1}] {src}{res_tag} | T:{tim:.1f} P:{pro:.1f}")
        print(f"       {title}")

    print(f"\n[Source Distribution]:")
    for src, cnt in sorted(sources_count.items(), key=lambda x: -x[1]):
        is_tech = any(k in src for k in tech_keywords)
        tag = "[TECH]" if is_tech else "[LEAK]"
        print(f"   {tag} {src}: {cnt}")

if __name__ == "__main__":
    asyncio.run(main())
