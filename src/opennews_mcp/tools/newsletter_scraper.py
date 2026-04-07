import asyncio
import re
import html as html_lib
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx


NEWSLETTER_SOURCES = {
    "TLDR AI": {
        "url": "https://tldr.tech/ai",
        "parser": "tldr_ai",
        "priority": 1,
    },
    "AlphaSignal": {
        "url": "https://alphasignal.news/",
        "parser": "alphasignal",
        "priority": 1,
    },
    "Maginative": {
        "url": "https://maginative.com/",
        "parser": "maginative",
        "priority": 2,
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _clean_text(text: str) -> str:
    text = html_lib.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = text.replace('\xa0', ' ')
    return text


def _parse_tldr_ai(html_content: str, source_name: str) -> list[dict]:
    items = []
    
    article_blocks = re.findall(
        r'<a[^>]+href="([^"]+)"[^>]*>(?:\s*<[^>]*>\s*)*([^<]*(?:AI|GPT|LLM|model|openai|anthropic|google|meta|nvidia|machine learning|deep learning|neural|transformer|agent|robot|chip|gpu|training|inference|benchmark|research|paper|startup|funding)[^<]*)</a>',
        html_content, re.I
    )
    
    if not article_blocks:
        article_blocks = re.findall(
            r'<a[^>]+href="(/ai/[^"]+)"[^>]*>([^<]{20,300})</a>',
            html_content
        )
    
    for url, title in article_blocks[:15]:
        title = _clean_text(title)
        if len(title) < 15 or len(title) > 500:
            continue
        if not url.startswith("http"):
            url = f"https://tldr.tech{url}"
        items.append({
            "title": title,
            "link": url,
            "source": source_name,
            "time": datetime.now(timezone.utc),
        })
    
    return items


def _parse_alphasignal(html_content: str, source_name: str) -> list[dict]:
    items = []
    
    articles = re.findall(
        r'<a[^>]+href="([^"]+)"[^>]*>(?:\s*<[^>]*>\s*)*([^<]{20,400})</a>',
        html_content
    )
    
    ai_keywords = re.compile(
        r'(AI|GPT|LLM|model|openai|anthropic|gemini|claude|nvidia|'
        r'machine.learning|deep.learning|neural|transformer|agent|'
        r'robot|chip|gpu|training|inference|benchmark|research|paper|'
        r'startup|funding|open.source|fine.tune|quantization|RAG|embedding)',
        re.I
    )
    
    seen_titles = set()
    for url, title in articles[:30]:
        title = _clean_text(title)
        if title in seen_titles or len(title) < 20:
            continue
        if not ai_keywords.search(title):
            continue
        seen_titles.add(title)
        if not url.startswith("http"):
            url = f"https://alphasignal.news{url}"
        items.append({
            "title": title,
            "link": url,
            "source": source_name,
            "time": datetime.now(timezone.utc),
        })
        if len(items) >= 10:
            break
    
    return items


def _parse_maginative(html_content: str, source_name: str) -> list[dict]:
    items = []
    
    articles = re.findall(
        r'<a[^>]+href="([^"]+)"[^>]*>(?:\s*<h[23][^>]*>\s*)?([^<]{20,400})(?:\s*</h[23]>)?\s*</a>',
        html_content
    )
    
    if not articles:
        articles = re.findall(
            r'<article[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>([^<]{20,400})</a>',
            html_content, re.DOTALL
        )
    
    tool_keywords = re.compile(
        r'(AI|tool|app|platform|agent|bot|automation|productivity|'
        r'plugin|extension|integration|workflow|copilot|assistant|'
        r'generator|creator|builder|editor|manager|dashboard|API|SDK)',
        re.I
    )
    
    seen_titles = set()
    for url, title in articles[:25]:
        title = _clean_text(title)
        if title in seen_titles or len(title) < 20:
            continue
        seen_titles.add(title)
        if not url.startswith("http"):
            url = f"https://maginative.com{url}"
        is_tool_related = tool_keywords.search(title) or len(items) < 5
        items.append({
            "title": title,
            "link": url,
            "source": source_name,
            "time": datetime.now(timezone.utc),
            "_score_bonus": 2.0 if is_tool_related else 0.0,
        })
        if len(items) >= 8:
            break
    
    return items


PARSER_MAP = {
    "tldr_ai": _parse_tldr_ai,
    "alphasignal": _parse_alphasignal,
    "maginative": _parse_maginative,
}


async def fetch_newsletter(source_name: str) -> list[dict]:
    if source_name not in NEWSLETTER_SOURCES:
        return []
    
    config = NEWSLETTER_SOURCES[source_name]
    parser_func = PARSER_MAP.get(config["parser"])
    
    if not parser_func:
        return []
    
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(config["url"], headers=HEADERS)
            resp.raise_for_status()
            
            items = parser_func(resp.text, source_name)
            priority = config.get("priority", 2)
            for item in items:
                item["_newsletter_priority"] = priority
            
            print(f"   [Newsletter] {source_name}: {len(items)} items scraped")
            return items
            
    except Exception as e:
        print(f"   [Newsletter] {source_name} failed: {e}")
        return []


async def fetch_all_newsletters() -> list[dict]:
    all_items = []
    tasks = [fetch_newsletter(name) for name in NEWSLETTER_SOURCES]
    results = await asyncio.gather(*tasks)
    
    for items in results:
        all_items.extend(items)
    
    return all_items


if __name__ == "__main__":
    async def test():
        print("=" * 60)
        print("  Newsletter Scraper Test")
        print("=" * 60)
        
        for name in NEWSLETTER_SOURCES:
            print(f"\n--- {name} ---")
            items = await fetch_newsletter(name)
            for i, item in enumerate(items[:5]):
                print(f"  [{i+1}] {item['title'][:80]}")
                print(f"       {item['link']}")
        
        print(f"\n\nTotal: {sum(1 for _ in (await fetch_all_newsletters()))} items")
    
    asyncio.run(test())
