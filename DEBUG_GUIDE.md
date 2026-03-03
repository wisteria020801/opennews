# 🚨 Telegram 机器人“哑巴”故障排查指南 (DEBUG_GUIDE)

> **核心逻辑**：如果 GitHub Actions 显示 "Success" (绿色勾) 但群里没消息，说明**代码跑通了，但 Telegram 拒绝了发送请求**。

以下是按照**可能性从高到低**排列的 5 个致命坑点：

---

## 🛑 1. 变量名不匹配 (The Variable Mismatch) —— **可能性 90%**
这是最容易犯的错。你在 GitHub Secrets 里填的名字，和代码里想要的名字**必须一字不差**。

*   **GitHub Secrets 里填的是**: `FINANCEBOTTOKEN` (全大写，无下划线)
*   **代码里要的是**: `BOT_TOKEN_B` (有下划线)
*   **Action 配置文件必须这样连**:
    ```yaml
    env:
      BOT_TOKEN_B: ${{ secrets.FINANCEBOTTOKEN }}
    ```
    *(如果你漏了这行映射，代码拿到的 Token 就是空的，发不出消息)*

---

## 🛑 2. Chat ID 错误或丢失 (The Lost Chat ID) —— **可能性 80%**
Chat ID 必须是**负数** (如 `-100xxxx`)。

*   **坑点 A**: 你填成了正数 (个人 ID)。Telegram 会报错 400。
*   **坑点 B**: 你的群升级了 (变成了 Supergroup)，ID 变了，你还在用旧 ID。
*   **坑点 C**: 环境变量没传进去，代码拿到了 `None`，报错。

---

## 🛑 3. 机器人不在群里 (The Outsider Bot) —— **可能性 50%**
哪怕 Token 对了，ID 对了，如果机器人没进群，它也没法发消息。

*   **检查**: 点开群成员列表，搜索 `@BetaTrackerBot`。
*   **注意**: 很多群默认禁止普通成员发言。**必须给机器人管理员权限 (Admin)**，否则它会被禁言。

---

## 🛑 4. 拼写错误 (The Typo Trap) —— **可能性 30%**
哪怕少了一个字母，Secrets 也会读取失败。

*   **经典案例**: `MILITARY` (对) vs `MILLITARY` (错，多了一个 L)。
*   **后果**: 如果你 Secrets 建的是错的，代码里用的是对的，那就读不到了。

---

## 🛑 5. 消息格式错误 (The Markdown Crash) —— **可能性 10%**
如果你的新闻标题里包含特殊字符（如 `_`, `*`, `[`），而你开启了 `Markdown` 模式，Telegram 会因为解析失败而拒绝发送整条消息。

*   **表现**: 同样是 400 Bad Request。
*   **修复**: 代码里需要对特殊字符做转义 (Escape)。

---

## ✅ 终极自救流程 (Checklist)

1.  **看 GitHub Secrets**: 确认名字是 `FINANCEBOTTOKEN` 还是 `BOT_TOKEN_B`？
2.  **看 Action YAML**: 确认 `env:` 下面有没有把它们连起来？
3.  **看群成员**: 确认 5 个机器人都在群里，且是 Admin。
4.  **跑本地测试**: 运行 `python debug_matrix.py`。
    *   如果本地能发 -> GitHub 配置问题 (1, 2, 4)。
    *   如果本地发不出 -> 机器人本身问题 (3) 或 Chat ID 错 (2)。
