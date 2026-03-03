# Wisteria Intelligence News Matrix - 使用手册 (Manual)

> **Powered by Wisteria**
> 专业级信息套利矩阵，包含 5 个情报采集机器人和 1 个 AI 先知。

---

## 🕒 1. 自动更新时间表 (Auto Schedule)

系统已配置为全自动运行，无需人工干预。以下时间均为 **北京时间 (UTC+8)**：

| 时间 | 播报内容 | 目的 |
| :--- | :--- | :--- |
| **08:00** | 早安简报 | 汇总隔夜欧美市场收盘数据、凌晨突发新闻。 |
| **14:00** | 午间追踪 | 监控亚洲市场午盘、欧洲市场开盘前瞻。 |
| **20:00** | 晚间前瞻 | 汇总美股盘前消息、关键经济数据发布预警。 |

*注意：GitHub Actions 可能会有 10-30 分钟的随机延迟，这是云平台的正常现象。*

---

## 🤖 2. 机器人矩阵 (5+1 架构)

### 采集者 (Collectors)
这些机器人负责广撒网，抓取第一手情报。

1.  **🌍 Alpha-Sentry (哨兵)**
    *   **职责**: 全球突发、地缘政治。
    *   **源**: Reuters, AP, CNN.
2.  **💹 Beta-Tracker (追踪)**
    *   **职责**: 金融异动、加密货币。
    *   **源**: 华尔街见闻, 金十数据, Investing.com.
3.  **⚖️ Charlie-Watch (守望)**
    *   **职责**: 政治博弈、政策法规。
    *   **源**: Politico, Fox, SEC.
4.  **📡 Delta-Radar (雷达)**
    *   **职责**: 娱乐、舆情、社交热度。
    *   **源**: Variety, TMZ, YouTube, Weibo Hot.
5.  **⚔️ Echo-WarRoom (战情)**
    *   **职责**: 军事冲突、防务动态。
    *   **源**: Defence Blog, Military.com.

### 分析师 (Oracle)
6.  **🔮 Foxtrot-Oracle (先知)**
    *   **职责**: 阅读以上所有新闻，进行 AI 分析，输出红色预警。
    *   **大脑**: Google Gemini API (云端) / Ollama (本地)。

---

## 🛠️ 3. 常用指令 (Commands)

如果你想在非自动时间手动触发播报，可以在本地终端运行以下命令：

### 启动所有采集机器人 (A-E)
```bash
python src/run_multibot_matrix.py
```

### 启动先知进行 AI 分析 (F)
```bash
python src/bot_f_oracle.py
```

---

## ⚠️ 4. 故障排查 (Troubleshooting)

### Q: 为什么 8:00 准时没收到消息？
A: GitHub 的免费服务器资源是共享的，"08:00" 的任务可能会排队，通常在 08:05 - 08:30 之间送达。

### Q: 先知 (Oracle) 为什么显示 "Fallback Mode"？
A: 这说明 AI 调用失败了（可能是 API 限流或网络问题）。
*   不用担心，系统会自动降级为 **"关键词共振模式"**。
*   它依然会捕捉 "War", "Crash", "Bitcoin" 等敏感词并报警，只是没有具体的 AI 评语。

### Q: 我想修改 Token 怎么办？
A: 不要改代码！去 GitHub 仓库的 **Settings -> Secrets -> Actions** 里修改对应的 `TELEGRAM_BOT_TOKEN_X` 即可。

---

## 🔒 5. 安全提醒
*   你的 Gemini API Key 已内置在代码中以便云端运行。
*   如果觉得 Key 有泄漏风险，请去 Google AI Studio 重新生成一个，并在 GitHub Secrets 里添加 `GEMINI_API_KEY` 来覆盖默认值。
