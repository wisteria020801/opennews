import asyncio
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import httpx
from xml.etree import ElementTree as ET
from mcp.server.fastmcp import Context
from opennews_mcp.app import mcp
from opennews_mcp.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

SOURCES = [
    # Finance / Crypto (High Speed / Arbitrage)
    ("Wallstreetcn (华尔街见闻)", "https://api.wallstreetcn.com/v2/it/articles?limit=20&category=global"),
    ("Jin10 (金十数据)", "https://flash-api.jin10.com/get_flash_list?channel=-24"),
    ("Investing.com", "https://www.investing.com/rss/news.rss"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("The Block", "https://www.theblock.co/rss.xml"),
    ("Foresight News", "https://foresightnews.pro/rss"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews"),
    ("Coinbase", "https://blog.coinbase.com/feed"),
    ("Kraken", "https://blog.kraken.com/feed/"),
    ("CoinGecko", "https://blog.coingecko.com/rss"),
    ("CFTC", "https://www.cftc.gov/PressRoom/PressReleases/rss"),
    ("SEC", "https://www.sec.gov/rss/news/press.xml"),
    
    # Politics / World (Geopolitics)
    ("Reuters World", "https://feeds.reuters.com/reuters/worldNews"),
    ("AP News (美联社)", "https://apnews.com/hub/world-news/feed"),
    ("CNN World", "http://rss.cnn.com/rss/edition_world.rss"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("Politico", "https://rss.politico.com/politics-news.xml"),
    ("Fox News", "http://feeds.foxnews.com/foxnews/latest"),
    
    # Military / Defense (Conflict Monitoring)
    ("Defence Blog", "https://defence-blog.com/feed/"),
    ("Military.com", "http://www.military.com/rss-feeds/content?type=news"),
    ("Defense One", "https://www.defenseone.com/rss/all/"),
    
    # Entertainment / Social / Trends
    ("Variety", "https://variety.com/feed/"),
    ("E! Online", "https://www.eonline.com/news/rss.xml"),
    ("TMZ", "https://www.tmz.com/rss.xml"),
    ("YouTube: Bloomberg", "https://rsshub.app/youtube/channel/UCOAYqZ5qiQC78px6fLPz_OQ"),
    ("YouTube: CNBC", "https://rsshub.app/youtube/channel/UCvJJ_dzjViJCoLf5uK9txAw"),
]

KEYWORDS = re.compile(r"(SEC|ETF|listing|suspend|halt|hack|merger|liquidation|bankruptcy|court|lawsuit|approval|上市|暂停|黑客|诉讼|合并|破产|下架|批准|传闻|war|conflict|strike|election|policy|scandal|movie|star|army|navy|air force|missile|tank|drone|interest rate|fed|cpi|inflation|rates|rate hike|cut|stimulus|gdp|nfp|payroll|oil|gold|btc|eth|crypto|regulation|sanction|trade war|tariff|video|trailer|interview)", re.I)

PRIORITY = {
    "Wallstreetcn": 1,
    "Jin10": 1,
    "Reuters": 1,
    "AP News": 1,
    "The Block": 1,
    "Foresight News": 1,
    "Investing.com": 1,
    "Yahoo Finance": 1,
    "CNN World": 2,
    "Al Jazeera": 2,
    "CoinDesk": 2,
    "Politico": 2,
    "Fox News": 2,
    "Defense One": 2,
    "Defence Blog": 2,
    "Military.com": 2,
    "YouTube": 2, # High priority for video content
    "Twitter": 2,
    "Variety": 2,
    "TMZ": 2,
    "E! Online": 3,
}


def _rank(src: str) -> int:
    if not src:
        return 9
    for k, v in PRIORITY.items():
        if k.lower() in src.lower():
            return v
    return 8


def _parse_time(ts: str) -> datetime:
    if not ts:
        return datetime.now(timezone.utc)
    try:
        return parsedate_to_datetime(ts).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _parse_wallstreetcn(text: str) -> list[dict]:
    import json
    items = []
    try:
        data = json.loads(text)
        articles = data.get("data", {}).get("items", [])
        for art in articles:
            # 华尔街见闻 API 结构
            title = art.get("title", "")
            content = art.get("content_text", "") or art.get("digest", "")
            url = art.get("uri", "")
            ts = art.get("display_time", 0)
            
            # 过滤不需要的
            if not title: continue
            
            dt = datetime.fromtimestamp(ts, timezone.utc)
            items.append({
                "title": title.strip(),
                "link": url,
                "source": "Wallstreetcn",
                "time": dt,
                "summary": content[:200]
            })
    except Exception:
        pass
    return items

def _parse_jin10(text: str) -> list[dict]:
    import json
    items = []
    try:
        data = json.loads(text)
        flash_list = data.get("data", [])
        for flash in flash_list:
            # 金十 API 结构
            content = flash.get("data", {}).get("content", "")
            if not content: continue
            
            # 金十快讯通常没有标题，直接用内容前段做标题
            title = content[:50] + "..." if len(content) > 50 else content
            ts = flash.get("time_txt", "") # 格式可能需要处理，这里简化
            raw_time = flash.get("time", "") # "2023-10-27 10:00:00"
            
            try:
                dt = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=8)))
            except:
                dt = datetime.now(timezone.utc)

            link = flash.get("link", "")
            
            items.append({
                "title": title,
                "link": link,
                "source": "Jin10",
                "time": dt,
                "summary": content
            })
    except Exception:
        pass
    return items

