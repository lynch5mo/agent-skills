---
name: alpha-ficc-hermes-testing
description: "Execute Alpha-FICC Hermes Agent test commands via the local script bridge AND access the Agent terminal chart-context API. Covers chart context reading (GET /api/comparison/current/context), V1 final acceptance, V1.5 render/local relay, V2 research promotion+run, V2.5-V2.7 chart annotations/market validation, V3 rule compilation, V4 observation-revision loop, and V5 Research OS (contract/scheduler/digest/promotion). Security: token is server-side only — never search, read, or ask for it."
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
  category: devops
  triggers:
    - "alpha-ficc"
    - "terminal-v1-final-acceptance"
    - "render-report"
    - "render-terminal-screenshot"
    - "research-v2"
    - "hermes.*alpha.*ficc"
    - "最终验收.*Alpha.*FICC"
    - "V2.*测试"
    - "V2.5.*验收"
    - "V2.6.*验收"
    - "V2.6.3.*验收"
    - "annotation.*验收"
    - "review.*packet"
    - "出图.*标注.*完整"
    - "人民币汇率压力"
    - "v2-full-acceptance"
    - "hermes_v263"
    - "V2.7.*验收"
    - "validation.*run"
    - "market.*validation"
    - "端到端.*验收"
    - "v27"
    - "panelId.*不存在"
    - "INVALID_ANNOTATION_PANEL"
    - "RULE_NOT_STRUCTURED"
    - "annotation.*panel.*matching"
    - "panel.*extract"
    - "V3.*验收"
    - "rule.*compil"
    - "rule.*compiler"
    - "编译.*rule"
    - "规则编译"
    - "accept.*rule"
    - "accepted.*rules.*first"
    - "compileIfMissing"
    - "V4.*验收"
    - "V4.*observation"
    - "V4.*revision"
    - "observation.*revision.*loop"
    - "external.*evidence"
    - "revision.*proposal"
    - "V5.*验收"
    - "V5.*Research.*OS"
    - "research.*os.*scheduler"
    - "research.*os.*digest"
    - "research.*os.*contract"
    - "knowledge.*promotion"
    - "model.*health.*score"
    - "scheduler.*tick"
    - "watch.*policy"
    - "SSH.*banner"
    - "banner.*exchange"
    - "sshd.*卡住"
    - "chart.*context.*读取"
    - "终端.*图表.*内容"
    - "agent.*terminal.*access.*handbook"
    - "alpha-ficc.*接入手册"
    - "分享给 Agent"
    - "comparison.*context"
    - "A股.*分析"
    - "沪深300.*行情"
    - "CSI300"
    - "人民币.*走强"
    - "中美利差"
    - "五阶段"
    - "经常项"
    - "分析.*文章.*观点"
    - "verify.*article"
    - "chart.*data.*verification"
    - "多阶段.*行情"
    - "attribution.*decomposition"
    - "从.*开始算.*行情"
---

# Alpha-FICC Hermes Agent 测试技能

## 触发条件

当用户提到以下关键词时加载此技能：
- Alpha-FICC 测试/验收
- terminal-v1-final-acceptance
- render-report / render-report-local / render-terminal-screenshot-local
- research-v2 / research-v2-validate
- Hermes V1/V1.5/V2/V2.5/V2.6/V2.6.3 最终验收
- annotation store / review packet 验证
- 出图 + 标注 + 验证 完整链路测试

## 与 use-alpha-ficc-terminal 的分工

`use-alpha-ficc-terminal` 是日常终端操作的首选 skill（health check、KB 搜索、图表上下文读取、推送系列、标注、渲染任务）。本 skill 覆盖更深的测试验收协议（V1-V5 全链路验证、annotation store/review packet、market validation run）和故障排查。日常操作优先用 `use-alpha-ficc-terminal`，测试/验收/排查用本 skill。

## 脚本位置

```bash
cd /Users/lynch5mo/Work Documents/alpha-ficc && bash scripts/hermes_alpha_ficc.sh <subcommand> [args]
```

脚本内部使用 `server_ssh` 函数通过 SSH 连接 Alpha-FICC 服务器（`lynch5mo@192.168.10.33`），执行 Docker 操作和 API 调用。

## 硬性安全规则（必须遵守）

1. **绝不输出 Token**：无论从何处读取 token，**绝对不**在回复、日志、脚本输出中暴露 token 内容。
2. **绝不索要 Token**：用户不会通过聊天提供 token。如果两侧都缺失，通知用户 token 未就绪。
3. **绝不访问 `/api/terminal-chart-actions/pending`**：该端点只能由网页端 `/comparison` 自动轮询消费。
4. **只执行用户明确给出的命令**：不要自行扩展、组合或编排命令。
5. **我是 Hermes Agent，不是 Codex**：在 Alpha-FICC 终端语境中，始终以 `hermes` 身份（`X-Alpha-FICC-Agent: hermes`）访问 API。Codex 有独立的 token 和窗口。用户会立即纠正身份混淆。

### Token 读取方式（按优先级）

#### 方式 A：从本地 .env 文件读取（SSH 可用时备用 / SSH 不可用时主用）

本地路径 `/Users/lynch5mo/.hermes/profiles/codex/.env` 包含可用的 `ALPHA_FICC_HERMES_AGENT_TOKEN`（142 字符，含逗号和 `hermes-local-` 前缀）。

**⚠️ 必须用 Python 二进制行解析读取，不得使用 shell grep 或 os.getenv：**

```python
with open("/Users/lynch5mo/.hermes/profiles/codex/.env", "rb") as f:
    for line in f.read().split(b"\n"):
        if line.startswith(b"ALPHA_FICC_HERMES_AGENT_TOKEN="):
            t = line.split(b"=", 1)[1].strip()
            token = t.decode("utf-8", errors="replace")
            if token.startswith('"') and token.endswith('"'): token = token[1:-1]
            break
```

**坑**：`grep ALPHA_FICC_HERMES_AGENT_TOKEN .env` 截断到 13 字符。`os.getenv("ALPHA_FICC_HERMES_AGENT_TOKEN")` 拿到的是空值或被旧进程污染的短值。**必须用 Python 读二进制文件并逐行解析。**

#### 方式 B：SSH 服务器读取（SSH 可用时主用）

```python
token = read_dotenv_key(pathlib.Path(".env"), "ALPHA_FICC_HERMES_AGENT_TOKEN")
```
服务器路径 `/home/lynch5mo/alpha-ficc/.env`。
\n## API 端点选择\n\n### 公网 HTTPS (默认)\n\n```\napi = \"https://alpha-ficc.lynch5mo.xyz/api\"\n```\n\nCloudflare 代理，**可能间歇性 SSL 握手失败**（`SSL: UNEXPECTED_EOF_WHILE_READING`、`Temporary failure in name resolution`）。如果频繁失败，切换到内部 API。\n\n### 内部 HTTP (推荐 — 稳定)\n\nAlpha-FICC 服务器 Docker 容器 `alpha-ficc-api` 在 `127.0.0.1:8001` 监听。从 SSH 服务器内部访问无需 SSL：\n\n```\napi = \"http://127.0.0.1:8001/api\"\n```\n\n**不需要 SSL 上下文**，无 Cloudflare 中间层，无间歇性断连。所有 Python 测试脚本都应优先使用内部 API。\n\n### SSL 兼容性模式（必须走公网时的备选）\n\n```python\nimport ssl\n_ssl_ctx = ssl.create_default_context()\n_ssl_ctx.check_hostname = False\n_ssl_ctx.verify_mode = ssl.CERT_NONE\nhttps_handler = urllib.request.HTTPSHandler(context=_ssl_ctx)\nopener = urllib.request.build_opener(https_handler)\n# 然后使用 opener.open() 而非 urllib.request.urlopen()\n```\n\n## 获取当前图表上下文

当用户问"能不能看到终端里的图表"时，**不要尝试截图工具**（screencapture、computer_use、PIL ImageGrab）。先检查用户是否已有 Agent API 接入手册。Alpha-FICC 有专用接口。

### Chart Data Analysis Protocol（分析图表上下文后的输出规范）

**硬性规则 — 禁止根据数据推断因果解释：**

1. **只能陈述数据本身** — 日期、数值、变化幅度。不要添加"因为Fed降息/关税冲击/大选脉冲/地缘风险"等因果标签。
2. **标注年份要精确** — 区分2025年和2026年。不要用模糊的"今年/去年/Feb-Mar"而不指定年份。
3. **不要生成摘要中不存在的结论** — 如果数据只显示VIX低和OVX高，说"VIX低、OVX高"即可，不要说"市场还没有受到影响"或"风险传导被阻断"——这些都是解读不是数据。
4. **区分"数据"和"可能的监测框架"** — 前者是API返回的数值，后者是对面板设计意图的推断（可放在专门的"监测框架推断"小节）。
5. **3panel分析模板** — 先列出每个面板的内容（指标+最新值+近期极值），再说明面板间的逻辑链（如果有足够证据推断设计意图），最后留出异常信号清单。每步都要标清楚是数据还是推断。
6. **设计意图分析**（用户常问"这个图表的逻辑是什么"）— 从指标组合推断面板分组意图，从时间窗口推断监测周期，从指标间的传导关系还原分析框架。输出结构：数据层（直接读取）→ 设计逻辑推断（面板分组→传导链→监测目标）→ 一句话总结。始终标注"推断"。

