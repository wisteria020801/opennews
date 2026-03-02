# OpenNews MCP 架构与接入规划

本文档记录了当前系统的架构以及未来接入外部项目的路径。

## 1. 当前已接入 (Phase 1: 自动化聚合矩阵)
目前我们已经构建了一个基于 GitHub Actions 的多机器人新闻聚合系统，完全免费且自动化。

| 模块 | 已接入源/项目 | 状态 |
| --- | --- | --- |
| **Finance Bot** | Yahoo Finance, Investing.com, CoinDesk, The Block, Foresight News, **Wallstreetcn (华尔街见闻)**, **Jin10 (金十数据)** | ✅ 运行中 |
| **World Bot** | Reuters, CNN World, Al Jazeera, AP News | ✅ 运行中 |
| **Politics Bot** | Politico, Fox News, Reuters Politics | ✅ 运行中 |
| **Entertainment**| Variety, E! Online, TMZ | ✅ 运行中 |
| **Military** | Defence Blog, Military.com, Defense One | ✅ 运行中 |
| **核心引擎** | `aggregator_rss.py` (RSS/JSON 解析), `run_multibot_matrix.py` (矩阵调度) | ✅ 运行中 |
| **调度器** | GitHub Actions (`schedule_matrix.yml`) | ✅ 运行中 |

## 2. 待接入/规划中 (Phase 2: 深度数据与 AI)
以下是你提到的外部项目，我们将按照“低成本、高价值”的原则逐步接入。

### A. 深度数据源 (Data Ingestion)
| 项目 | 接入方式建议 | 难度 | 价值 |
| --- | --- | --- | --- |
| **TradingView** | 官方无免费 API。建议使用 `tvdatafeed` (Python 库) 或通过 Webhook 对接 TradingView Alerts。 | 中 | ⭐⭐⭐⭐⭐ (K线/指标) |
| **OpenSky Network**| 使用官方 `opensky-api` Python 库。需要注册免费账号。可监控私人飞机/军机动向。 | 低 | ⭐⭐⭐ (特种套利) |
| **NASA FIRMS** | 使用 NASA LANCE API。可监控全球火灾/冲突热点（对大宗商品/农业套利有用）。 | 低 | ⭐⭐ (另类数据) |
| **RSS-Bridge** | 自建 Docker 服务。用于把没有 RSS 的网站（如 Twitter, Instagram）强行转为 RSS。 | 中 | ⭐⭐⭐⭐ (补全缺失源) |
| **snscrape** | Python 库。用于无 API 抓取 Twitter/X 数据（替代收费 API）。 | 中 | ⭐⭐⭐⭐ (舆情监控) |

### B. AI 与 向量数据库 (Intelligence Layer)
这一层负责从海量新闻中“提纯”出交易信号。

| 项目 | 接入路径 | 作用 |
| --- | --- | --- |
| **Ollama** | 本地部署 (需 GPU) 或云端 API。用于运行 Llama 3 / Mistral 模型，分析新闻情感。 | 中 | ⭐⭐⭐⭐⭐ (大脑) |
| **llama.cpp** | Ollama 的底层。如果你想在 CPU/Mac 上跑模型，用这个。 | 高 | ⭐⭐⭐ (轻量化 AI) |
| **Milvus** | 向量数据库。用于存储新闻的 Embedding，实现“历史相似行情搜索”（例如：上次发生类似新闻时，BTC 涨了多少？）。 | 高 | ⭐⭐⭐⭐ (历史回测) |
| **FAISS** | Facebook 开源的向量检索库。Milvus 的轻量级替代品，适合单机运行。 | 中 | ⭐⭐⭐ (推荐起步用这个) |

## 3. 下一步行动建议
1.  **稳固 Phase 1**：观察当前 5 个机器人的运行情况，根据反馈微调关键词。
2.  **启动 Phase 2.1 (Twitter 监控)**：
    -   使用 `snscrape` 或 `RSS-Bridge` 监控关键人物（Elon Musk, Vitalik, CZ）。
    -   接入 Bot B (Finance)。
3.  **启动 Phase 2.2 (AI 过滤)**：
    -   尝试接入 Ollama（如果你有本地算力）或 DeepSeek API。
    -   使用 `prompt_template.md` 让 AI 帮你打分。

---
*Last Updated: 2026-03-02*
