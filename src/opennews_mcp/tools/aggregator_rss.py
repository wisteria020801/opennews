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
    ("Twitter: Elon Musk (via RSSHub)", "https://rsshub.app/twitter/user/elonmusk"),
    ("Weibo: Hot Search (via RSSHub)", "https://rsshub.app/weibo/search/hot"),
    ("Xiaohongshu: Tech Trends", "https://rsshub.app/xiaohongshu/topic/tech"),
    ("Xiaohongshu: Finance", "https://rsshub.app/xiaohongshu/topic/finance"),
    ("TikTok: Crypto Trends", "https://rsshub.app/tiktok/tag/crypto"),
    ("Whale Alert (Big Transfers)", "https://rsshub.app/twitter/user/whale_alert"),
    ("Economic Calendar (Investing.com)", "https://rsshub.app/investing/economic-calendar"),
    ("Fed Calendar (Federal Reserve)", "https://www.federalreserve.gov/feeds/press_monetary.xml"),

    # === AI & Technology (NEW — v2.1) ===
    # Tier 1: Core AI Media
    ("MIT Technology Review", "https://www.technologyreview.com/feed/"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    ("VentureBeat (AI)", "https://venturebeat.com/category/ai/feed/"),
    ("TechCrunch (AI)", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("Wired", "https://www.wired.com/feed/rss"),
    
    # Tier 2: AI Labs & Research (Fixed URLs)
    ("OpenAI News", "https://openai.com/news/rss.xml"),
    ("DeepMind Blog", "https://deepmind.google/blog/rss.xml"),
    ("Google Research Blog", "https://blog.google/technology/ai/rss/"),
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    
    # Tier 3: Specialized AI/Data Science
    ("KDnuggets (AI/ML)", "https://www.kdnuggets.com/feed"),
    ("MIT Tech Review (AI Topic)", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    ("BAIR Blog (Berkeley AI)", "https://bair.berkeley.edu/blog/feed.xml"),

    # Tier 4: AI Newsletters & Curated (High Signal — v2.1)
    ("The Decoder (AI)", "https://the-decoder.com/feed/"),
    ("Ben's Bites (AI)", "https://bensbites.com/feed"),
    
    # Tier 5: Research & Academic (Gold Standard)
    ("arXiv CS.AI (Papers)", "https://rss.arxiv.org/rss/cs.AI"),
    ("MIRI Blog (AI Safety)", "https://intelligence.org/feed"),
    
    # Tier 6: Cloud/Enterprise AI
    ("AWS Machine Learning Blog", "https://aws.amazon.com/blogs/machine-learning/feed/"),
    ("Google Cloud AI Blog", "https://cloud.google.com/blog/ai-and-machine-learning/rss"),
]

KEYWORDS = re.compile(r"(SEC|ETF|listing|suspend|halt|hack|merger|liquidation|bankruptcy|court|lawsuit|approval|上市|暂停|黑客|诉讼|合并|破产|下架|批准|传闻|war|conflict|strike|election|policy|scandal|movie|star|army|navy|air force|missile|tank|drone|interest rate|fed|cpi|inflation|rates|rate hike|cut|stimulus|gdp|nfp|payroll|oil|gold|btc|eth|crypto|regulation|sanction|trade war|tariff|video|trailer|interview|AI|artificial intelligence|LLM|GPT|Claude|Gemini|OpenAI|Anthropic|DeepMind|Google AI|model release|API|agent|MCP|machine learning|neural network|transformer|diffusion|training|inference|GPU|chip|semiconductor|NVIDIA|open source|framework|fine-tune|RAG|embedding|benchmark|SOTA|AGI|safety|alignment|regulation|AI act|chip act|data center|compute|scaling|reasoning|multimodal|vision|NLP|robotics|autonomous|开源|大模型|人工智能|芯片|算力|推理|训练)", re.I)

TECH_KEYWORDS = re.compile(
    r"(AI|artificial intelligence|GPT|Claude|Gemini|Llama|Qwen|Mistral|DeepSeek|"
    r"LLM|large language model|multimodal|vision language|text-to-image|image generation|"
    r"diffusion model|transformer|attention mechanism|neural network|deep learning|"
    r"machine learning|ML|reinforcement learning|RLHF|RLAIF|supervised fine.tuning|SFT|"
    r"training|inference|token|context window|parameters|weights|architecture|"
    r"OpenAI|Anthropic|Google DeepMind|Meta AI|Microsoft AI|xAI|Mistral AI|"
    r"Hugging Face|LangChain|LlamaIndex|PyTorch|TensorFlow|JAX|ONNX|"
    r"GPU|NVIDIA|AMD|TPU|chip|semiconductor|TSMC|data center|compute|"
    r"agent|autonomous agent|MCP|tool use|function calling|RAG|retrieval|"
    r"embedding|vector database|knowledge graph|prompt engineering|chain-of-thought|"
    r"benchmark|evaluation|SOTA|state.of.the.art|leaderboard|arena|"
    r"open source|foundation model|fine.tune|quantization|distillation|pruning|"
    r"AGI|general intelligence|alignment|safety|red.teaming|guardrail|"
    r"robotics|self.driving|computer vision|NLP|speech recognition|"
    r"code generation|Copilot|Cursor|IDE|developer tool|"
    r"startup|funding|series.|valuation|IPO|acquisition|unicorn|"
    r"research paper|arXiv|conference|NeurIPS|ICML|ICLR|CVPR|ACL|EMNLP|"
    r"开源|大模型|人工智能|机器学习|深度学习|神经网络|芯片|算力|推理|训练|"
    r"生成式|多模态|智能体|自动驾驶|计算机视觉|自然语言处理)",
    re.I
)

PRIORITY = {
    "Wallstreetcn": 1,
    "Jin10": 1,
    "Reuters": 1,
    "AP News": 1,
    "The Block": 1,
    "Foresight News": 1,
    "Investing.com": 1,
    "Yahoo Finance": 1,
    "OpenAI": 1,
    "DeepMind": 1,
    "Anthropic": 1,
    "Google Research": 1,
    "MIT Technology Review": 1,
    "The Decoder": 1,
    "Hugging Face": 1,
    "TechCrunch": 1,
    "Ars Technica": 1,
    "VentureBeat": 1,
    "Ben's Bites": 1,
    "arXiv": 1,
    "AWS": 1,
    "Google Cloud": 1,
    "MIRI": 2,
    "CNN World": 2,
    "Al Jazeera": 2,
    "CoinDesk": 2,
    "Politico": 2,
    "Fox News": 2,
    "Defense One": 2,
    "Defence Blog": 2,
    "Military.com": 2,
    "YouTube": 2,
    "Twitter": 2,
    "Variety": 2,
    "TMZ": 2,
    "E! Online": 3,
    "The Verge": 2,
    "Wired": 2,
    "KDnuggets": 2,
    "BAIR": 2,
    "Papers with Code": 2,
}


def _rank(src: str) -> int:
    if not src:
        return 9
    for k, v in PRIORITY.items():
        if k.lower() in src.lower():
            return v
    return 8


HIGH_WEIGHT_ENTITIES = {
    "BTC", "BITCOIN", "ETH", "ETHEREUM", "SOL", "SOLANA",
    "BNB", "BINANCE", "COINBASE", "USDT", "USDC", "TETHER",
    "SEC", "CFTC", "FED", "FEDERAL RESERVE", "ECB", "BOJ", "PBOC",
    "CPI", "NFP", "NONFARM", "GDP", "INFLATION", "INTEREST RATE",
    "FOMC", "RATE HIKE", "RATE CUT", "QT", "QE",
    "UKRAINE", "RUSSIA", "IRAN", "ISRAEL", "GAZA", "CHINA", "TAIWAN",
    "TRUMP", "BIDEN", "PUTIN", "XI", "NETANYAHU",
    "OPENAI", "GOOGLE", "META", "APPLE", "MICROSOFT", "NVIDIA",
    "MCP", "LLM", "GPT", "GEMINI", "CLAUDE", "ANTHROPIC",
    "ETF", "IPO", "MERGER", "ACQUISITION", "BANKRUPTCY", "LIQUIDATION",
    "AI", "ARTIFICIAL INTELLIGENCE", "AGI", "LLM", "TRANSFORMER",
    "DEEPMIND", "HUGGING FACE", "LANGCHAIN", "PYTORCH", "TENSORFLOW",
}


def _extract_entities(title: str) -> set[str]:
    found = set()
    for entity in HIGH_WEIGHT_ENTITIES:
        if entity in title.upper():
            found.add(entity)
    return found


def _tokenize(text: str) -> set[str]:
    import re
    english = set(re.findall(r'[a-zA-Z]{2,}', text.lower()))
    chinese = set(text[i:i+2] for i in range(len(text)-1) if '\u4e00' <= text[i] <= '\u9fff')
    return english | chinese


def _jaccard(set_a: set, set_b: set) -> float:
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _mark_resonant(item_a: dict, item_b: dict):
    item_a["resonance_count"] += 1
    item_b["resonance_count"] += 1
    item_a["co_sources"].append(item_b.get("source", ""))
    item_b["co_sources"].append(item_a.get("source", ""))


def _entity_resonance(items: list[dict], time_window_minutes: int = 30) -> list[dict]:
    n = len(items)
    for i in range(n):
        items[i]["resonance_count"] = 1
        items[i]["co_sources"] = []
        entities_i = _extract_entities(items[i].get("title", ""))
        time_i = items[i].get("time")
        
        for j in range(i + 1, n):
            entities_j = _extract_entities(items[j].get("title", ""))
            time_j = items[j].get("time")
            
            shared = entities_i & entities_j
            if len(shared) >= 2:
                if time_i and time_j:
                    delta = abs((time_i - time_j).total_seconds()) / 60
                    if delta <= time_window_minutes:
                        _mark_resonant(items[i], items[j])
                else:
                    _mark_resonant(items[i], items[j])
    
    return items


def detect_resonance(items: list[dict],
                     threshold: float = 0.4,
                     use_entity_first: bool = True) -> list[dict]:
    if use_entity_first:
        items = _entity_resonance(items)
    
    n = len(items)
    for i in range(n):
        title_a = _tokenize(items[i]["title"])
        
        for j in range(i + 1, n):
            source_b = items[j].get("source", "")
            if source_b in items[i].get("co_sources", []):
                continue
            
            if (items[i].get("link") and items[i]["link"] == items[j].get("link")):
                _mark_resonant(items[i], items[j])
                continue
            
            title_b = _tokenize(items[j]["title"])
            sim = _jaccard(title_a, title_b)
            if sim >= threshold:
                _mark_resonant(items[i], items[j])
    
    return items


def calc_timeliness(pub_time: datetime, now: datetime = None) -> float:
    if now is None:
        now = datetime.now(timezone.utc)
    delta_minutes = (now - pub_time).total_seconds() / 60
    
    if delta_minutes <= 30:   return 10.0
    elif delta_minutes <= 120: return 9.0
    elif delta_minutes <= 360: return 7.0
    elif delta_minutes <= 720: return 5.0
    elif delta_minutes <= 1440: return 3.0
    else: return 0.0


def calc_prominence(source: str, resonance_count: int) -> float:
    base_score = {1: 8.0, 2: 5.0, 3: 3.0}.get(_rank(source), 2.0)
    resonance_bonus = min((resonance_count - 1) * 1.5, 2.0)
    return min(base_score + resonance_bonus, 10.0)


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


def _filter(items: list[dict], max_items: int, enable_resonance: bool = True, category: str = None) -> list[dict]:
    keyword_pattern = TECH_KEYWORDS if category == "tech" else KEYWORDS
    seen = set()
    out = []
    cutoff_hours = 48 if category == "tech" else 24
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cutoff_hours)
    
    for it in items:
        title = it.get("title", "")
        link = it.get("link", "")
        pub_time = it.get("time")
        
        if not title:
            continue
            
        if not keyword_pattern.search(title):
            continue
            
        if pub_time and pub_time < cutoff:
            continue

        key = (title.lower(), link[:80])
        if key in seen:
            continue
        seen.add(key)
        
        it["resonance_count"] = 1
        it["co_sources"] = []
        it["raw_timeliness"] = calc_timeliness(pub_time) if pub_time else 10.0
        out.append(it)
        
    if enable_resonance and len(out) > 1:
        out = detect_resonance(out)
    
    for it in out:
        it["raw_prominence"] = calc_prominence(it.get("source", ""), it.get("resonance_count", 1))
        
    out.sort(key=lambda x: (_rank(x.get("source", "")), -x["time"].timestamp()))
    return out[:max_items]


async def _send_telegram(lines: list[str], category: str = "all", bot_token: str = None, chat_id: str = None) -> str:
    """发送消息到 Telegram Bot"""
    if not lines:
        return "skip"
    
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
        # Use provided bot_token/chat_id if available, else use global
        target_token = bot_token or TELEGRAM_BOT_TOKEN
        target_chat = chat_id or TELEGRAM_CHAT_ID
        
        # Ensure chat_id is integer-like if possible (but Telegram API accepts string for channel username @channel)
        # If it's a private/group ID (e.g. "-100..."), ensure it's a string or int.
        
        r = await c.post(
            f"https://api.telegram.org/bot{target_token}/sendMessage",
            json={
                "chat_id": target_chat, 
                "text": msg_body, 
                "parse_mode": "Markdown", # 启用 Markdown 美化
                "disable_web_page_preview": True
            },
        )
        try:
            r.raise_for_status()
            return "ok"
        except Exception as e:
            return f"error:{e} (Response: {r.text})"


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
    # 1. 根据 category 筛选源 (v2.1 — 新增AI科技源)
    selected_sources = []
    STRICT_CATEGORIES = {"tech", "finance", "world", "politics", "entertainment", "military"}
    
    for name, url in SOURCES:
        if category == "all":
            selected_sources.append((name, url))
        elif category == "finance" and any(k in name for k in ["Wallstreetcn", "Jin10", "Investing", "Yahoo Finance", "The Block", "Foresight", "CoinDesk", "Cointelegraph", "Coinbase", "Kraken", "CoinGecko", "CFTC", "SEC", "Reuters Business", "Whale Alert"]):
            selected_sources.append((name, url))
        elif category == "tech" and any(k in name for k in ["MIT Technology", "Ars Technica", "VentureBeat", "TechCrunch", "The Verge", "Wired", "OpenAI", "DeepMind", "Google Research", "Hugging Face", "KDnuggets", "BAIR", "The Decoder", "Ben's Bites", "arXiv", "MIRI", "AWS", "Google Cloud"]):
            selected_sources.append((name, url))
        elif category == "world" and any(k in name for k in ["Reuters World", "AP News", "CNN World", "Al Jazeera", "Politico", "Fox News"]): 
            selected_sources.append((name, url))
        elif category == "politics" and any(k in name for k in ["Politico", "Fox News", "CNN World", "Al Jazeera"]):
            selected_sources.append((name, url))
        elif category == "entertainment" and any(k in name for k in ["Variety", "E! Online", "TMZ", "YouTube:", "Twitter:", "Weibo:", "Xiaohongshu:", "TikTok:"]):
            selected_sources.append((name, url))
        elif category == "military" and any(k in name for k in ["Defence Blog", "Military.com", "Defense One"]):
            selected_sources.append((name, url))
        elif category not in STRICT_CATEGORIES:
             selected_sources.append((name, url))

    if not selected_sources and category in STRICT_CATEGORIES:
        print(f"[WARN] No sources matched for category='{category}', using all sources as fallback")
        selected_sources = SOURCES

    async with httpx.AsyncClient() as client:
        tasks = [asyncio.create_task(_fetch(client, name, url)) for name, url in selected_sources]
        results = await asyncio.gather(*tasks)
    
    items = []
    for arr in results:
        items.extend(arr)
    
    picked = _filter(items, max_items, category=category)
    lines = []
    for it in picked:
        tstr = it["time"].astimezone(timezone(timedelta(hours=8))).strftime("%H:%M")
        src = it.get("source", "")
        title = it.get("title", "").replace("[", "(").replace("]", ")").replace("*", "") # 简单的Markdown转义
        link = it.get("link", "")
        res_count = it.get("resonance_count", 1)
        co_srcs = it.get("co_sources", [])
        
        line = f"⏰ `{tstr}` | *{src}*"
        if res_count > 1:
            co_str = ", ".join(co_srcs[:3])
            line += f" 🔥×{res_count} ({co_str})"
        line += f"\n{title}"
        if link:
            line += f"\n[🔗 点击阅读]({link})"
        lines.append(line + "\n")
    
    status = None
    if send_to_telegram:
        # 临时覆盖全局配置 (如果传入了特定参数)
        # Note: We now pass token/chat_id directly to _send_telegram via a modified signature or globals
        # But _send_telegram uses global variables by default. 
        # Let's refactor _send_telegram to accept arguments to avoid global state issues.
        
        status = await _send_telegram(lines, category=category, bot_token=bot_token, chat_id=chat_id)

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
                "resonance_count": it.get("resonance_count", 1),
                "co_sources": it.get("co_sources", []),
                "raw_timeliness": round(it.get("raw_timeliness", 0), 1),
                "raw_prominence": round(it.get("raw_prominence", 0), 1),
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