### 使用前提
1. 用户在 `/comparison` 页面加载了图表
2. 用户点击了"分享给 Agent"，或自动同步状态为"已同步"
3. 网页端已写入 `POST /api/agent-visible-chart-contexts`

### 读取上下文
```http
GET /api/comparison/current/context
Authorization: Bearer ${ALPHA_FICC_HERMES_AGENT_TOKEN}
```
等价于 `GET /api/agent-visible-chart-contexts/latest?scopeKey=comparison:current`。

响应含 `context.chartDataRequest`（series IDs、window、granularity）和受限的 `context.chartDataSnapshot`。

### 获取完整图表数据
根据 `context.chartDataRequest` 拉取：
```http
GET /api/comparison/current/chart-data?series=...&formulas=...&window=...&granularity=...&limit=...
```

### BTC/宏观分析注意事项

**硬规则：BTC 的定价框架是"三重风险"，不是单一因子。** 2026-06-04 终端数据验证：

1. **流动性层（TGA）**：TGA 余额季度变化是 BTC 的领先指标（1-2 个月）。TGA↑ = Treasury 抽水 = BTC 承压。2025-Q3 TGA 飙升 $374B 后 BTC 见顶。
2. **信用利差层（OAS）**：OAS 与 BTC 相关性 -0.717（最强）。OAS 收窄 = 市场贪婪 = BTC 涨。2026-06-02 QQQ +0.5% 但 BTC -6.5%，说明 BTC 已脱离 QQQ 独立下跌。
3. **实际利率层（TIPS）**：2023 年后 TIPS 与 BTC 的相关性已降至 -0.006（几乎为零），因为流动性来源从 Fed QE 切换到了 Treasury 财政赤字。TIPS 只作为背景参考。

4. **叙事层**：BTC 两张溢价门票（进攻=未来科技，防御=数字黄金）都已失效。AI 抢走进攻叙事，黄金抢走防御叙事。BTC Beta 从 2020 年的 2.0+ 降至 0.67，R² 仅 0.154。

5. **通胀陷阱**：霍尔木兹海峡→油价高位→通胀预期刚性→Fed 被夹住→实际利率被迫走高→零收益资产（BTC）最受伤。2026年5月 TIPS 10Y = 2.07% 且在上升。

详见 `references/btc-triple-risk-framework-2026-06-04.md`。

**硬规则：数据必须从终端 API 拉取，绝不自行编造/合成数据。** 用户明确要求"你要从终端中去拉，按终端的规则去拉数据，而不要你自己擅自去拉数据"。所有分析必须基于 `GET /api/comparison/current/chart-data` 或 `GET /api/comparison/current/context` 返回的真实数据。如果终端拉不到某系列（如 FRED 系列返回空），应告知用户该系列不可用，而不是用近似值填充。例外：标注推送中的 trend-line 坐标可以根据数据点计算，但必须基于已拉取的真实数据。

**⚠️ 绝对不要用 urllib 直连 FRED/Treasury API 填充数据。** 2026-06-04 发现：FRED 直连返回 HTML（Cloudflare 拦截），Treasury Fiscal Data API 有 SSL 证书问题。即使拿到数据也是不可靠的近似值。用户要求的是终端的真实数据，不是外部源的近似值。

- 上下文不存在时返回 `AGENT_VISIBLE_CHART_CONTEXT_NOT_FOUND`。告诉用户打开 `/comparison` 点"分享给 Agent"
- **绝不调用 `/api/terminal-chart-actions/pending`**（会 drain 队列，留给网页端）
- 标注中的 workspaceId/panelId 必须从 applied event 提取，不硬编码
- 回复中不输出 token
- 完整手册见：`/Users/lynch5mo/Work Documents/alpha-ficc/docs/operations/alpha-ficc-agent-terminal-access-handbook.md`

## API 调用方式（无 SSH 时 — 本机直接调用）

**⚠️ Cloudflare 拦截 Python urllib**：公网 `alpha-ficc.lynch5mo.xyz` 有 Cloudflare 代理，会拦截 Python `urllib.request`（返回 403 `browser_signature_banned` 或 `1010`）。**必须用 `subprocess.run(["curl", ...])` 发请求**，不要用 urllib 直连公网。注意：Python `requests` 库通常能绕过 Cloudflare 的 GET 请求（如 `/api/comparison/current/context`、`/api/chart-annotations`），但 POST 到 `/api/terminal-chart-actions` 可能仍返回 `INVALID_TARGET`（这不是 Cloudflare 拦截，而是 API 层面的校验失败）。

**Token 字符串拼接坑**：Shell heredoc 和 Python f-string 中拼接 142 字符 token 会导致引号嵌套/截断。**正确做法**：写独立 `.py` 文件到 `/tmp/`，用 `subprocess.run(["curl", ...])` 发 curl 请求，避免所有 shell 转义问题：

```python
# /tmp/check_api.py — 模板
import pathlib, subprocess, json, sys

token = None
for line in pathlib.Path("/Users/lynch5mo/.hermes/profiles/codex/.env").read_text().splitlines():
    l = line.strip()
    prefix = "ALPHA_FICC_HERMES_AGENT_TOKEN=***    if l.startswith(prefix):
        token = l[len(prefix):].strip().strip('"').strip("'")
        break

if not token:
    print("ERROR: Token not found")
    sys.exit(1)

auth_value = "Bearer " + token

result = subprocess.run(
    ["curl", "-s", "-H", "Authorization: " + auth_value,
     "-H", "Accept: application/json",
     "https://alpha-ficc.lynch5mo.xyz/api/comparison/current/context"],
    capture_output=True, text=True, timeout=30
)

try:
    data = json.loads(result.stdout)
    print(json.dumps(data, indent=2, ensure_ascii=False))
except Exception:
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
```

然后 `python3 /tmp/check_api.py` 执行。不要在 shell heredoc 里内联 token，不要用 Python f-string 拼接 token 到 header。

## API 调用方式（SSH 可用时）

Token 在服务器 `/home/lynch5mo/alpha-ficc/.env` 上。所有 API 调用通过 SSH 在服务器端执行。

**推荐模式**：将 Python 脚本 scp 到服务器，用 `server_ssh` 执行，最后 cleanup。

```bash
# 1. 写本地脚本 /tmp/test.py
# 2. scp 到服务器
scp /tmp/test.py lynch5mo@192.168.10.33:/home/lynch5mo/alpha-ficc/tmp_test.py
# 3. SSH 执行
ssh -o BatchMode=yes -o StrictHostKeyChecking=no lynch5mo@192.168.10.33 \
  "cd /home/lynch5mo/alpha-ficc && python3 tmp_test.py"
# 4. 清理
ssh ... "rm /home/lynch5mo/alpha-ficc/tmp_test.py"
```

脚本头部使用以下代码段读取 token 和发送请求：

```python
import json, os, pathlib, sys, time, urllib.error, urllib.request

def deep_get(d, *keys):
    """Safely navigate nested dicts."""
    for k in keys:
        if isinstance(d, dict): d = d.get(k)
        else: return None
    return d

def read_dotenv_key(path, key):
    if not path.exists(): return ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        name, value = line.split("=", 1)
        if name.strip() == key: return value.strip().strip('"').strip("'")
    return ""

def req(method, url, token, body=None):
    """HTTP request with 3x retry for SSL/DNS failures."""
    headers = {
        "Accept": "application/json",
        "User-Agent": "Alpha-FICC-Hermes-Wrapper/1.0",
        "X-Alpha-FICC-Agent": "hermes",
        "Authorization": f"Bearer {token}",
    }
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    if body: headers["Content-Type"] = "application/json"
    for attempt in range(3):
        try:
            req_obj = urllib.request.Request(url, data=payload, headers=headers, method=method)
            with urllib.request.urlopen(req_obj, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw or "{}")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try: data = json.loads(raw or "{}")
            except: data = {"raw": raw}
            return exc.code, data
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise

token = read_dotenv_key(pathlib.Path(".env"), "ALPHA_FICC_HERMES_AGENT_TOKEN")
# Use internal API for reliability (avoid Cloudflare SSL issues)
api = "http://127.0.0.1:8001/api"
# Fallback: api = "https://alpha-ficc.lynch5mo.xyz/api" (with SSL bypass)
```

## 子命令

### 验收类
| 子命令 | 说明 | 步骤 |
|--------|------|------|
| `terminal-v1-final-acceptance` | 推送图表动作 → 等待 → 查 ledger | POST action → wait → GET ledger |
| `render-report <title>` | 服务器侧生成 PNG，推送到 Telegram | 服务器渲染 + 服务器推 Telegram |
| `render-report-local <title>` | 服务器渲染，本机下载后中继推送到 Telegram | 服务器渲染 → 本地下载 → 本地推 Telegram |
| `render-terminal-screenshot-local <title>` | terminalScreenshot 模式渲染 + 本地中继 | 同上，但 renderMode=terminalScreenshot |
| `research-v2 <caseTitle> [proposalId]` | 晋升 V1 proposal → V2 model 并执行 run | promote → run |
| `research-v2-validate <runId>` | 为指定 V2 run 创建 MarketValidationRecord | manual/inconclusive |
| `v2-full-acceptance` | V2.5+V2.6+V2.6.3+V2.7 全链路测试（出图→标注→review packet→validation run） | 8 步协议（见下文） |