def _parse_rss(xml: str, source: str) -> list[dict]:
    # Special handling for JSON APIs
    if "Wallstreetcn" in source:
        return _parse_wallstreetcn(xml)
    if "Jin10" in source:
        return _parse_jin10(xml)
        
    out = []
    try:
        # 尝试解析 JSON 格式 (某些 API 虽然叫 RSS 但返回 JSON)
        if xml.strip().startswith("{") or xml.strip().startswith("["):
             # 这里可以扩展其他 JSON 格式的处理
             pass

        root = ET.fromstring(xml)
    except Exception:
        return out
    channel = root.find("channel")
    if channel is not None:
        for item in channel.findall("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            pub_el = item.find("pubDate")
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            pub = _parse_time(pub_el.text.strip()) if pub_el is not None and pub_el.text else datetime.now(timezone.utc)
            if title:
                out.append({"title": title, "link": link, "source": source, "time": pub})
        return out
    for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
        title_el = entry.find("{http://www.w3.org/2005/Atom}title")
        link_el = entry.find("{http://www.w3.org/2005/Atom}link")
        pub_el = entry.find("{http://www.w3.org/2005/Atom}updated") or entry.find("{http://www.w3.org/2005/Atom}published")
        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        href = ""
        if link_el is not None:
            href = link_el.get("href", "").strip()
        pub = _parse_time(pub_el.text.strip()) if pub_el is not None and pub_el.text else datetime.now(timezone.utc)
        if title:
            out.append({"title": title, "link": href, "source": source, "time": pub})
    return out


async def _fetch(client: httpx.AsyncClient, name: str, url: str) -> list[dict]:
    try:
        # Add headers to mimic browser and avoid 403/301 blocks
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*"
        }
        resp = await client.get(url, timeout=10.0, headers=headers, follow_redirects=True)
        resp.raise_for_status()
        return _parse_rss(resp.text, name)
    except Exception:
        return []


def _filter(items: list[dict], max_items: int) -> list[dict]:
    seen = set()
    out = []
    for it in items:
        title = it.get("title", "")
        link = it.get("link", "")
        if not title:
            continue
        if not KEYWORDS.search(title):
            continue
        key = (title.lower(), link[:80])
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    out.sort(key=lambda x: (_rank(x.get("source", "")), -x["time"].timestamp()))
    return out[:max_items]


async def _send_telegram(lines: list[str], category: str = "all") -> str:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not lines:
        return "skip"
    
    bot_token = TELEGRAM_BOT_TOKEN
    chat_id = TELEGRAM_CHAT_ID
    
    # 装饰 Header
    headers = {
        "world": "🌍 **Alpha-Sentry | 全球哨兵**",
        "finance": "💹 **Beta-Tracker | 金融追踪**",
        "politics": "🏛️ **Politics-Eye | 政治观察**",
        "entertainment": "🎬 **Grassroot-Eye | 娱乐风向**",
        "military": "⚔️ **War-Room | 军事前线**",
        "tech": "🤖 **Tech-Radar | 科技雷达**",
        "all": "📰 **OpenNews | 综合聚合**"
    }
    header = headers.get(category, headers["all"])
    
    # 构建消息体 (支持 Markdown)
    msg_body = f"{header}\n━━━━━━━━━━━━━━━━━━\n" + "\n".join(lines) + "\n━━━━━━━━━━━━━━━━━━\n_Powered by Wisteria_"
    
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id, 
                "text": msg_body, 
                "parse_mode": "Markdown", # 启用 Markdown 美化
                "disable_web_page_preview": True
            },
        )
        try:
            r.raise_for_status()
            return "ok"
        except Exception as e:
            return f"error:{e}"


