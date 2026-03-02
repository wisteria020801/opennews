# Wisteria Intelligence News Matrix (OpenNews-MCP)

> **Powered by Wisteria Intelligence**  
> An advanced, multi-bot information arbitrage system for real-time global intelligence.

## 1. System Architecture: The "5+1" Matrix

This system implements a professional intelligence gathering network consisting of 5 specialized "Collector" bots and 1 central "Oracle" bot.

### The Collectors (Information Gathering)
These bots run in parallel to scan high-frequency data sources.

| Bot Code | Agent Name | Focus Area | Key Sources |
| :--- | :--- | :--- | :--- |
| **A** | **🌍 Alpha-Sentry** | Global News & Geopolitics | Reuters World, AP, CNN, Al Jazeera |
| **B** | **💹 Beta-Tracker** | Finance & Crypto Arbitrage | Wallstreetcn, Jin10, Investing.com, The Block |
| **C** | **⚖️ Charlie-Watch** | Politics & Policy | Politico, Fox News, Government Feeds (SEC/CFTC) |
| **D** | **📡 Delta-Radar** | Tech, Military & Social | Defence Blog, Variety, TMZ, YouTube Trends |
| **E** | **(Reserved)** | (Expansion Slot) | *Currently covered by Delta-Radar* |

### The Oracle (Analysis & Insight)
| Bot Code | Agent Name | Role | Function |
| :--- | :--- | :--- | :--- |
| **F** | **🔮 Echo-Oracle** | Synthesis & Red Alerts | Runs *after* collectors. Analyzes cross-domain data for "Red Alerts" (e.g., War + Market Crash). |

---

## 2. Data Sources (High-Value Feeds)

We have integrated over 20+ high-value, free data sources, optimized for speed and reliability.

### 🚀 Finance & Crypto (Arbitrage Focused)
*   **Wallstreetcn (华尔街见闻)**: Real-time global financial news (JSON API).
*   **Jin10 (金十数据)**: High-speed flash news for trading (JSON API).
*   **Investing.com**: Global markets.
*   **Yahoo Finance**: Stock market updates.
*   **The Block / Foresight News**: Crypto industry deep dives.
*   **CoinDesk / Cointelegraph**: Crypto market movements.
*   **SEC / CFTC**: Regulatory press releases.

### 🌍 Geopolitics & World
*   **Reuters World / Business**: Top-tier global wire service.
*   **AP News**: Associated Press global feed.
*   **Al Jazeera / CNN**: Regional coverage.

### ⚔️ Military & Defense
*   **Defence Blog**: Military hardware and conflict news.
*   **Defense One**: Defense policy and strategy.
*   **Military.com**: Operational news.

### 🎭 Social & Entertainment
*   **Variety**: Entertainment industry business.
*   **TMZ**: Celebrity and social trends.
*   **YouTube (RSSHub)**: Tracking Bloomberg/CNBC video feeds.

---

## 3. Deployment & Usage

### Prerequisites
*   Python 3.10+
*   Telegram Bot Tokens (5-6 tokens recommended)
*   GitHub Account (for automated scheduling)

### Configuration
Set the following secrets in your GitHub Repository or `.env` file:

```bash
# Telegram Configuration
TELEGRAM_BOT_TOKEN_A="<Alpha-Sentry Token>"
TELEGRAM_BOT_TOKEN_B="<Beta-Tracker Token>"
TELEGRAM_BOT_TOKEN_C="<Charlie-Watch Token>"
TELEGRAM_BOT_TOKEN_D="<Delta-Radar Token>"
TELEGRAM_BOT_TOKEN_ORACLE="<Echo-Oracle Token>" # Optional, defaults to Bot A if missing
TELEGRAM_CHAT_ID="<Your Target Channel ID>"
```

### Manual Execution (Local)
To run the full matrix cycle immediately:

```bash
# 1. Run the Collectors (A-D)
python src/run_multibot_matrix.py

# 2. Run the Oracle (F)
python src/bot_e_oracle.py
```

### Automated Scheduling (GitHub Actions)
The system is configured to run automatically via `.github/workflows/schedule_matrix.yml`.
*   **Schedule**: Runs every 6 hours (00:00, 06:00, 12:00, 18:00 UTC).
*   **Workflow**:
    1.  Sets up Python environment.
    2.  Installs dependencies.
    3.  Executes `run_multibot_matrix.py` (Collectors).
    4.  Executes `bot_e_oracle.py` (Oracle).

---

## 4. Integration with ClawDBot (OpenClaw)

This project is built on the **Model Context Protocol (MCP)**, making it "Skill-Ready" for advanced AI agents like ClawDBot.

### Method A: SSH MCP (Recommended for Remote Servers)
If ClawDBot supports SSH MCP connections:
1.  Deploy this repo to your cloud server.
2.  Configure ClawDBot to connect via SSH to this directory.
3.  ClawDBot will automatically discover the `opennews_mcp` server and its tools (`aggregator_rss`, `get_latest_news`, etc.).

### Method B: As a Skill Module
To "package" this as a skill for ClawDBot:
1.  Ensure ClawDBot can execute Python scripts or MCP servers.
2.  The file `src/opennews_mcp/server.py` exposes the core logic as an MCP server.
3.  Add the following command to ClawDBot's MCP configuration:
    ```json
    "opennews": {
      "command": "python",
      "args": ["src/opennews_mcp/server.py"]
    }
    ```

### Future Roadmap
*   **LLM Integration**: Connect the "Oracle" to a local LLM (Ollama/Llama 3) for real semantic analysis instead of keyword matching.
*   **Interactive Mode**: Allow users to query the bot (e.g., "/analyze BTC price").