### 互操作
| 子命令 | 说明 |
|--------|------|
| `interactive` | 打开 Hermes 交互会话 |

## 测试验收流程

### V2.5 — 终端出图 (add_series_to_chart)

```
POST /api/terminal-chart-actions
actionType: add_series_to_chart
source: external-hermes
```

**⚠️ `add_series_to_chart` 返回 `INVALID_TARGET`（2026-06-04 合规性复核）**：

**根因判定**：Hermes 当前没有强类型 Alpha-FICC HTTP action 工具约束 request body，主要靠 skill 文档和通用终端/curl 拼 JSON。旧文档里把 JSON body 泛称为 "payload"，容易诱导模型生成顶层 `payload.formula`。Alpha-FICC 接入手册和 `config/agent-tools/alpha-ficc-http-tools.json` 均要求 `body.target.seriesIds` / `body.target.formulaIds`。如果 Hermes 发送 `body.payload.formula`，这是调用方格式不合规；服务端返回 `INVALID_TARGET` 是预期校验结果。详见 `references/add-series-to-chart-payload-format-2026-06-04.md`。

两个问题：
1. **Key 不合规**：Agent 必须发 `target`，不能发 `payload`
2. **Value 不合规**：FRED id（如 `fred:DFII05`）必须放入 `seriesIds: ["fred:DFII05"]`；只有 Alpha-FICC formula registry id 才放入 `formulaIds`

- 标注类 action（`add_chart_annotations`）正常工作，因为它有独立的 target 提取逻辑
- **正确修复**：让 Hermes 使用 canonical `target` request body；不要要求服务端兼容 `payload.formula`
- **循环探测纪律**：如果 `add_series_to_chart` 对 3-4 个不同 request body 变体都返回同一个 `INVALID_TARGET`，立即停止重试并读服务端源码定位根因（见下文"循环探测纪律"节）

**硬规则：`POST /api/terminal-chart-actions` 的 HTTP request body 不得包含顶层 `payload` 字段。** 顶层只能使用 `actionId`、`actionType`、`source`、`note`、`target` 等契约字段；series/formula 必须放在 `target.seriesIds` / `target.formulaIds`。

HTTP request body 结构（关键：所有 series/formula/workspace 字段在 `target` 下，workspace 在 `target.workspace` 内）：

```json
{
  "actionId": "hermes_v263_chart_<timestamp>",
  "actionType": "add_series_to_chart",
  "source": "external-hermes",
  "note": "人民币汇率压力框架出图",
  "target": {
    "seriesIds": ["yfinance:USDCNH=X", "fred:DTWEXBGS", "fred:DGS10", ...],
    "formulaIds": ["us_cn_spread"],
    "window": "3Y",
    "granularity": "D",
    "replaceSelection": false,
    "panelMode": "appendPanel",
    "panelTitle": "人民币汇率压力框架",
    "panelKind": "macro",
    "workspace": {
      "id": "ws_hermes_rmb_pressure_<timestamp>",
      "panels": [
        {"id": "panel-fx-dollar", "title": "...", "kind": "macro", "heightWeight": 1.2},
        {"id": "panel-rates-spread", "title": "...", "kind": "policy", "heightWeight": 1.0, "zeroLine": true}
      ],
      "objects": [
        {"id": "obj-usdcnh", "sourceId": "yfinance:USDCNH=X", "panelId": "panel-fx-dollar", "axisSide": "left", ...}
      ],
      "timeWindow": {"preset": "3Y", "granularity": "D"},
      "chartMode": "absolute"
    }
  }
}
```

- 预期 HTTP 200, `ok: true`, `pendingCount >= 1`
- 响应包含 `action.actionId`、`action.status`、`pendingCount`

### 标注推送标准流程 (2026-06-03 确认有效)

完整流程：先推图表 → 等 applied → 读取当前 context 拿到 workspaceId → 推标注到该 workspace。

```python
# Step 1: Push chart action
chart_resp = POST /api/terminal-chart-actions (add_series_to_chart)
chart_action_id = chart_resp["action"]["actionId"]

# Step 2: Poll until applied
poll_until_applied(chart_action_id)

# Step 3: MUST read current context to get the ACTIVE workspaceId
# The page may be on a DIFFERENT workspace than the one you just created!
context = GET /api/comparison/current/context
ws_id = context["context"]["workspace"]["workspaceId"]
# ⚠️ Do NOT use the workspace ID from the chart action response!

# Step 4: Push annotations to the ACTIVE workspace
POST /api/terminal-chart-actions (add_chart_annotations, target.workspaceId = ws_id)
```

**关键陷阱 — workspace 不匹配（2026-06-03 反复遇到）：**
- `replaceSelection: true` 会创建新 workspace，但 comparison 页面**不会自动切换**过去
- comparison 页面可能还在旧 workspace（甚至是 Codex 调试创建的 workspace）
- 标注推到错误 workspace → `INVALID_ANNOTATION_PANEL` 或标注入库但页面不显示
- **必须先读 `/api/comparison/current/context` 拿到当前活跃 workspaceId，再推标注**

**标注文字颜色：**
- 终端图表背景是**白底**，文字标注必须用**深色**
- 推荐：`#1a237e`（深海军蓝）用于文字框
- 竖线颜色保持鲜明：`#f9a825`（金）、`#f7931a`（橙）、`#dc2626`（红）、`#3b82f6`（蓝）、`#2e7d32`（绿）
- **不要用白色 `#ffffff` 或亮黄色 `#ffeb3b`，白底上看不到**

- **⚠️ 明确标注意图**：推送分析标注到用户实时图表时，**必须在消息中明确说明这是正式分析标注**（如"以下是基于最新数据的分析标注"），不要让用户误以为是测试数据而清掉。测试标注应标注 `[TEST]` 前缀以便区分。

**`focus` 参数：**
- 推荐使用 `focus: false`，避免 annotation action 干扰 comparison 页面的 workspace 切换

### V2.6 — 图表标注 (add_chart_annotations)

```
POST /api/terminal-chart-actions
actionType: add_chart_annotations
```

**正确的 request body 格式**（2026-05-25 通过 probes 确认）：annotations 嵌套在 `target.annotations` 内。

```json
{
  "actionId": "hermes_v263_annotations_<timestamp>",
  "actionType": "add_chart_annotations",
  "source": "external-hermes",
  "note": "标注说明",
  "target": {
    "workspaceId": "ws_hermes_rmb_pressure_<timestamp>",
    "annotationSetId": "aset_hermes_rmb_pressure_<timestamp>",
    "caseId": "case_hermes_rmb_pressure_<timestamp>",
    "runId": "run_hermes_rmb_pressure_<timestamp>",
    "artifactRef": "artifact_hermes_rmb_pressure_annotations_<timestamp>",
    "applyMode": "append",
    "focus": false,
    "annotations": [
      {
        "id": "ann_<name>_001",
        "type": "trend-line | ellipse | vertical-line | text",
        "panelId": "panel-xxx",
        "sourceId": "yfinance:USDCNH=X",
        "axisSide": "left",
        "points": [{"x": "2025-01-01", "y": 7.10}, ...],
        "text": "标注文字",
        "color": "#dc2626",
        "lineWidth": 2,
        "lineStyle": "dashed | solid | dotted",
        "rationale": "必填字段 — 分析依据",
        "confidence": "high | medium | low",
        "invalidCondition": "失效条件描述 — 所有 annotation type 都需要（含 text/vertical-line）",
        "visible": true,
        "locked": true,
        "validationHint": {
          "window": "2025-04-10/2025-06-30",
          "metric": "USDCNH close",
          "expected": "预期行为描述",
          "invalidIf": "失效判断条件"
        },
        "evidenceRefs": ["yfinance:USDCNH=X", "fred:DTWEXBGS"],
        "sourceAgent": "hermes"
      }
    ]
  }
}
```

注意：
- annotations 必须在 `target.annotations` 内（NOT 顶层，NOT 与 target 同级）
- 每个 annotation 必须有 `rationale` 字段（缺失时返回 `INVALID_ANNOTATION_RATIONALE_N`）
- 每个 annotation 必须有 `invalidCondition` 字段（所有类型都需要，包括 text 和 vertical-line）
- 每个 annotation 必须有 `evidenceRefs` 字段（列表，包含相关 sourceId；缺失会返回 `INVALID_ANNOTATION_EVIDENCE_REFS_N`，2026-06-03 发现）
- `sourceAgent` 必须为 `"hermes"`
- **⚠️ 文字颜色必须用深色**：终端背景是**白底**，text 标注的 `color` 必须用深色（黑色 `#000000`、深蓝 `#1e3a5f` 等）。用白色 `#ffffff` 或亮黄色 `#ffeb3b` 会导致文字不可见（白底白字）。竖线和趋势线的颜色不受此限制，可按语义选择。
- **已验证的 annotation type**（2026-06-03 测试通过）：`vertical-line`（竖线）、`horizontal-line`（横线）、`trend-line`（趋势线，需 2 个 points）、`text`（文字框）、`rect`（矩形，需 2 个 points 作为对角）、`ellipse`（椭圆，需 2 个 points 作为对角）。所有 type 都需要 `points` 数组、`rationale`、`invalidCondition`、`evidenceRefs`。