@mcp.tool()
async def aggregate_free_news(
    ctx: Context, 
    max_items: int = 20, 
    send_to_telegram: bool = True,
    category: str = "all",  # all, finance, tech, world
    bot_token: str = None,
    chat_id: str = None
) -> dict:
    """
    聚合免费 RSS 新闻源并可选推送到 Telegram。
    
    Args:
        max_items: 返回/发送的最大条数
        send_to_telegram: 是否推送到 TG
        category: 资讯类别 (all/finance/tech/world)，影响来源筛选
        bot_token: 可选，指定发送用的 Bot Token (覆盖默认)
        chat_id: 可选，指定发送用的 Chat ID (覆盖默认)
    """
    # 1. 根据 category 筛选源
    selected_sources = []
    for name, url in SOURCES:
        # 简单分类逻辑 (可根据实际需求细化)
        if category == "all":
            selected_sources.append((name, url))
        elif category == "finance" and name in ["SEC", "CFTC", "Reuters", "WSJ", "Financial Times", "Bloomberg", "Yahoo Finance", "Investing.com", "The Block", "Foresight News", "CoinDesk"]:
            selected_sources.append((name, url))
        elif category == "tech" and name in ["CoinDesk", "The Block", "TechCrunch", "Foresight News"]: # 示例
            selected_sources.append((name, url))
        elif category == "world" and name in ["Reuters", "BBC World", "BBC Politics", "CNN World", "Al Jazeera", "Reuters World"]: 
            selected_sources.append((name, url))
        elif category == "politics" and name in ["BBC Politics", "Reuters", "Politico", "Fox News Politics"]:
            selected_sources.append((name, url))
        elif category == "entertainment" and name in ["Variety", "E! Online", "TMZ", "YouTube: Bloomberg", "YouTube: CNBC", "Twitter: Elon Musk (Demo)"]:
            selected_sources.append((name, url))
        elif category == "military" and name in ["Defence Blog", "Military.com", "Defense One"]:
            selected_sources.append((name, url))
        # 默认回落到 crypto 相关源
        elif category not in ["all", "finance", "tech", "world", "politics", "entertainment", "military"] and name in ["CoinDesk", "Cointelegraph", "Coinbase"]:
             selected_sources.append((name, url))

    if not selected_sources and category != "all":
        # 如果分类筛选后为空，默认用全量，或者针对 crypto 优化
        selected_sources = SOURCES

    async with httpx.AsyncClient() as client:
        tasks = [asyncio.create_task(_fetch(client, name, url)) for name, url in selected_sources]
        results = await asyncio.gather(*tasks)
    
    items = []
    for arr in results:
        items.extend(arr)
    
    picked = _filter(items, max_items)
    lines = []
    for it in picked:
        tstr = it["time"].astimezone(timezone(timedelta(hours=8))).strftime("%H:%M")
        src = it.get("source", "")
        title = it.get("title", "").replace("[", "(").replace("]", ")").replace("*", "") # 简单的Markdown转义
        link = it.get("link", "")
        
        # 美化每一行
        line = f"⏰ `{tstr}` | *{src}*\n{title}"
        if link:
            line += f"\n[🔗 点击阅读]({link})"
        lines.append(line + "\n")
    
    status = None
    if send_to_telegram:
        # 临时覆盖全局配置 (如果传入了特定参数)
        global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
        original_token = TELEGRAM_BOT_TOKEN
        original_chat = TELEGRAM_CHAT_ID
        
        if bot_token:
            TELEGRAM_BOT_TOKEN = bot_token
        if chat_id:
            TELEGRAM_CHAT_ID = chat_id
            
        status = await _send_telegram(lines, category=category)
        
        # 恢复
        TELEGRAM_BOT_TOKEN = original_token
        TELEGRAM_CHAT_ID = original_chat

    return {
        "success": True,
        "category": category,
        "count": len(picked),
        "items": [
            {
                "title": it["title"],
                "link": it["link"],
                "source": it["source"],
                "time": it["time"].isoformat(),
                "rank": _rank(it["source"]),
            }
            for it in picked
        ],
        "telegram": status or "skip",
    }


if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    # 确保能找到 opennews_mcp 包
    root_dir = Path(__file__).resolve().parents[3]
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    
    # 手动运行测试
    print("Running aggregator test locally...")
    result = asyncio.run(aggregate_free_news(None, max_items=5, send_to_telegram=True))
    print(f"Result: {result}")
