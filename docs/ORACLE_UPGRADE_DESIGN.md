# Oracle Bot 结构化升级设计方案 v2.1

> 从"新闻搬运工"到"情报分析官"的架构升级路径
> v2.1: 根据落地评审反馈修订 — Proximity 拆分/实体共振/推送策略优化/JSON 容错增强

---

## 1. 现状诊断

### 1.1 当前数据流

```
36个RSS源 → aggregator_rss.py (并发抓取+关键词过滤+去重+排序)
    → run_multibot_matrix.py (按category分发给Bot A~E推送到Telegram)
    → bot_f_oracle.py (重新抓取全量 → 拼接成文本 → 喂给Gemini → 自由文本输出)
```

### 1.2 核心痛点

| # | 痛点 | 位置 | 影响 |
|---|------|------|------|
| P1 | **Oracle 重复抓取** | `bot_f_oracle.py:42-48` | Bot A~E 已经抓过一遍，Oracle 又重新调用 `aggregate_free_news()`，浪费时间和 API 额度 |
| P2 | **自由文本 Prompt** | `bot_f_oracle.py:61-79` | Gemini 返回 Markdown 文本，无法程序化处理（排序/过滤/存档） |
| P3 | **无共振检测** | `aggregator_rss.py` 全局 | 36 个源可能同时报同一事件，但系统不知道，AI 拿到的只是重复标题列表 |
| P4 | **无结构化评分** | `bot_f_oracle.py` 全局 | "打分"只存在于 AI 输出文本中，无法做 `timeliness > 9` 这类程序化筛选 |
| P5 | **Telegram 展示扁平** | `bot_f_oracle.py:148-165` | 所有信息堆在一条消息里，CRITICAL 和 NOISE 同级展示 |

### 1.3 当前代码关键位置