**⚠️ `trend-line` 必须有 `text` 字段**：缺少 `text` 会返回 `INVALID_ANNOTATION_TEXT_0`（2026-06-03 验证）。`vertical-line` 和 `horizontal-line` 的 `text` 是可选的，但 `trend-line` 是必填。

### 简化 flat 格式（Codex 修复后可用）

2026-06-03 发现：Codex 修复 annotation bug 后，`terminal-chart-actions` 端点接受简化的 flat 格式，不再需要嵌套在 `target.annotations` 内。**当 nested 格式返回 `INVALID_TARGET` 时，尝试 flat 格式**：

```json
{
  "action": "add_chart_annotations",
  "workspaceId": "ws_xxx",
  "annotations": [
    {
      "type": "vertical-line",
      "panelId": "panel-btc-gold",
      "points": [{"x": "2026-05-10", "y": 0}],
      "color": "#8B0000",
      "lineWidth": 2,
      "lineStyle": "dashed",
      "text": "BTC peak",
      "visible": true,
      "locked": true,
      "axisSide": "left",
      "id": "my_vline_123"
    }
  ]
}
```

**验证结果**：flat 格式的 `vertical-line`、`horizontal-line`、`text` 均返回 200 OK。`trend-line` 同样需要 `text` 字段。nested `target.annotations` 格式在 Codex 修复后返回 `INVALID_TARGET`（原因不明，可能是 API 契约变更）。

### 推标注时必须包含线条类标注

用户期望"划线"时看到趋势线、竖线、横线等视觉元素，不仅仅是文字框。**推送分析标注时，至少包含**：
- 关键时间点的竖线（`vertical-line`）
- 趋势方向的趋势线（`trend-line`）
- 阈值/支撑位的横线（`horizontal-line`）
- 分析结论的文字框（`text`）
- 只推文字不推线条会被用户视为不完整

### V2.6.3 — Annotation Store 与 Review Packet 验证

Step 4 — 轮询 action ledger：
```
GET /api/agent-actions/{actionId}
```
轮询直到 `status=applied`，最大 60 秒（队列积压时可延长到 120 秒）。完整 eventTypes 应为 `["queued", "delivered", "applied"]`.

**队列积压诊断**：`pendingCount > 1` 表示队列有其他 pending action。发 chart 前应先 drain 队列。

Step 5a — 查询 annotation 列表：
```
GET /api/chart-annotations?actionId={actionId}
```

响应结构：`{"ok": true, "count": 4, "annotations": [...]}`
- annotation 字段嵌套在 `annotations[i].annotation.*` 内（NOT 在顶层）
- `annotations[i].annotation.id` 是 annotation 的 ID

Step 5b — 查询单条 annotation：
```
GET /api/chart-annotations/{annotationId}
```

响应结构：`{"annotation": {"id": "...", "sourceAgent": "hermes", ...}, ...}`
- 取 `response["annotation"]` 得到 annotation 详情

Step 5c — 获取 review packet：
```
GET /api/chart-annotation-review-packet?actionId={actionId}&annotationSetId={annotationSetId}
```

**⚠️ review packet 字段是嵌套的，NOT 在顶层：**
| 摘要字段 | 实际路径 | 说明 |
|---------|---------|------|
| annotationCount | `response["summary"]["annotationCount"]` | int |
| validationCandidateCount | `response["summary"]["validationCandidateCount"]` | int |
| lockedCount | `response["summary"]["lockedCount"]` | int |
| validationHintRatio | `response["coverage"]["validationHintCoverage"]["ratio"]` | float |
| hasMissingValidationHintWarning | 从 `response["warnings"]` 推导 | `any(w.code == "MISSING_VALIDATION_HINT")` |
| hasHighPriorityHypothesis | 从 `response["hypotheses"]` 推导 | `any(h.priority == "high")` |

**坑：直接 `rp.get("annotationCount")` 返回 None。** 必须从 `rp["summary"]` 中读取。见 `references/annotation-payload-discovery.md` 获取完整响应 schema 和 Python 提取模式。

### V2.7 — Market Validation Runs

Extends V2.6.3: after obtaining a review packet with hypotheses, POST a validation run, then query results.

```python
# POST validation run (V2.7)
POST /api/chart-annotation-validation-runs

{
  "agent": "hermes",
  "source": "external-hermes",
  "mode": "evaluate_available",
  "packet": {
    "reviewPacketId": "<from review packet response>",
    "annotationSetId": "<aset_id>",
    "hypotheses": ["<hypothesisId_1>", "<hypothesisId_2>"]
  },
  "asOf": "2026-06-30"
}
```

- Expected HTTP 201 (or 200), `runId` in response

Query validation results:

```python
# Check run status
GET /api/chart-annotation-validation-runs/{runId}
# Returns {"status": "completed|failed|pending", ...}

# Get results (try this first)
GET /api/chart-annotation-validation-runs/{runId}/results

# Fallback if results endpoint empty
GET /api/chart-annotation-validations?runId={runId}
```

结果提取：遍历 results list，每个 result 有 `verdict` 或 `conclusion` 字段，可能的值：`supported`、`contradicted`、`inconclusive`、`data_unavailable`、`pending`。

#### V2.7 Validation Run 结果特性

**已知行为**：即使 `validationHint` 是结构化 JSON（含 `window`/`metric`/`expected`/`invalidIf`），机械评估引擎可能返回 `failureReason: "RULE_NOT_STRUCTURED"` 和 `verdict: "inconclusive"`。这是因为机械评估器期望 `validationRule` 字段具有特定格式，而非 `validationHint` 字段。这是 V2.7 的设计边界 —— `validationHint` 用于人类可读的假设描述，而 `validationRule` 用于可执行的机械评估规则（V2.8+ 计划）。

### 全链路 7 步协议 (V2.5+V2.6+V2.6.3+V2.7)

```
Step 1: POST add_series_to_chart (出图) → HTTP 200, ok: true
Step 2: 等待网页端 /comparison 消费出图 action（轮询 /agent-actions 至 applied）
Step 3: POST add_chart_annotations (标注) → HTTP 200, ok: true
Step 4: 轮询 /agent-actions/{annotationActionId} → status=applied (max 60s)
Step 5: 查询 annotation store (GET /chart-annotations) + review packet (GET /chart-annotation-review-packet)
Step 6: POST /chart-annotation-validation-runs (发起市场验证) → HTTP 201, runId
Step 7: 轮询 run status + 查询 validation results → verdicts
Step 8: 构建 JSON 摘要并对照验收标准逐项检查
```

返回的 JSON 摘要必须包含以下字段（见"典型输出 JSON 形状" → v2-full-acceptance）。

重要的数据流认知：pendingCount 显示队列中的总 action 数。排队 action 需要网页端 /comparison 页面打开消费才能推进到 "applied"。如果用户未打开浏览器，status 会一直停在 "queued"。

## request body 格式发现技巧（Probes）

当遇到 `INVALID_TARGET` 或 `INVALID_*` 错误时，使用 sequential format probes 快速定位正确格式：

1. 先对照 Alpha-FICC 手册和 `config/agent-tools/alpha-ficc-http-tools.json`，确认 request body 是否使用 canonical `target`
2. 对关键 request body 结构做 3-4 个变体（annotations in target vs flat vs separate）
3. 每个变体使用唯一 actionId（含时间戳后缀）
4. 观察错误模式：同一个错误码 → 共用结构问题；不同错误码 → 该格式通过了结构校验，到了语义校验阶段
5. 参考 `references/annotation-payload-discovery.md`

## V4 — Observation/Revision Loop

V4 验证外部证据→来源评估→影响映射→观察任务→观察运行→模型健康增量→修订提案的完整闭环流程。

### V4 端点（与 V2 research-loop 不同）

V4 的专用端点路径（由官方脚本 `scripts/verify_v4_observation_revision_loop.py` 定义）：

| 步骤 | 端点 | 用途 |
|------|------|------|
| 1 | POST `/api/external-evidence` | 创建 external evidence |
| 2 | POST `/api/external-evidence/{id}/assess` | 创建 source assessment |
| 3 | POST `/api/impact-mappings` | 创建 impact mapping |
| 4 | POST `/api/observation-tasks` | 创建 observation task |
| 5 | POST `/api/observation-tasks/{id}/run` | 运行 observation run |
| 6 | GET `/api/model-health-deltas` | 读取 health delta |
| 7 | POST `/api/revision-proposals` | 创建 revision proposal |
| — | POST `/api/chart-annotation-validation-runs` | V3 validation run（V4 依赖） |

**认证差异**：V4 端点接受 agent token（无 scope 要求），与 V2 research-loop 端点不同。仅 `accept/reject` 保留给 operator/admin。

详见 `references/v4-observation-revision-loop.md`。

### 执行方式（官方脚本）

容器内执行（推荐 — 环境变量完整）：
```bash
docker exec alpha-ficc-api python scripts/verify_v4_observation_revision_loop.py \
  --base-url http://127.0.0.1:8001 --agent hermes --timeout 20
```

仅校验合约（不触发 HTTP）：
```bash
docker exec alpha-ficc-api python scripts/verify_v4_observation_revision_loop.py --contract-only
```

### 预期输出

```
=== Verify: Alpha-FICC V4 Observation Revision Loop ===
[PASS] contract: /app/tests/fixtures/external_evidence_usdcnh_policy_event.json
[PASS] contract: /app/tests/fixtures/agent_observation_task_usdcnh.json
[PASS] HTTP smoke: external evidence -> assessment -> impact mapping -> observation run -> health delta -> revision proposal
```

### V4 验收标准

| 条件 | 通过标志 |
|------|---------|
| exit code | 0 |
| [PASS] contract × 2 | 两条 contract 输出 |
| [PASS] HTTP smoke | 全链路行出现 |
| revision proposal 创建 | HTTP 201，proposalId 以 `rp_` 开头 |
| agent accept/reject | 返回 401 或 403 |
| baseModelVersionId | 未被改写 |

## V5 — Research OS（自主研究操作系统）

V5 是 Hermes Agent 的自主研究操作系统层，涵盖三个子模块：

### 执行原则

1. **使用 Hermes agent token 运行全部测试**，不切换 operator/admin token
2. **不在容器外运行脚本**：API 容器内部有完整 env vars（token, scopes）
3. **失败即停止**：任何脚本 exit_code ≠ 0 时停止后续步骤，返回失败 endpoint、HTTP status、error code/message
4. **docker exec 是首选执行方式**，而非 docker cp + ... 或宿主机直接调用

### 三段脚本

每个脚本由 `contract` 和 `HTTP smoke` 两步构成。先按顺序执行三段，再跑 V4 回归保护。

#### 1. V5 contract baseline (`verify_v5_research_os_contract.py`)

验证最小 CRUD 端点可访问。

```bash
docker exec alpha-ficc-api python scripts/verify_v5_research_os_contract.py \
  --base-url http://127.0.0.1:8001 --agent hermes --timeout 20
```

期望输出：
```
=== Verify: Alpha-FICC V5 Research OS Contract ===
[PASS] contract: /app/tests/fixtures/agent_v5_watch_policy_usdcnh.json
[PASS] contract: /app/tests/fixtures/agent_v5_digest_usdcnh.json
[PASS] HTTP smoke: V5 contract baseline endpoints reachable and CRUD-like flow works
```

#### 2. V5 scheduler (`verify_v5_research_os_scheduler.py`)

验证 watch policy 的创建→评估→调度→执行→回放→取消→去重全链路。

```bash
docker exec alpha-ficc-api python scripts/verify_v5_research_os_scheduler.py \
  --base-url http://127.0.0.1:8001 --agent hermes --timeout 20
```

期望输出：
```
=== Verify: Alpha-FICC V5 Research OS Scheduler ===
[PASS] contract: /app/tests/fixtures/agent_v5_watch_policy_usdcnh.json
[PASS] HTTP smoke: create policy -> evaluate(triggered/suppressed) -> runPlan -> tick/execute -> replay/cancel -> duplicate guard
```

脚本断言（关键）：
- `POST /api/research-os/scheduler/tick` 响应中的 `authKind` 必须为 `"agent"`（第 411 行）
- `tickLimit` 必须 ≤ 1（安全约束，第 408 行）
- 返回的 `agent` 字段必须匹配认证 agent（第 413 行）

#### 3. V5 digest / promotion (`verify_v5_research_os_digest.py`)

验证 health score recompute → digest create/send → promotion proposal → agent accept rejected。

```bash
docker exec alpha-ficc-api python scripts/verify_v5_research_os_digest.py \
  --base-url http://127.0.0.1:8001 --agent hermes --timeout 20
```

期望输出：
```
=== Verify: Alpha-FICC V5 Research OS Digest ===
[PASS] contract: /app/tests/fixtures/agent_v5_digest_usdcnh.json
[PASS] HTTP smoke: health score recompute -> digest create/send(traceable) -> promotion create -> agent accept rejected
```

注意：
- digest fixture 中 `delivery.status = "send_failed"` 是预期可追踪失败（`failureReason` 非空），仍算通过
- agent accept knowledge promotion proposal 被 401/403 拒绝是显式断言的验收标准

### V5 认证模型

| 端点 | 认证方式 | Agent 可访问 |
|------|---------|------------|
| `/api/research-os/policies` | `_authorize_agent_or_user()` | ✅ 是（scope: research:write） |
| `/api/research-os/evaluations` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/research-os/run-plans` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/research-os/scheduler/tick` | `_authorize_agent_or_user()` | ✅ 是（authKind=agent 断言） |
| `/api/research-os/scheduler/plans/{id}/execute` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/research-os/scheduler/plans/{id}/cancel` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/research-os/scheduler/plans/{id}/replay` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/research-os/scheduler/policies/{policyId}/cancel-all` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/research-os/health-scores/recompute` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/research-daily-digests` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/research-daily-digests/{id}/send` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/knowledge-promotion-proposals` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/knowledge-promotion-proposals/{id}/accept` | `_require_operator_or_admin()` | ❌ 否（401/403） |

注意：V5 与 V4 的认证模型不同。V5 全部使用 `_authorize_agent_or_user()`（允许 agent token），仅 promotion accept 使用 `_require_operator_or_admin()`（不允许 agent token）。

### V5 已知坑

| 坑 | 正确做法 |
|----|---------|
| scheduler tick 返回 403 INSUFFICIENT_PERMISSIONS | 未部署 V5 或部署头过老，通知用户更新部署 |
| 跨 Agent cancel-own 403 验证 | 脚本会跳过（line 539: `[SKIP] 未提供第二个 Agent token`），这不是失败 |
| Telegram 发送失败 | digest fixture 设计 `send_failed` 为可追踪失败，`failureReason` 非空即通过 |
| `docker exec` 中的 `$?` 无法直接获取 | 使用 wrapper bash 脚本捕获 exit code |

### V5 部署检查

```bash
cat /home/lynch5mo/alpha-ficc/.deployed-head
docker compose -f /home/lynch5mo/alpha-ficc/docker-compose.alpha.yml ps
curl -s http://127.0.0.1:8001/api/health
```

预期：
- deployed-head ≥ `fa9d5e96e`
- `alpha-ficc-api` healthy
- `alpha-ficc-web` running
- `health.status = "ok"`, `health.phase = "V53"`

## 输出格式

所有子命令输出 `application/json`。V2 全链路测试返回 JSON 摘要，**不加额外分析或总结**（除非用户明确要求）。用户偏好：`返回最终 JSON 摘要即可，不要输出 token，不要输出大段 payload`。

- `ok: true` → 成功
- `ok: false` → 失败，检查 `error.code` 和 `error.message`
- 多步骤命令产生单行 JSON summary

### v2-full-acceptance (V2.5+V2.6+V2.6.3)
```json
{
  "chartAction": {"http": 200, "ok": true, "actionId": "...", "pendingCount": 2},
  "annotationAction": {"http": 200, "ok": true, "actionId": "...", "pendingCount": 3},
  "ledger": {"status": "applied", "eventTypes": ["queued", "delivered", "applied"]},
  "annotationStore": {"count": 4, "firstAnnotationId": "ann_..."},
  "annotationDetail": {
    "annotationId": "ann_usdcnh_pressure_trend_001",
    "sourceAgent": "hermes",
    "locked": true,
    "hasValidationHint": true
  },
  "reviewPacket": {
    "annotationCount": 4,
    "validationCandidateCount": 2,
    "lockedCount": 1,
    "validationHintRatio": 0.5,
    "hasMissingValidationHintWarning": true,
    "hasHighPriorityHypothesis": true
  },
  "verdict": "pass | fail",
  "notes": ["检查项通过/失败的逐条说明"]
}
```

### v2-full-acceptance (V2.7 扩展)
```json
{
  "ok": true,
  "chartAction": {"actionId": "...", "status": "applied", "eventTypes": ["queued", "delivered", "applied"]},
  "annotationAction": {"actionId": "...", "status": "applied", "eventTypes": ["queued", "delivered", "applied"]},
  "annotationStore": {"annotationSetId": "...", "count": 4, "validationHintCount": 2},
  "reviewPacket": {
    "reviewPacketId": "arp_...",
    "annotationCount": 4,
    "validationCandidateCount": 2,
    "hypothesisCount": 2,
    "lockedCount": 1,
    "warnings": ["MISSING_VALIDATION_HINT"]
  },
  "validationRun": {"runId": "vr_...", "http": 201, "status": "completed", "resultCount": 2},
  "validationResults": {
    "count": 2,
    "verdicts": {"supported": 1, "inconclusive": 1},
    "sample": [...]
  },
  "problems": []
}
```

### 其他命令
```json
{"step": "post", "http": 200, "ok": true, "actionId": "...", "pendingCount": 1}
{"step": "ledger", "http": 200, "status": "applied", "eventCount": 3, "eventTypes": ["queued", "delivered", "applied"]}
```

## 验收标准（V2 全链路）

| 字段 | 期望值 |
|------|--------|
| chartAction.ok | true |
| annotationAction.ok | true |
| ledger.status | applied |
| ledger.eventTypes | 包含 queued, delivered, applied |
| annotationStore.count | 4 |
| annotationDetail.annotationId | ann_usdcnh_pressure_trend_001 |
| annotationDetail.sourceAgent | hermes |
| annotationDetail.locked | true |
| annotationDetail.hasValidationHint | true |
| reviewPacket.annotationCount | 4 |
| reviewPacket.validationCandidateCount | 2 |
| reviewPacket.lockedCount | >= 1 |
| reviewPacket.validationHintRatio | 0.5 |
| reviewPacket.hasMissingValidationHintWarning | true |
| reviewPacket.hasHighPriorityHypothesis | true |