- **源定义**: [aggregator_rss.py:14-49](src/opennews_mcp/tools/aggregator_rss.py#L14-L49) — `SOURCES` 列表（36 个源）
- **关键词过滤**: [aggregator_rss.py:51](src/opennews_mcp/tools/aggregator_rss.py#L51) — `KEYWORDS` 正则
- **优先级**: [aggregator_rss.py:53-77](src/opennews_mcp/tools/aggregator_rss.py#L53-L77) — `PRIORITY` 字典
- **聚合函数**: [aggregator_rss.py:230-290](src/opennews_mcp/tools/aggregator_rss.py#L230-L290) — `aggregate_free_news()`
- **Oracle 入口**: [bot_f_oracle.py:36](src/opennews_mcp/src/bot_f_oracle.py#L36) — `run_oracle()`
- **当前 Prompt**: [bot_f_oracle.py:61-79](src/opennews_mcp/src/bot_f_oracle.py#L61-L79) — 自由文本格式
- **调度器**: [.github/workflows/schedule_matrix.yml](.github/workflows/schedule_matrix.yml) — 每 2 小时触发

---

## 2. 目标架构

### 2.1 升级后数据流

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions 调度                        │
│                  每 2 小时 (schedule_matrix.yml)              │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
           ┌───────────────────────────────┐
           │   Engine: IntelligenceHub     │  ← 新增：统一情报引擎
           │   (替代 run_multibot_matrix)   │
           └───────────┬───────────────────┘
                       │
          ┌────────────┼────────────────┐
          ▼            ▼                ▼
   ┌────────────┐ ┌──────────┐  ┌──────────────┐
   │ RSS Fetcher│ │ Resonance │  │ Scoring      │
   │ (36源并发) │ │ Detector │  │ Engine       │
   │            │ │ (新增)    │  │ (五维打分)    │
   └─────┬──────┘ └─────┬────┘  └──────┬───────┘
       │               │               │
       ▼               ▼               ▼
   ┌──────────────────────────────────────────┐
   │        Structured News Feed              │
   │  [{title, source, time, resonance_count, │
   │    raw_scores: {t,i,p,p,a}}]             │
   └──────────────────┬───────────────────────┘
                      │
         ┌────────────┼────────────────┐
         ▼            ▼                ▼
   ┌──────────┐ ┌──────────┐  ┌──────────┐
   │ Bot A~E  │ │ Oracle   │  │ Archive  │
   │ 分类推送  │ │ AI增强   │  │ 存档(可选)│
   └──────────┘ └─────┬────┘  └──────────┘
                    │
                    ▼
           ┌────────────────┐
           │  Gemini API     │
           │  (结构化JSON)   │
           └───────┬────────┘
                   ▼
           ┌────────────────────┐
           │  Intelligence Pack │
           │  [5W1H + 五维评分] │
           └───────┬────────────┘
                   ▼
           ┌────────────────┐
           │  Telegram 推送  │
           │  分级 + 滤镜    │
           └────────────────┘
```

### 2.2 核心设计原则

1. **Single Source of Truth**: 只抓一次 RSS，所有 Bot 共享同一份数据
2. **Structured First**: 数据在进入 AI 前就已经是结构化的
3. **Graceful Degradation**: Gemini 挂了也能用关键词 fallback 出基础评分
4. **Telegram Friendly**: 输出严格控制在消息长度限制内

---

## 3. 数据模型定义

### 3.1 RawNewsItem（原始新闻条目）

从 RSS 抓取后的原始条目，在现有基础上扩展：

```python
@dataclass
class RawNewsItem:
    title: str                          # 新闻标题
    link: str                           # 原文链接
    source: str                         # 来源名称（如 "Reuters World"）
    time: datetime                      # 发布时间 (UTC)
    summary: str = ""                   # 摘要（如果有）
    
    # === Phase 1 新增字段 ===
    resonance_count: int = 1            # 有多少个独立源在报这件事
    co_sources: list[str] = field(default_factory=list)  # 共振的其他源名列表
    
    # === Phase 1 新增：预计算的基础分数（非AI） ===
    raw_timeliness: float = 0.0         # 时效性（基于时间衰减公式计算）
    raw_prominence: float = 0.0         # 知名度（基于源优先级 + 共振计数）
```

### 3.2 IntelligencePack（情报包）— Oracle 输出的核心结构

```python
@dataclass
class IntelligencePack:
    """一条经过 AI 分析后的完整情报"""
    
    # --- 5W1H ---
    who: str = ""        # 主体：谁发起的？（如 "美联储 / SEC / Elon Musk / 以色列国防军"）
    what: str = ""       # 事件：发生了什么？
    where: str = ""      # 地点：物理位置或数字领地（如 "华盛顿 / Solana链上 / 中东地区"）
    when: str = ""       # 时间：发生时间及持续时间
    why: str = ""        # 原因：触发背后的逻辑
    how: str = ""        # 过程：如何演变的
    implication: str = "" # 预示：最值钱的部分 — 对市场/政治/领域的影响预测
    
    # --- 元数据 ---
    original_title: str = ""
    original_sources: list[str] = field(default_factory=list)  # 原始来源列表
    event_id: str = ""   # 事件唯一标识（用于去重和追踪）
    
    # --- 五维评分 (0-10) ---
    scores: dict = field(default_factory=lambda: {
        "timeliness": 0,    # 时效性：新鲜度衰减
        "importance": 0,    # 重要性：影响范围与深度
        "proximity": 0,     # 接近性：与用户关注领域的相关性
        "prominence": 0,    # 知名度：跨源共振 + 社交热度
        "anomaly": 0,       # 异常性：打破常规的程度
    })
    
    # --- 综合标签 ---
    tag: str = "NOISE"      # CRITICAL / HIGH / TRENDING / NOISE
    composite_score: float = 0.0  # 加权综合分（用于全局排序）
    
    # --- 特殊标记 ---
    is_resonance_alert: bool = False  # 是否触发共振报警
    chain_signal: str = ""            # 链上信号（如有）：BULLISH / BEARISH / NEUTRAL
    macro_trigger: bool = False       # 是否为宏观日历事件（CPI/非农等）
```

### 3.3 OracleReport（Oracle 最终报告）

```python
@dataclass
class OracleReport:
    """一次 Oracle 运行的完整输出"""
    run_time: datetime
    total_items_analyzed: int
    packs: list[IntelligencePack]
    summary_text: str = ""            # AI 生成的总体摘要
    market_outlook: str = ""          # AI 给出的市场展望
    telegram_messages: list[str] = field(default_factory=list)  # 待推送的消息列表
```

---

## 4. 核心模块设计

### 4.1 Module A: ResonanceDetector（跨源共振检测）

**文件位置**: `aggregator_rss.py` 中新增函数（或新建 `resonance.py`）

**输入**: `list[RawNewsItem]` （去重后的全部新闻）
**输出**: 每条 item 的 `resonance_count` 和 `co_sources` 被填充

**算法（v2.1 修订：双轨制 — 实体匹配 + Jaccard 兜底）**：

```
核心洞察：新闻标题是短文本，不同源对同一事件的措辞差异极大。
例如 "SEC approves Ethereum ETF" vs "ETH ETF greenlit by regulators"，
纯 Jaccard 可能只有 0.2，但它们明显是同一件事。

解决方案：采用「实体优先 + 相似度兜底」的双轨策略。
```

**轨道 A：实体共振检测（主路径，高精度）**

```python
# 高权重实体词表（可扩展）
HIGH_WEIGHT_ENTITIES = {
    # 加密货币
    "BTC", "BITCOIN", "ETH", "ETHEREUM", "SOL", "SOLANA",
    "BNB", "BINANCE", "COINBASE", "USDT", "USDC", "TETHER",
    # 监管机构
    "SEC", "CFTC", "FED", "FEDERAL RESERVE", "ECB", "BOJ", "PBOC",
    # 宏观指标
    "CPI", "NFP", "NONFARM", "GDP", "INFLATION", "INTEREST RATE",
    "FOMC", "RATE HIKE", "RATE CUT", "QT", "QE",
    # 地缘/政治
    "UKRAINE", "RUSSIA", "IRAN", "ISRAEL", "GAZA", "CHINA", "TAIWAN",
    "TRUMP", "BIDEN", "PUTIN", "XI", "NETANYAHU",
    # 科技/AI
    "OPENAI", "GOOGLE", "META", "APPLE", "MICROSOFT", "NVIDIA",
    "MCP", "LLM", "GPT", "GEMINI", "CLAUDE", "ANTHROPIC",
    # 金融事件
    "ETF", "IPO", "MERGER", "ACQUISITION", "BANKRUPTCY", "LIQUIDATION",
}

def _extract_entities(title: str) -> set[str]:
    """从标题中提取大写实体词"""
    import re
    found = set()
    for entity in HIGH_WEIGHT_ENTITIES:
        if entity in title.upper():
            found.add(entity)
    return found

def _entity_resonance(items: list[dict], time_window_minutes: int = 5) -> list[dict]:
    """
    轨道A：基于实体的共振检测
    规则：两个标题在 time_window 分钟内共享 >= 2 个高权重实体 → 判定为共振
    """
    n = len(items)
    for i in range(n):
        items[i]["resonance_count"] = 1
        items[i]["co_sources"] = []
        entities_i = _extract_entities(items[i].get("title", ""))
        time_i = items[i].get("time")
        
        for j in range(i + 1, n):
            entities_j = _extract_entities(items[j].get("title", ""))
            time_j = items[j].get("time")
            
            # 条件1：共享 >= 2 个高权重实体
            shared = entities_i & entities_j
            if len(shared) >= 2:
                # 条件2：时间窗口内（默认5分钟，宽松模式可放宽到30分钟）
                if time_i and time_j:
                    delta = abs((time_i - time_j).total_seconds()) / 60
                    if delta <= time_window_minutes:
                        _mark_resonant(items[i], items[j])
                else:
                    # 无时间信息时，仅凭实体匹配也判定为共振
                    _mark_resonant(items[i], items[j])
    
    return items
```

**轨道 B：Jaccard 相似度（兜底路径）**

```python
def detect_resonance(items: list[dict],
                     threshold: float = 0.4,       # v2.1: 从 0.6 降低到 0.4
                     use_entity_first: bool = True) -> list[dict]:
    """跨源共振检测 — 双轨制入口"""
    
    # 轨道 A：实体匹配（优先）
    if use_entity_first:
        items = _entity_resonance(items)
    
    # 轨道 B：Jaccard 兜底（捕获实体匹配遗漏的语义相似项）
    n = len(items)
    for i in range(n):
        title_a = _tokenize(items[i]["title"])
        
        for j in range(i + 1, n):
            # 跳过已经被实体匹配标记过的对（避免重复计数）
            source_b = items[j].get("source", "")
            if source_b in items[i].get("co_sources", []):
                continue
            
            # URL 快速路径
            if (items[i].get("link") and items[i]["link"] == items[j].get("link")):
                _mark_resonant(items[i], items[j])
                continue
            
            # Jaccard 兜底
            title_b = _tokenize(items[j]["title"])
            sim = _jaccard(title_a, title_b)
            if sim >= threshold:
                _mark_resonant(items[i], items[j])
    
    return items


def _tokenize(text: str) -> set[str]:
    """简单分词（英文按空格+小写，中文按字符级ngram）"""
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
```

### 4.2 Module B: PreScorer（预评分引擎 — 非AI层）

**目的**: 在送入 Gemini 前，先计算出可以纯数学推导的两个维度分数，节省 AI token 并提供 fallback。

**时效性 (Timeliness)** — 纯时间衰减函数：

```python
def calc_timeliness(pub_time: datetime, now: datetime = None) -> float:
    """
    时效性评分 (0-10)
    - 0-30分钟内: 10分 (极速)
    - 30分钟-2小时: 9分 (快讯)
    - 2-6小时: 7分 (热点)
    - 6-12小时: 5分 (一般)
    - 12-24小时: 3分 (旧闻)
    - >24小时: 0分 (丢弃，由 _filter 处理)
    """
    if now is None:
        now = datetime.now(timezone.utc)
    delta_minutes = (now - pub_time).total_seconds() / 60
    
    if delta_minutes <= 30:   return 10.0
    elif delta_minutes <= 120: return 9.0
    elif delta_minutes <= 360: return 7.0
    elif delta_minutes <= 720: return 5.0
    elif delta_minutes <= 1440: return 3.0
    else: return 0.0
```

**知名度 (Prominence)** — 源权威度 + 共振计数：

```python
def calc_prominence(source: str, resonance_count: int) -> float:
    """
    知名度评分 (0-10)
    基础分来自 PRIORITY 字典（反转：priority=1 是最高权威）
    共振加成：每多一个源报同一件事 +1.5 分（上限 10）
    """
    base_score = {1: 8.0, 2: 5.0, 3: 3.0}.get(_rank(source), 2.0)
    resonance_bonus = min((resonance_count - 1) * 1.5, 2.0)  # 最多 +2
    return min(base_score + resonance_bonus, 10.0)
```

### 4.3 Module C: OracleAnalyzer（AI 分析引擎）

**这是升级的核心**。将当前的自由文本 Prompt 替换为结构化 JSON Prompt。

#### 4.3.1 System Prompt 设计

```python
ORACLE_SYSTEM_PROMPT = """你是 Wisteria Intelligence 的首席情报官（Oracle）。
你的任务是将原始新闻流转化为高度结构化的【情报包】。

## 输出要求
你必须且只能返回一个合法的 JSON 数组，每个元素代表一条核心事件的情报包。
不要包含任何 JSON 之外的文字、markdown 代码块标记或解释。

## 情报包结构
对每条新闻，输出以下 JSON 对象：
{
  "who": "主体（谁发起的？组织/人物/机构）",
  "what": "事件描述（发生了什么？一句话概括核心事实）",
  "where": "地点（物理位置或数字领域，如：华盛顿DC / Solana链上 / 东地中海）",
  "when": "时间（事件发生时间点及持续性描述）",
  "why": "原因（触发的深层逻辑或直接导火索）",
  "how": "过程（事态如何演变/发展脉络）",
  "implication": "预示（对市场/政治/特定领域的短期影响预测，这是最有价值的部分）",
  "original_title": "原标题",
  "original_sources": ["来源1", "来源2"],
  "scores": {
    "timeliness": 0-10,
    "importance": 0-10,
    "proximity": 0-10,
    "prominence": 0-10,
    "anomaly": 0-10
  },
  "tag": "CRITICAL 或 HIGH 或 TRENDING 或 NOISE",
  "chain_signal": "BULLISH 或 BEARISH 或 NEUTRAL 或 N/A",
  "macro_trigger": true/false
}

## 五维评分标准

### timeliness (时效性)
- 10: 30分钟内的突发（刚刚发生）
- 8-9: 1-2小时内的重要快讯
- 6-7: 当天上午发布的新闻
- 4-5: 超过6小时的旧闻
- 0-3: 超过12小时的信息

### importance (重要性)
- 9-10: 全球级震荡（战争爆发/重大监管政策/GDP级经济数据）
- 7-8: 行业级变动（巨头并购/主要央行决议/重大安全事件）
- 5-6: 公司/项目级动态（财报/产品发布/人事变动）
- 3-4: 常规更新（日常运营/例行公告）
- 0-2: 无关紧要

### proximity (接近性) — v2.1 修订：三维度加权模型

**用户画像核心**: 量化交易者（币安资金费率套利） + AI开发者（OpenClaw/MCP生态） + 关注中国/北京科技圈 + Crypto投资者

Proximity 不再是单一分数，而是由三个子维度加权合成：

```
proximity = max(trading_score, geographic_score, tech_score)
即：取三个子维度中的最高分作为最终 proximity 值
（因为任一维度的强关联都意味着"与我高度相关"）
```

#### 子维度 A: 交易关联 (Trading Relevance) — 权重最高，满分 10

| 触发条件 | 分数 | 示例 |
|---------|------|------|
| 直接影响币安资金费率套利的异动 | **10** | 小市值币种解锁 / OI暴增 / 币安上币下架公告 |
| BTC/ETH 价格剧烈波动 (>5%) | **9-10** | 暴涨暴跌 / 大额清算 |
| 链上大额转账 (Whale Alert >$10M) | **9** | 砸盘/拉盘前兆信号 |
| 交易所相关重大事件 | **8-9** | Coinbase/Binance 监管诉讼 / 安全事件 |
| 宏观经济数据发布 (CPI/NFP/Fed Rate) | **8** | 直接影响全市场波动率 |
| 一般加密行业新闻 | **6-7** | 项目更新 / 合作公告 |

#### 子维度 B: 地域关联 (Geographic Relevance) — 中等权重，满分 8~9

| 触发条件 | 分数 | 示例 |
|---------|------|------|
| 北京本地重大突发 | **9** | 本地安全事件 / 政策发布会现场 |
| 中国国内宏观政策/监管文件 | **8-9** | 央行政策 / 网信办新规 / 数据安全法 |
| 中美关系/贸易摩擦 | **7-8** | 关税 / 制裁 / 科技封锁 |
| 亚太地区重要动态 | **6-7** | 日韩/东南亚金融政策 |

#### 子维度 C: 技术关联 (Tech Relevance) — 中等权重，满分 8~9

| 触发条件 | 分数 | 示例 |
|---------|------|------|
| AI Agent 框架 / MCP 协议更新 | **9** | OpenClaw 生态直接影响 |
| LLM API 降价或新版本发布 | **8-9** | GPT/Claude/Gemini 新版 → 影响技术栈选型 |
| 开源 AI 工具链重大变更 | **7-8** | LangChain / CrewAI / AutoGen 更新 |
| 云服务/算力基础设施变化 | **6-7** | GPU 租赁价格 / 推理成本变动 |

### prominence (知名度/话题度)
参考输入中提供的 resonance_count（跨源共振数）和 source_authority（源权威度）
- 9-10: 5+个独立源同时报道 + 权威媒体（Reuters/AP/Bloomberg级别）
- 7-8: 3-4个源共振 或 单一顶级源独家重磅
- 5-6: 2个源共振 或 行业知名媒体报道
- 3-4: 单一普通源报道
- 0-2: 几乎无人关注的边缘信息

### anomaly (异常性)
- 9-10: 黑天鹅事件（完全出乎意料、打破常规范式的事件）
- 7-8: 显著异常（非常规但有一定前兆的事件）
- 5-6: 轻微异常（比预期更极端的结果）
- 3-4: 符合预期的常规事件
- 0-2: 完全可预测的例行事项

## 标签判定标准
- CRITICAL: importance >= 8 且 (anomaly >= 7 或 timeliness >= 9)
- HIGH: importance >= 6 且 timeliness >= 7
- TRENDING: prominence >= 7 或 resonance_count >= 3
- NOISE: 其他所有

## 去重与合并原则
如果多条新闻是同一事件的不同角度报道，合并为一条情报包，
在 original_sources 中列出所有来源，implication 综合各源观点。

## 特殊处理
- Whale Alert 大额转账: 分析是否为砸盘/拉盘信号 → chain_signal
- Economic Calendar (CPI/NFP/Rate): 标记 macro_trigger=true，提示具体发布时间
- Elon Musk/Twitter: 如果内容涉及币圈，标注潜在的市场影响
"""
```

#### 4.3.2 User Prompt 构建

```python
def build_oracle_prompt(items: list[dict]) -> str:
    """
    构建发送给 Gemini 的 User Prompt
    将预处理过的新闻列表（含共振数据和预评分）格式化为结构化输入
    """
    news_blocks = []
    for idx, item in enumerate(items[:15], 1):  # 最多 15 条，控制 token
        block = f"""---
[{idx}] 标题: {item['title']}
来源: {item['source']}
时间: {item['time'].strftime('%Y-%m-%d %H:%M UTC')}
共振数: {item.get('resonance_count', 1)} 个源共同报道
共振源: {', '.join(item.get('co_sources', ['仅此一家']))}
预评时效: {item.get('raw_timeliness', 'N/A')}/10
预评知名: {item.get('raw_prominence', 'N/A')}/10
---"""
        news_blocks.append(block)
    
    current_time = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M 北京时间')
    
    return f"""以下是当前 ({current_time}) 从 36 个全球情报源捕获的高价值信号。
请按照 System Prompt 要求的结构化格式返回分析结果。

{chr(10).join(news_blocks)}"""
```

#### 4.3.3 结构化输出解析

```python
def parse_gemini_response(raw_text: str) -> list[dict]:
    """
    解析 Gemini 返回的结构化 JSON
    包含多层容错机制
    """
    import json
    import re
    
    text = raw_text.strip()
    
    # 尝试 1: 直接解析
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "packs" in data:
            return data["packs"]
    except json.JSONDecodeError:
        pass
    
    # 尝试 2: 提取 ```json ... ``` 代码块
    code_block_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', text, re.DOTALL)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # 尝试 3: 找第一个 [ 到最后一个 ]
    array_match = re.search(r'\[.*\]', text, re.DOTALL)
    if array_match:
        try:
            return json.loads(array_match.group(0))
        except json.JSONDecodeError:
            pass
    
    # 全部失败 → 返回空列表，走 fallback
    return []
```

### 4.4 Module D: TelegramFormatter（分级推送格式化器）

**v2.1 修订：采用「快慢结合」策略，避免 Telegram 变成垃圾桶**

#### 推送分级规则

| 级别 | 触发条件 | 推送方式 | 标签 |
|------|---------|---------|------|
| 🔴 **CRITICAL 紧急刺透** | `timeliness >= 9` 且 `proximity >= 8`（交易强相关） | **无视时间窗口，单条立刻推送** | `🔥 紧急` |
| 🟡 **HIGH 高热共振** | `importance >= 6` 且 (`resonance >= 3` 或 `anomaly >= 7`) | 合并为结构化卡片，周期结束时统一推 | — |
| 🟠 **TRENDING 趋势热点** | `prominence >= 7` 或 `resonance >= 3` | 合并摘要推送 | — |
| ⚪ **NOISE 信息噪音** | `composite_score < 5` 或 tag=NOISE | **静默不推送**，写入本地日志备查 | — |

```python
def format_telegram_report(report: OracleReport) -> list[str]:
    """
    v2.1: 快慢结合策略
    - CRITICAL: 立即逐条推送（最多3条）
    - HIGH + TRENDING: 合并为一组结构化卡片
    - NOISE: 完全静默（仅日志记录）
    - 总消息数 <= 4 条
    """
    messages = []
    
    critical_packs = [p for p in report.packs if p.tag == "CRITICAL"]
    high_packs = [p for p in report.packs if p.tag in ("HIGH", "TRENDING")]
    # NOISE 级别不进入消息列表
    
    # === 如果没有任何可推送的内容 → 发送"空报告"提示 ===
    if not critical_packs and not high_packs:
        return [_format_empty_report(report)]
    
    # === Header 消息 ===
    header = f"""🔮 **Wisteria Oracle | 情报简报**
⏰ `{report.run_time.strftime('%H:%M')} Beijing`
📊 {report.total_items_analyzed} 条原始信号 → 提炼 {len(report.packs)} 条核心情报
🔴{len(critical_packs)} 紧急 | 🟡{len([p for p in high_packs if p.tag=='HIGH'])} 高热 | 🟠{len([p for p in high_packs if p.tag=='TRENDING'])} 趋势 | ⚪静默{len([p for p in report.packs if p.tag=='NOISE'])}条
━━━━━━━━━━━━━━━━━━"""
    messages.append(header)
    
    # === 🔴 CRITICAL: 逐条立即推送（带🔥紧急标签）===
    for pack in critical_packs[:3]:
        msg = _format_critical_pack(pack, urgent=True)
        messages.append(msg)
    
    # === 🟡+🟠 HIGH/TRENDING: 合并推送 ===
    if high_packs:
        msg = ""
        high_only = [p for p in high_packs if p.tag == "HIGH"]
        trend_only = [p for p in high_packs if p.tag == "TRENDING"]
        
        if high_only:
            msg += "🟡 **HIGH PRIORITY**\n"
            for pack in high_only[:5]:
                msg += _format_compact_pack(pack) + "\n"
        
        if trend_only:
            msg += "\n� **TRENDING**\n"
            for pack in trend_only[:6]:
                msg += f"• [{pack.tag}] {pack.what[:70]} ({', '.join(pack.original_sources[:2])})\n"
        
        messages.append(msg)
    
    # === Footer（市场展望）===
    if report.market_outlook:
        messages.append(f"\n🧭 **Market Outlook**: {report.market_outlook}\n_Powered by Wisteria_")
    
    return messages


def _format_empty_report(report: OracleReport) -> str:
    """
    v2.1 新增：空新闻时的友好提示
    即使没有高价值情报，也给用户一个「系统正常」的信号
    """
    return f"""🔮 **Wisteria Oracle | 巡逻报告**
⏰ `{report.run_time.strftime('%H:%M')} Beijing`

✅ **系统运行正常，本轮未发现高价值情报信号。**

扫描了 {report.total_items_analyzed} 条原始信息源，
所有条目均被判定为常规/低优先级动态（NOISE）。

> 💤 全球平静时刻。适合喝杯咖啡 ☕

━━━━━━━━━━━━━━━━━━
_Powered by Wisteria_"""


def _format_critical_pack(pack: IntelligencePack, urgent: bool = False) -> str:
    """格式化单条 CRITICAL 情报（v2.1: 支持🔥紧急标签）"""
    s = pack.scores
    emoji_map = {"CRITICAL": "🔴", "HIGH": "🟡", "TRENDING": "🟠", "NOISE": "⚪"}
    urgency_tag = "\n🔥 **⚡ URGENT ⚡**\n" if urgent else ""
    
    return f"""{emoji_map.get(pack.tag, '📰')} **[{pack.tag}]** {pack.what}
{urgency_tag}━━━━━━━━━━━━━━━━━━
👤 **Who**: {pack.who}
📍 **Where**: {pack.where}
⏰ **When**: {pack.when}
❓ **Why**: {pack.why}
🔄 **How**: {pack.how}
💡 **Implication**: {pack.implication}

📊 **Scores**: ⏱{s['timeliness']} | 🎯{s['importance']} | 🏠{s['proximity']} | 📢{s['prominence']} | ⚡{s['anomaly']}
📡 **Sources**: {', '.join(pack.original_sources)}
{'🐳 ' + pack.chain_signal if pack.chain_signal != 'N/A' else ''}
{'📅 MACRO TRIGGER' if pack.macro_trigger else ''}
{'🔥 RESONANCE ALERT (' + str(len(pack.original_sources)) + ' sources)' if len(pack.original_sources) >= 3 else ''}
━━━━━━━━━━━━━━━━━━"""


def _format_compact_pack(pack: IntelligencePack) -> str:
    """紧凑格式（用于 HIGH/TRENDING 级别）"""
    s = pack.scores
    return f"""• **{pack.what[:80]}**
  👤{pack.who} | 📍{pack.where} | 💡{pack.implication[:100]}
  Scores: ⏱{s['timeliness']} 🎯{s['importance']} 🏠{s['proximity']} 📢{s['prominence']} ⚡{s['anomaly']}
  Sources: {', '.join(pack.original_sources)}"""
```

---

## 5. 改动清单（File-by-File）

### 5.1 `src/opennews_mcp/tools/aggregator_rss.py`

| 改动项 | 类型 | 说明 |
|--------|------|------|
| 新增 `_detect_resonance()` | 函数 | 跨源共振检测算法 |
| 新增 `calc_timeliness()` | 函数 | 时效性预评分 |
| 新增 `calc_prominence()` | 函数 | 知名度预评分 |
| 修改 `_filter()` | 函数 | 在返回前注入共振检测和预评分 |
| 修改 `RawNewsItem` 返回结构 | 数据 | 增加 `resonance_count`, `co_sources`, `raw_timeliness`, `raw_prominence` 字段 |

### 5.2 `src/bot_f_oracle.py`

| 改动项 | 类型 | 说明 |
|--------|------|------|
| 重写 `ORACLE_SYSTEM_PROMPT` | 常量 | 从自由文本改为结构化 JSON Prompt |
| 新增 `build_oracle_prompt()` | 函数 | 构建含元数据的 User Prompt |
| 新增 `parse_gemini_response()` | 函数 | 多层容错的 JSON 解析器 |
| 新增 `IntelligencePack` dataclass | 数据类 | 情报包数据结构 |
| 新增 `OracleReport` dataclass | 数据类 | Oracle 报告数据结构 |
| 重写 `run_oracle()` | 函数 | 主流程重构 |
| 新增 `format_telegram_report()` | 函数 | 分级格式化推送 |
| 删除旧的 fallback 逻辑 | 清理 | 用新的结构化 fallback 替代 |

### 5.3 `src/run_multibot_matrix.py`

| 改动项 | 类型 | 说明 |
|--------|------|------|
| 可选优化：增加共享缓存 | 功能 | 让 Oracle 复用 Matrix 已抓取的数据，避免重复请求 |

### 5.4 `.github/workflows/schedule_matrix.yml`

| 改动项 | 类型 | 说明 |
|--------|------|------|
| 无需改动 | - | 当前调度频率已满足需求 |

---

## 6. 容错与降级策略（v2.1 增强）

### 6.1 Gemini JSON 解析失败处理 — 核心决策：**绝不丢弃，正则兜底**

这是 Phase 1 最容易翻车的点。Gemini Free Tier 偶尔会在 JSON 中混入 markdown 格式、
注释文字、或截断输出。我们的策略是 **4 层渐进式容错 + 正则兜底**：

```
解析优先级链:
  Layer 1: json.loads() 直接解析 → 成功？→ 返回结构化列表 ✅
    ↓ 失败
  Layer 2: 提取 ```json ... ``` 代码块 → 解析 → 成功？✅
    ↓ 失败
  Layer 3: 正则提取 [ ... ] 数组 → 尝试修复常见问题后解析 → 成功？✅
    ↓ 失败
  Layer 4 (v2.1 新增): 正则字段提取兜底 → 从自由文本中暴力提取关键信息 ⭐
    ↓ 全部失败
  返回空列表 → 走 Level 1 关键词 Fallback（见 6.2）
```

#### Layer 4 详细设计：正则字段提取器

```python
import re
import json

def _regex_fallback_extract(raw_text: str) -> list[dict]:
    """
    v2.1 新增：当所有 JSON 解析路径都失败时，
    用正则从自由文本中"暴力"提取结构化字段。
    
    这保证了即使 Gemini 输出格式完全跑偏，
    我们仍然能拿到 who/what/implication 等核心信息，
    而不是直接丢弃整条分析结果。
    """
    packs = []
    
    # 按段落或编号分割文本（Gemini 通常按条目分段输出）
    segments = re.split(r'\n(?=\d+\.|\n*[-*•]|\n*##|\n*\d+\))', raw_text)
    
    for seg in segments:
        if len(seg.strip()) < 20:
            continue
        
        pack = {
            "who": _extract_field(seg, r'(?:who|主体|谁)[:：]\s*(.+?)(?:\n|$)'),
            "what": _extract_field(seg, r'(?:what|事件|发生了什么|描述)[:：]\s*(.+?)(?:\n|$)'),
            "where": _extract_field(seg, r'(?:where|地点|位置)[:：]\s*(.+?)(?:\n|$)'),
            "when": _extract_field(seg, r'(?:when|时间)[:：]\s*(.+?)(?:\n|$)'),
            "why": _extract_field(seg, r'(?:why|原因|导火索)[:：]\s*(.+?)(?:\n|$)'),
            "how": _extract_field(seg, r'(?:how|过程|演变)[:：]\s*(.+?)(?:\n|$)'),
            "implication": _extract_field(seg, 
                r'(?:implication|预示|影响|预测|market\s*impact)[:：]\s*(.+?)(?:\n|$)'),
            # 分数提取
            "scores": {
                "timeliness": _extract_score(seg, r'timeliness|时效'),
                "importance": _extract_score(seg, r'importance|重要'),
                "proximity": _extract_score(seg, r'proximity|接近|相关'),
                "prominence": _extract_score(seg, r'prominence|知名|热度'),
                "anomaly": _extract_score(seg, r'anomaly|异常'),
            },
            "tag": "TRENDING",  # 兜底默认标签
            "original_title": seg.split('\n')[0][:100] if seg else "",
            "original_sources": ["Oracle-Fallback"],
        }
        
        # 只有 what 或 implication 有值时才保留
        if pack["what"] or pack["implication"]:
            packs.append(pack)
    
    return packs


def _extract_field(text: str, pattern: str) -> str:
    """从文本中用正则提取单个字段的值"""
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip()[:200] if match else ""


def _extract_score(text: str, pattern: str) -> int:
    """从文本中提取 0-10 的分数"""
    match = re.search(rf'{pattern}[^0-9]*(\d+)', text, re.IGNORECASE)
    if match:
        val = int(match.group(1))
        return max(0, min(10, val))
    return 5  # 默认中间值，表示"不确定"
```

#### 完整的 parse_gemini_response（整合 4 层）

```python
def parse_gemini_response(raw_text: str) -> tuple[list[dict], str]:
    """
    v2.1 完整版：4 层容错解析
    
    Returns:
        (packs_list, parse_method) — 返回解析出的情报包列表和使用的解析方法
        parse_method 用于日志记录，方便后续统计各层命中率
    """
    import json, re
    text = raw_text.strip()
    
    # Layer 1: 直接 JSON 解析
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data, "layer1_direct"
        if isinstance(data, dict) and "packs" in data:
            return data["packs"], "layer1_dict"
    except json.JSONDecodeError:
        pass
    
    # Layer 2: 提取代码块
    code_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', text, re.DOTALL)
    if code_match:
        try:
            return json.loads(code_match.group(1)), "layer2_codeblock"
        except json.JSONDecodeError:
            pass
    
    # Layer 3: 提取数组 + 常见问题修复
    array_match = re.search(r'\[.*\]', text, re.DOTALL)
    if array_match:
        raw_json = array_match.group(0)
        # 常见修复：去掉尾部逗号、去掉注释等
        raw_json = re.sub(r',\s*([}\]])', r'\1', raw_json)       # trailing comma
        raw_json = re.sub(r'//.*$', '', raw_json, flags=re.MULTILINE)  # comments
        try:
            return json.loads(raw_json), "layer3_array_repair"
        except json.JSONDecodeError:
            pass
    
    # Layer 4: 正则暴力提取（v2.1 新增 — 绝不丢弃！）
    fallback_packs = _regex_fallback_extract(text)
    if fallback_packs:
        return fallback_packs, "layer4_regex_fallback"
    
    # 全部失败
    return [], "all_layers_failed"
```

### 6.2 AI 服务不可用时的降级方案

当 Gemini 完全不可用时（网络断/额度耗尽/429 限流），系统走关键词规则引擎：

```
Level 0: Gemini 正常 → 完整 5W1H + AI 五维评分
Level 1: Gemini JSON 解析失败 → Layer 4 正则兜底提取核心字段（见 6.1）
Level 2: Gemini API 不可用 → 使用预评分（timeliness/prominence 已有）+ 
                              关键词规则推断 importance/proximity/anomaly
Level 3: Ollama 可用 → 用本地模型替代 Gemini（prompt 相同，质量略低）
Level 4: 全部 AI 不可用 → 纯关键词匹配 + 共振计数，只推送 resonance >= 2 的条目
```

**Level 2 关键词规则示例**:

```python
FALLBACK_RULES = {
    "importance": [
        (r"(war|attack|nuclear|missile)", 9),
        (r"(fed|cpi|nfp|rate decision|interest rate)", 8),
        (r"(sec|etf|approval|regulation)", 7),
        (r"(merger|acquisition|ipo)", 6),
        (r"(earnings|revenue|profit)", 4),
    ],
    "anomaly": [
        (r"(unprecedented|first.time|never|record)", 9),
        (r"(unexpected|surprise|beat|miss)", 7),
        (r"(hack|breach|exploit)", 8),
    ],
    "proximity": {  # v2.1: 三维度分别匹配
        "trading": [
            (r"(binance|funding rate|oi|open interest|delisting|listing)", 10),
            (r"(btc|eth|whale|liquidation)", 9),
            (r"(coinbase|kraken|exchange)", 8),
        ],
        "geographic": [
            (r"(beijing|北京|china|中国|央行|pboc)", 9),
            (r"(us-china|中美|tariff|制裁)", 8),
        ],
        "tech": [
            (r"(mcp|openclaw|agent|llm|api.*price|降价)", 9),
            (r"(openai|anthropic|gemini|gpt|claude)", 8),
        ],
    },
}
```

### 6.3 空新闻 / 零信号场景处理

**决策：始终给用户一句话。**

即使在以下极端情况下，Oracle 也应推送一条消息：
- 所有 RSS 源返回空结果（源站宕机/被封）
- 过滤后零条高价值新闻
- AI 分析全部判定为 NOISE

```python
def handle_empty_oracle(run_time: datetime, total_scanned: int = 0,
                        error_msg: str = None) -> OracleReport:
    """
    v2.1 新增：空新闻 / 异常情况的统一处理
    保证用户每次都能收到一条消息，而不是沉默。
    """
    if error_msg:
        status_text = f"""⚠️ **Wisteria Oracle | 异常报告**
⏰ `{run_time.strftime('%H:%M')} Beijing`

❌ 系统运行异常：`{error_msg}`

可能原因：
• RSS 源站暂时不可达（部分源可能被 GFW 或 CDN 拦截）
• Gemini API 额度耗尽或限流（Free Tier 限制）
• GitHub Actions 运行时超时

> 🔧 下次调度将自动重试。如持续出现请联系管理员。

━━━━━━━━━━━━━━━━━━
_Powered by Wisteria_"""
    else:
        status_text = f"""🔮 **Wisteria Oracle | 巡逻报告**
⏰ `{run_time.strftime('%H:%M')} Beijing`

✅ **系统运行正常，本轮未发现高价值情报信号。**

扫描了 {total_scanned} 条原始信息源，
所有条目均被判定为常规/低优先级动态（NOISE）。

> 💤 全球平静时刻。适合喝杯咖啡 ☕

━━━━━━━━━━━━━━━━━━
_Powered by Wisteria_"""
    
    return OracleReport(
        run_time=run_time,
        total_items_analyzed=total_scanned,
        packs=[],
        summary_text="NO_SIGNAL",
        market_outlook="",
        telegram_messages=[status_text]
    )
```

---

## 7. Token 与成本估算

### 7.1 Gemini 调用估算

| 参数 | 值 |
|------|-----|
| 模型 | gemini-2.0-flash-lite（免费额度最高） |
| Input | System Prompt (~2500 tokens) + 15条新闻 x ~150 tokens ≈ **4750 tokens** |
| Output | 10条情报包 x ~300 tokens ≈ **3000 tokens** |
| 单次调用总计 | ~7750 tokens |
| Free Tier 限额 | 150万 tokens/分钟（几乎无限） |
| **结论** | **完全在免费额度内，无需担心成本** |

### 7.2 GitHub Actions 运行时影响

| 指标 | 当前 | 升级后 | 变化 |
|------|------|--------|------|
| 单次运行时长 | ~40-50 秒 | ~50-70 秒 | +10-20秒（Gemini 调用 + 解析） |
| 内存占用 | 低 | 低 | 无变化 |
| 新增依赖 | 无 | 无 | 仅使用标准库 + httpx（已有） |

---

## 8. 实施步骤（推荐顺序）

```
Step 1: aggregator_rss.py
  ├── 新增 _detect_resonance() 函数
  ├── 新增 calc_timeliness() / calc_prominence() 函数
  └── 修改 _filter() 注入新字段
        ↓
Step 2: bot_f_oracle.py
  ├── 定义 IntelligencePack / OracleReport dataclass
  ├── 编写 ORACLE_SYSTEM_PROMPT（结构化 JSON 版）
  ├── 实现 build_oracle_prompt()
  ├── 实现 parse_gemini_response()（含多层容错）
  ├── 实现 fallback 评分逻辑
  ├── 实现 format_telegram_report()（分级推送）
  └── 重写 run_oracle() 主流程
        ↓
Step 3: 测试验证
  ├── 手动运行一次完整流程
  ├── 验证 JSON 解析成功率
  ├── 验证 Telegram 消息格式
  └── 验证 fallback 降级路径
        ↓
Step 4 (可选): 动态滤镜
  ├── Telegram inline keyboard 支持
  └── /filter 命令实现
```

---

## 9. 未来扩展预留接口

本设计为以下功能预留了扩展空间：

1. **历史回溯**: `event_id` 可用作数据库主键，未来接入向量库（Milvus/FAISS）后可实现"上次类似事件发生时市场怎么走的"
2. **准确率追踪**: `composite_score` vs 实际市场反应的对比，用于迭代优化评分权重
3. **多语言支持**: `implication` 可配置输出语言
4. **自定义用户画像**: `proximity` 的评分权重可通过配置文件调整（如用户更关注欧洲市场则提高 EU 相关权重）
5. **Web Dashboard**: `OracleReport` 序列化后可直接提供给前端渲染

---

*文档版本: v2.1*
*最后更新: 2026-04-07*
*作者: Wisteria Intelligence Team*
*v2.1 变更: Proximity 三维拆分 / 实体共振双轨制 / 快慢推送策略 / JSON 四层容错 / 空新闻处理*