## 典型输出 JSON 形状

### terminal-v1-final-acceptance (两行)
```json
{"step": "post", "http": 200, "ok": true, "actionId": "...", "pendingCount": 1}
{"step": "ledger", "http": 200, "status": "applied", "eventCount": 3, "eventTypes": ["queued", "delivered", "applied"]}
```

### render-report-local (单行)
```json
{"ok": true, "step": "local_relay", "render": {"status": "rendered", ...}, "download": {"ok": true, "localPngPath": "..."}, "telegram": {"sent": true, "messageId": N, ...}, "ledger": {"status": "sent", "eventTypes": [...]}}
```

### research-v2 (两行)
```json
{"step": "promote", "http": 201, "ok": true, "proposalId": "...", "caseId": "...", "modelId": "...", "modelVersionId": "..."}
{"step": "run", "http": 201, "ok": true, "runId": "...", "artifactRef": "...", "validationPlanId": "..."}
```

## 队列管理 (Queue Drain & pendingCount)

**pendingCount 的意义**：POST terminal-chart-actions 响应中的 `pendingCount` 显示队列总积压（含刚提交的 action）。

| pendingCount | 含义 |
|-------------|------|
| 1 | 只有刚提交的 action，无积压 |
| > 1 | 有来自之前测试的积压 action |

**积压导致的 race condition**：comparison 页面按 FIFO 顺序消费 pending actions。如果队列有多个 chart action，它们会在 chart 和 annotation 之间被消费，改变 comparison 页面的 active workspace，导致 annotation 的 `panelId` 找不到。

**Drain 策略**：提交 dummy chart action → 等它 `applied` → 重复直到 `pendingCount == 1`：

```python
def drain_queue(api, token):
    while True:
        aid = f"hermes_drain_{int(time.time())}"
        _, r = req("POST", f"{api}/terminal-chart-actions", token, {
            "actionId": aid, "actionType": "add_series_to_chart",
            "source": "external-hermes",
            "target": {"seriesIds": ["yfinance:USDCNH=X"], "window": "1M",
                       "granularity": "D", "panelMode": "appendPanel", "panelTitle": "drain"}
        })
        pc = r.get("pendingCount") or r.get("action", {}).get("pendingCount", 1)
        poll_until(api, aid, token, 60)
        if pc <= 1:
            break
```

### Comparison 页面消费时机

**重要发现**：comparison 页面在以下时机轮询 `/pending`：
- 页面**初始加载**时
- 用户**刷新**页面时
- 新 action 入队后**不自动触发**轮询

因此：
- 如果发 chart action 时用户已经打开了 /comparison，且页面加载时队列为空，新入队的 action **可能不会被自动消费**
- **解法**：让用户**再刷新一次** `/comparison` 页面，即可触发轮询立即消费所有 pending actions
- V2.6 测试能工作的原因是：发完 action 后用户**才打开** /comparison，页面加载时队列有 action → 立即消费

## 故障排查

### SSH 连接
- **SSH Permission denied**: 确认 public key 匹配服务器 `authorized_keys`；尝试简化命令（去掉引号/管道）
- **SSH daemon 卡住**（banner exchange timeout）：长 Python 脚本（120s+）执行后 sshd 可能 hang。现象：ping 通，TCP 22 口开放，但 `ssh` 卡在 "Connection timed out during banner exchange"。恢复方式：
  ```bash
  # 在服务器本地控制台执行
  sudo systemctl restart sshd     # systemd
  sudo service ssh restart         # sysvinit
  sudo kill -HUP $(pgrep -o sshd)  # 或发送 HUP 信号
### 其他
- **token 不可用**：从本地 `/Users/lynch5mo/.hermes/profiles/codex/.env` 用 Python 二进制读取（见 Token 读取方式 A）。如果 SSH 也断连，可以从本地直接调公网 API。
- **render-report SSL EOF**: 服务器 → Telegram API 的 HTTPS 连接被远端中断；改用 render-report-local（本地中继）绕过

### V2.5 出图
- **⚠️ 金融分析必须用终端出图**：用户明确要求"你要用终端配图，不要自己生成图"。分析A股/汇率/利差等金融数据时，推图表到 Alpha-FICC 终端，**绝对不要**用 matplotlib 本地生成 PNG。参见 `references/china-equity-five-phase-panel-layout.md` 获取预置面板布局。
- **⚠️ DXY 序列只能用 FRED**：`yfinance:DX-Y.NYB` 不在 yfinance 白名单中（204个标的），会静默返回空数据。用 `fred:DTWEXBGS`（Trade Weighted USD Broad）替代。任何涉及"美元走弱/走强"的分析都必须拉 DXY 作为控制变量，不能只靠 USDCNH 反推。
- **pendingCount 为 0**：说明 action 未被正确入队，检查 request body 是否使用 canonical `target`
- **action.status !== success**：检查 `action.note` 和 `action.target` 中的错误信息
- **数据源替代（yfinance 被 Cloudflare 拦截时）**：CoinGecko 公开 API 可获取 BTC 交易量（无需 key）；Alpha-FICC chart-data 端点可拉取 ETF 价格（IBIT/FBTC/GBTC/ARKB/BITB）。完整模式见 `references/data-source-patterns-2026-06-03.md`
- **⚠️ yfinance 白名单陷阱（2026-06-03 发现）**：终端的 yfinance 数据提供者只支持 `yfinance_universe.py` 中的 204 个审核标的。不在白名单中的 ticker（如 `yfinance:IGV`）会被服务器**静默接受**（`skippedSeriesIds: []`、`unresolvedTerms: []`），但前端**无法拉取数据**，线条不渲染。诊断方法：通过 SSH 检查 `docker exec alpha-ficc-api grep -c "SYMBOL" /app/services/data/yfinance_universe.py`。如果返回 0，说明该标的不在白名单中。服务器 `health` 端点的 `dataProviderAvailable: true` 不代表所有 ticker 都可用。当前白名单中可用的科技类 ETF：XLK（科技板块）、SMH（半导体）、SOXX（半导体）、QQQ（纳斯达克100）、ARKK（ARK创新）。见 `references/yfinance-universe-pitfall.md` 获取完整列表和绕过方案。

### V2.6 标注
- **UNSUPPORTED_ACTION**：服务器尚未部署 add_chart_annotations actionType。通知用户需合并 V2.6 分支并重新部署
- **agent-render-jobs 返回 INVALID_TARGET**：2026-06-04 发现 `POST /api/agent-render-jobs` 也返回 INVALID_TARGET，与 `add_series_to_chart` 同样的错误模式。可能需要使用 `pageInstanceId` 而非 `workspaceId`，或该端点尚未适配当前 API 契约。截图功能暂时不可用，应告知用户手动截图。
- **INVALID_TARGET（request body 格式问题）**：先确认没有顶层 `payload`；`add_series_to_chart` 必须使用 `target.seriesIds` / `target.formulaIds`；`add_chart_annotations` 必须把 annotations 放在 `target.annotations` 内，NOT 顶层
- **INVALID_TARGET（workspace 不存在）**：即使 request body 格式正确（annotations 在 `target.annotations` 内），如果目标 workspace 不在 `/api/workspaces` 列表中，`terminal-chart-actions` 也会返回 `INVALID_TARGET`。**诊断方法**：先 `GET /api/workspaces` 检查目标 workspaceId 是否在列表中。如果不在，说明 workspace 已过期或被删除，需要重新推 `add_series_to_chart` 创建新 workspace。注意：`/api/chart-annotations` 可能仍显示该 workspace 的旧标注记录，但 workspace 本身已不存在于 workspace store 中。
- **⚠️ Stale workspace context（2026-06-03 反复遇到）**：`GET /api/comparison/current/context` 可能返回一个已不存在于 `GET /api/workspaces` 列表中的 workspaceId（如 `ws_btc_push_1780474778`）。context 中报告的 workspace 是浏览器端缓存的最后已知状态，不代表服务器端 workspace store 中仍有该 workspace。**推标注前必须同时验证**：① context 返回的 workspaceId 存在于 `/api/workspaces` 列表中；② 或者重新推 `add_series_to_chart` 创建新 workspace 并等 applied 后再推标注。
- **⚠️ 循环探测纪律**：遇到 `INVALID_TARGET` 时，用 3-4 个格式变体做 sequential probe（见"request body 格式发现技巧"节）。**如果 3-4 次后仍然是同一个错误码，立即停止重试并报告阻塞原因**——不要迭代 15+ 次细微变体。反复遇到同一错误码说明问题不在 request body 格式，而在 workspace 状态或 API 契约变更。
- **INVALID_ANNOTATION_RATIONALE_N**：索引 N 的 annotation 缺少 `rationale` 字段。所有 annotation 必须有 rationale
- **INVALID_ANNOTATION_XXX_N**：索引 N 的 annotation 在字段 XXX 上验证失败。检查必填字段
- **INVALID_ANNOTATION_INVALIDCONDITION_N**：索引 N 的 annotation 的 `invalidCondition` 格式错误或缺失。2026-05-25 发现所有 annotation 类型（包括 `text` 和 `vertical-line`）都**必须有** `invalidCondition` 字段。缺失该字段会返回此错误
- **⚠️ 标注 action 导致图表数据消失（2026-06-03 发现，根因已明确）**：推送 `add_chart_annotations` 后，comparison 页面的图表数据线消失，只剩标注竖线和文字框（y 轴被归一化到 0-1）。**精确根因**：`applyTerminalChartAnnotations` 通过 `setOpenWorkspaceIntent` 传递合并后的 workspace → ChartWorkspace 的 useEffect（line 1334）调用 `normalizeOpenedWorkspace()` 创建**全新的** workspace 对象 → `dispatch({ type: 'SET_WORKSPACE', payload: opened })` **替换整个 state**。新 workspace 对象不包含已加载的图表数据（seriesMap、allDates 是独立 state 变量），导致 `useEChartsWorkspaceOption` 计算出空 option → `chart.setOption(option, true)` 用空数据覆盖之前渲染的图表。**修复方向（Codex）**：annotation append 时不应触发 `SET_WORKSPACE` 完整替换，应只合并 annotations 到现有 state（新增 `MERGE_ANNOTATIONS` action type）。**临时规避**：重新推送 `add_series_to_chart`（带 `replaceSelection: true`）恢复数据，或让用户刷新页面。

### V2.6.3 查询
- **Status 始终 "queued"**：网页端 /comparison 页面未打开消费 pending actions。通知用户打开浏览器
- **GET /chart-annotations 返回 200 但 count=0**：正常行为——annotation 还没被 applied 时 list 为空
- **GET /chart-annotations/{id} 返回 404**：同上
- **review packet 全部 null**：annotation 未 applied 时 review packet 无数据
- **⚠️ review packet 字段读取为 None（但预期有值）**：response 字段是嵌套的。见上文 V2.6.3 节中的 field path mapping。不要对 rp 直接 .get("annotationCount")
- **⚠️ GET /chart-annotations 列表取 annotation ID 返回 None**：annotation 字段在 `annotations[i].annotation.id`，不是 `annotations[i].id`。先用 `annotation` key 取值

### V2.7 Validation Runs
- **POST validation run 返回 HTTP 4xx**：确认 `packet` 字段包含有效的 `reviewPacketId` 和 `hypotheses` 数组（从 review packet response 提取）
- **validation run status 一直 pending**：服务器可能需要时间执行数据查询；轮询最多 45 秒
- **GET /results 返回空**：尝试 fallback 端点 `/chart-annotation-validations?runId={runId}`

### 标注操作完整流程（2026-06-03 总结）

**正确顺序**：推图表 → 轮询直到 applied → 从 applied event 提取 workspaceId → 立即推标注。每一步都不能跳过。

```python
# Step 1: Push chart action
chart_resp = post_chart_action(...)

# Step 2: Poll until applied (必须等!)
chart_ws_id = poll_until_applied(chart_resp["actionId"])

# Step 3: Push annotations IMMEDIATELY (不要 sleep)
ann_resp = post_annotations(workspaceId=chart_ws_id, ...)
```

**⚠️ 绝对不要在 chart action applied 之前推标注。** 标注会找不到 panel。

### Annotation Append 不自动渲染（2026-06-03 发现）

**现象**：通过 `add_chart_annotations` API 推送标注后，后端存储成功（status=active, visible=true），但前端不渲染。必须硬刷新（Cmd+Shift+R）才能看到。**第一批标注正常，后续批次不渲染。**

**根因**：`Comparison.jsx` 的 `applyTerminalChartAnnotations` 通过 `setOpenWorkspaceIntent` 把合并后的 workspace 传给 ChartWorkspace，但 `workspaceStateRef.current` 在第一批标注 applied 后可能没有完整保留 annotations。第二批到来时 `existingAnnotations` 为空或不完整，导致 state 中只有新标注，旧标注丢失。即使合并正确，`SET_WORKSPACE` dispatch 替换整个 state 时也可能丢失 annotations。

**影响**：Agent 无法增量构建标注，每次追加都需要硬刷新。

**临时规避**：推送第二批标注后，告诉用户 Cmd+Shift+R 硬刷新页面。

**Codex 修复方向**：`applyTerminalChartAnnotations` 完成后，前端应主动调用 `GET /api/chart-annotations?workspaceId={workspaceId}` 重新拉取标注并合并到 state。详见 `references/annotation-append-rendering-bug.md`。

### Annotation 文字颜色（白底终端）

**终端背景是白色**，annotation 文字必须用深色（黑色 `#1a237e` 或深蓝），不要用白色 `#ffffff` 或亮黄色 `#ffeb3b`——白底上浅色文字不可见。

### Annotation Workspace 匹配问题（多 tab 场景）

用户可能在多个浏览器标签页打开 /comparison，每个 tab 有独立的 workspace。推送标注前**必须**从 `GET /api/comparison/current/context` 获取当前活跃的 workspaceId，而不是从 chart action 响应中取。

**正确流程**：
1. 推 chart action → 拿到 workspaceId
2. **等 chart applied 后**，让用户点"分享给 Agent"
3. `GET /api/comparison/current/context` → 取 `workspace.workspaceId`
4. 用这个 workspaceId 推标注

**错误做法**：直接用 chart action 响应中的 workspaceId 推标注——如果用户在另一个 tab 操作，comparison 页面可能不在这个 workspace 上。

### Annotation Panel 匹配问题（V2.6/V2.7 跨 session 常见阻塞）

```
INVALID_ANNOTATION_PANEL: annotations[0].panelId does not exist in current workspace.
```

这个错误不是 request body 格式问题，而是 comparison 页面当前 workspace 不包含指定的 panelId。已知原因：

1. **Workspace ID 被服务器自动生成**：`POST add_series_to_chart` 时 request body 的 `target.workspace.id`（如 `ws_hermes_xxx`）被服务器**忽略**。API 返回自动生成的 ID 如 `terminal-workspace-xxxxx`。**必须从 POST 响应中提取真实 workspaceId 和 panelIds**，然后在 annotation action 中使用它们：
   ```python
   def deep_get(d, *keys):
       for k in keys:
           if isinstance(d, dict): d = d.get(k)
           else: return None
       return d

   # 从 chart POST 响应提取
   ws_id = (deep_get(resp, "action", "target", "workspace", "id")
            or deep_get(resp, "action", "result", "data", "workspace", "id"))
   panels = (deep_get(resp, "action", "target", "workspace", "panels")
             or deep_get(resp, "action", "result", "data", "workspace", "panels") or [])
   panel_ids = list(set(p.get("id") for p in panels if isinstance(p, dict) and p.get("id")))
   ```
   ⚠️ **关键发现**：面板 ID（如 `panel-fx-dollar`、`panel-a-xxx`）是**被保留的**。你在 payload 中指定的 panel ID 会被正确创建。问题只在于 workspace ID 被重写。使用从响应中提取的 workspaceId + **你原本指定的 panelIds** 即可正确绑定。

2. **`focus: true` 不可靠**：annotation action 的 `focus: true` 不一定使 comparison 页面切换到指定 workspace。页面根据当前活跃 tab 消费 annotation。

3. **Queue 积压 race condition**：如果队列中有其他 pending chart action（来自之前失败的测试），它们会在你的 chart 和 annotation 之间被 FIFO 消费，改变 comparison 页面的 active workspace。

**缓解策略（层层递进）**：
   - **A** — 发 chart 前 flush 队列：post dummy chart → 等 applied → 重复直到 `pendingCount == 1`
   - **B** — chart → annotation 间隔尽量短（ms 级，不要加 time.sleep）
   - **C** — 如果 A+B 仍失败，让用户**刷新 `/comparison` 页面**。即使页面已开启且有数据，刷新会重建轮询状态
   - **D** — 使用内部 API (`http://127.0.0.1:8001/api`) 避免 SSL 断连导致的时序问题
   - **E** — ⚠️ **跨 Agent workspace 干扰**（2026-06-03 发现）：如果 Codex 在 /comparison 上创建了新 workspace（如调试用的 `ws-codex-repro-annotation`），comparison 页面会自动切换到该 workspace。此时 Hermes 的标注会因 `INVALID_ANNOTATION_PANEL` 失败，因为当前 workspace 的 panelIds 是 Codex 的（如 `panel-codex-repro-main`），不是 Hermes 的（如 `panel-btc-gold`）。**诊断方法**：错误响应的 `error.details.availablePanelIds` 会显示当前 workspace 的实际 panelIds。**修复**：重新推送 `add_series_to_chart` 切回正确的 workspace（带 `replaceSelection: true`），等 applied 后再推标注。

### 标注渲染失败（前端 timing bug）

**症状**：API 返回 `applied`，annotation store 里有 9 条 active 记录，但 comparison 页面上看不到任何标注。

**根因**：`EChartsWorkspaceRenderer.jsx` 的 `renderAnnotationGraphics()` 调用 `chart.convertToPixel()` 做坐标转换。如果 chart 数据还没完成 DOM 渲染，`convertToPixel` 返回 NaN → `toPixelPoint()` 返回 null → `buildAnnotationChildren()` 静默跳过所有 annotations。

**验证方法**：
1. 检查 chart 容器的 `data-alpha-ficc-annotation-count` 属性（应该是 visibleAnnotations.length）
2. 如果 > 0 但图上看不到，说明是 convertToPixel timing 问题

**临时绕过**：等图表数据完全加载后再推标注。先推 chart action → 轮询到 applied → 等 2-3 秒 → 再推 annotation action。

**修复方向**（给 Codex）：
1. `renderAnnotationGraphics` 里加 retry：如果 visibleAnnotations.length > 0 但实际渲染 children 为空，延迟 150ms 重试
2. 监听 echarts `finished` 事件后再调用 `renderAnnotationGraphics`
3. 依赖 `datafeedSeriesMap`/`datafeedAllDates` 就绪信号，而非仅 `option` 变化

### workspace 面板不匹配（INVALID_ANNOTATION_PANEL）

**症状**：annotation action 返回 `INVALID_ANNOTATION_PANEL`，error 里显示 `availablePanelIds: ["panel-codex-repro-main"]` 而非目标 panel。

**根因**：Codex 调试时在 comparison 页面创建了新 workspace，页面 active workspace 被切换。annotation action 的 `target.workspaceId` 被忽略，前端用当前 active workspace 解析 panelId。

**修复**：推标注前先通过 `GET /api/comparison/current/context` 确认 active workspace 是目标 workspace。如果不是，先推一个 chart action 切回目标 workspace，等 applied 后再推标注。

### Annotation 渲染时序 Bug (2026-06-03, Codex 修复)

**现象**：标注入库成功（annotation store 里有 active 记录），但图表上看不到。

**根因**：`renderAnnotationGraphics` 在 ECharts 坐标系统就绪前被调用，`toPixelPoint()`/`toPixelX()` 坐标转换全部返回 null，标注被静默跳过。

**前端链路**：
```
setOpenWorkspaceIntent (含 annotations)
  → ChartWorkspace useEffect → normalizeOpenedWorkspace() → dispatch SET_WORKSPACE
    → state.annotations 更新 → visibleAnnotations useMemo → renderAnnotationGraphics
      → buildAnnotationChildren() → toPixelPoint() 坐标转换 ← 此处失败
```

**修复方向**（Codex 实现）：在 `renderAnnotationGraphics` 中检测如果 `visibleAnnotations.length > 0` 但渲染 children 为空时，延迟重试或监听 chart `finished` 事件。

**排查方法**：
1. 检查 annotation store：`GET /api/chart-annotations?actionId=...` 确认 status=active
2. 检查 chart container 的 `data-alpha-ficc-annotation-count` 属性是否 > 0
3. 检查 comparison context 的 workspaceId 是否与标注绑定的 workspaceId 一致

### 通用
- **⚠️ `execute_code` 无法处理含嵌套引号的 Python 脚本**：`execute_code` 工具会对 heredoc 做字符串处理，当脚本中包含 `strip('"')` 或 `strip("'")` 等嵌套引号时，会抛出 `SyntaxError: unterminated string literal`。**解决方法**：使用 `write_file` 写 `/tmp/script.py`，然后 `terminal("python3 /tmp/script.py")`。或使用 `terminal` + `python3 << 'PYEOF' ... PYEOF`（单引号定界符阻止 shell 展开）。见 `references/multi-timeframe-financial-analysis.md`。
- **timeout 时 exit_code 为 0**：Python 脚本正常结束但轮询未完成。脚本设计上 timeout 在 main() 内处理，exit_code 仍为 0（不会 sys.exit(1)）。应检查 summary["verdict"]
- **PMI 价格分项不可用**：终端（nbs:publicrelease）和 akshare 均无制造业 PMI 主要原材料购进价格和出厂价格分项。这些数据来自 NBS 官方发布的分项表，需要外部数据源。不要声称"从终端验证了 PMI 价格剪刀差"——只能说"无法核验"。
- **不要写临时验收脚本**：验收脚本必须在仓库中存在。如果找不到，说明该版本尚未部署，告知用户而非自创。
- **不要改写 HTTP 4xx 为"预期通过"**：脚本自己定义 pass/fail。401 就是失败，如实报告 raw stdout/stderr。
- **返回原始输出**：用户要求原始 stdout/stderr，不要加注释性改写。提供原始摘录 + 简要事实即可。
- **容器内执行**：需要正确环境变量的脚本一律在容器内 docker exec 执行，而非宿主机 shell。
- **SSH 复杂命令外层用 wrapper bash**：`ssh user@host "cmd args; echo RC=$?"` 的嵌套引号容易出错。封装到 `/tmp/run_xxx.sh` 再执行，规避 shell quoting 问题。
- **V5 三段全跑 + V4 回归**：完整闭环验收 = v5_contract → v5_scheduler → v5_digest → v4_regression，任一失败即停止。

### 数据源缺口（中国宏观）
- **DXY（美元指数）**：`yfinance:DX-Y.NYB` 不在 yfinance 白名单中，API 静默接受但返回空数据。使用 `fred:DTWEXBGS`（贸易加权广义美元指数，月度）作为替代。分析人民币汇率时必须拉 DXY 判断被动升值 vs 主动升值的比例。
- **PMI 价格分项不可用**：NBS 公布的制造业 PMI 子指数「主要原材料购进价格」和「出厂价格」在 Alpha-FICC 终端和 akshare 中均不可用。当研究文章引用这些数据时，标记为「无法从终端验证」。可能的替代来源：Wind（万德）终端、东方财富 API、NBS 官方发布。
- **出口结构数据缺失**：终端仅有进出口总额和同比，缺少量价分解和品类/目的地分布。无法仅凭终端数据区分「真实外需修复」和「关税前抢出口」。

## 已知约束

- 完整 Agent 终端接入手册：`/Users/lynch5mo/Work Documents/alpha-ficc/docs/operations/alpha-ficc-agent-terminal-access-handbook.md`（含 V1-V5 API 端点定义、scopes、认证模型）
- SSH 到服务器使用公钥认证（`~/.ssh/id_ed25519`）
- 服务器 `authorized_keys` 有两个 key：`alpha-hermes-tunnel` + GitHub key
- 复杂引用/中文参数用单引号包裹避免 shell 转义问题
- 脚本调用 `server_ssh` 内部使用 `docker exec` 执行服务器侧操作；当 SSH 传递复杂命令失败时，可改用 `server_ssh` 辅助或 `docker exec` 路径
- 长脚本推荐 SCP 到服务器再 SSH 执行，而非 heredoc（避免 shell 转义问题）
- Temp 文件以 `tmp_` 开头，用完后务必通过 SSH 清理

## 支持文件

- `references/historical-cycle-analysis-pattern.md` — 多窗口历史周期分析模式：BTC vs IGV 相关性验证、ETF 性能对比、CoinGecko 量能数据
- `references/annotation-payload-discovery.md` — 2026-05-25 的格式探测记录，包含 probe 结果和错误码映射
- `references/v27-acceptance-test-2026-05-25.md` — V2.7 全链路验收测试记录
- `references/terminal-chart-actions-investigation-2026-06-03.md` — terminal-chart-actions INVALID_TARGET 调查记录：workspace 存在于 annotation store 但不在 workspace store 时的拒绝行为、循环探测纪律
- `references/fred-data-truncation-2026-06-03.md` — FRED BAMLH0A0HYM2 OAS 系列截断至 3 年数据（2026/04 FRED 政策变更），长周期信用利差分析的替代方案
- `references/v4-auth-model.md` — V4 API 认证模型参考（2026-05-26）
- `references/v4-observation-revision-loop.md` — V4 全链路端点参考
- `references/v5-auth-model.md` — V5 Research OS 认证模型、scheduler tick 断言细节、scope 配置影响（2026-05-26）
- `references/three-panel-macro-monitor-logic.md` — 三面板宏观监控布局的设计逻辑（利率曲线→MOVE→多资产波动率的传导链）
- `references/china-equity-five-phase-panel-layout.md` — 中国A股五阶段行情分析面板布局：CSI300+USDCNH/DXY+利差+PMI+贸易。含完整序列ID、标注模板、API调用模板。**用户要求：金融分析出图必须用终端，不要用matplotlib自生成。**
- `references/china-macro-cost-analysis-workflow.md` — 中国宏观成本分析工作流：进口分类→价格信号→成本-价格剪刀差→利润影响。含数据源（Trading Economics可用于进口分类，akshare无此数据）、分析框架、输出格式。
- `references/china-macro-data-sources-and-gaps.md` — 中国宏观数据源清单与已知缺口。包含已验证可用的终端序列、DXY 代理选择（`fred:DTWEXBGS`有效，`yfinance:DX-Y.NYB`不在白名单）、PMI 价格分项不可用的系统性缺口、研究文章交叉验证工作流。
- `references/multi-timeframe-financial-analysis.md` — 多时间框架金融分析方法论。含五阶段归因框架、货币升值的 DXY 分解技术、图表生成工作流、常见分析错误清单（cherry-picked 窗口、遗漏关键变量、末段现象解释整轮行情）。
- `references/annotation-workspace-mismatch-2026-06-03.md` — workspace ID 匹配陷阱 + annotation 渲染时序 bug 详解
- `references/terminal-chart-actions-investigation-2026-06-03.md` — terminal-chart-actions INVALID_TARGET 调查记录：workspace 存在于 annotation store 但不在 workspace store 时的拒绝行为、循环探测纪律
- `scripts/v2-full-acceptance.py` — 可复用的 V2 全链路 7 步测试脚本模板
