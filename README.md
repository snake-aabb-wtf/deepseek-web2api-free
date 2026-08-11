# DeepSeek Chat API Proxy

> 将 DeepSeek Chat (chat.deepseek.com) 的私有 API 转换为 OpenAI / Anthropic 兼容格式。

> **🤖 全 AI 生成声明**: 本项目没有一行人工手写代码。所有的 API 端点设计、协议逆向、PoW 求解、SSE 解析、格式映射、文档编写等等全部由 **DeepSeek v4 Flash 模型** + **Claude Code** 协作完成。

**免责声明**: 本项目仅限学习研究使用。非官方项目，与 DeepSeek 无关。使用需自行承担风险，不保证稳定性。

---

## 功能特性

- **OpenAI 兼容** — `/v1/chat/completions` 与 `/v1/models` 接口，支持 `stream` 模式
- **Anthropic 兼容** — `/v1/messages` 接口，支持 Claude API 格式
- **API Key 鉴权** — `/v1/*` 支持 `Authorization: Bearer` / `x-api-key`，适合公网部署
- **思维链（Reasoning/Thinking）** — 专家模式下自动分离思维链 tokens 并通过 `reasoning_content` 字段输出
- **专家模式（Expert Mode）** — 开启 R1 风格深度推理，响应含 THINK→RESPONSE 双阶段
- **Quick 模式** — V3 风格快速回答，低延迟
- **联网搜索** — 通过 `search_enabled` 参数启用实时搜索增强
- **Function Calling** — 基于 DSML（DeepSeek Markup Language）提示词注入实现工具调用
- **流式筛分** — `StreamSieve` 引擎，逐字符检测 DSML 工具调用标签，从 SSE 流中实时分离正文与工具调用
- **PoW 鉴权** — 自动完成 WASM 工作量证明（DeepSeekHashV1）挑战
- **会话管理** — 自动创建和管理 DeepSeek Chat 会话；可选多轮会话复用
- **多账号池** — 轮询分配、idle/busy/error 状态、健康检查、自动恢复
- **客户端限流** — 滑动窗口，按 API key 和 IP 独立计数；响应头 `X-RateLimit-*`
- **使用量统计** — 基于 tiktoken 估算的 prompt / completion / total tokens
- **管理面板** — 内置 Web 管理界面，支持请求统计、账号池管理（多账号轮询/持久化增删改查/重登录）

---

## 快速开始

### 前置条件

- Python 3.10+
- 可以访问 `chat.deepseek.com` 的网络环境
- 有效的 DeepSeek 账号（免费注册）

### 安装

```bash
# 1. 克隆/下载本项目
git clone https://github.com/snake-aabb-wtf/deepseek-web2api-free.git
cd deepseek-web2api-free

# 2. 安装依赖（Windows 推荐直接用 start.bat 自动创建虚拟环境并安装；手动方式：）
pip install -r requirements.txt
```

### 获取凭证

你需要从浏览器开发者工具中提取你的 DeepSeek 凭证：

1. 用浏览器打开 [chat.deepseek.com](https://chat.deepseek.com) 并登录
2. 按 `F12` 打开开发者工具，切换到 **Network（网络）** 标签
3. 在页面中随便发一条消息
4. 在网络请求列表中点击任意一个请求（如 `chat/completion`）
5. 在请求头中找到以下两个值：

| 凭证 | 位置 | 示例 |
|------|------|------|
| `DEEPSEEK_TOKEN` | `Authorization` 请求头的 Bearer 值 | `eyJhbGciOiJIUzI1NiIs...` |
| `DEEPSEEK_COOKIES` | `Cookie` 请求头的完整值 | `cf_clearance=xxx; session=yyy; ...` |

> **两种使用方式**：① 填入 `.env` 作为池空兜底；② 直接登录 WebUI 在「账号池」页添加（推荐，可增删改 + 一键重登录）。

### 配置

```bash
# 复制环境变量模板
cp .env.example .env
```

编辑 `.env` 文件：

```ini
# 必填：客户端 API Key，用于保护 /v1/* 公网接口
API_KEYS=sk-change-me
ALLOW_UNAUTHENTICATED_API=false

# 必填：WebUI 管理面板密码（未设置默认 admin，公网部署前必须修改）
DEEPSEEK_ADMIN_PASSWORD=change-me

# 可选：DeepSeek 账号凭证（v3.2.0 起为「池空兜底」）
# 不再预加载进账号池参与轮询；仅当面板账号数为 0 时作为只读兜底使用。
# 推荐：直接登录 WebUI 在「账号池」页面添加账号（持久化到 data/accounts.json，可增删改）。
DEEPSEEK_TOKEN=eyJhbGciOiJIUzI1NiIs...
DEEPSEEK_COOKIES=cf_clearance=xxx; session=yyy; ...
# 多账号格式同理（DEEPSEEK_TOKEN_1/COOKIES_1/EMAIL_1，取第一个有效作为兜底）

# 可选：模型路由（默认已启用——Playground 显示快速/专家两种模式）
MODEL_ROUTES={"deepseek-chat":"default","deepseek-reasoner":"expert"}

# 可选：API 中暴露的模型名称（不影响实际使用的模型）
MODEL_NAME=deepseek-chat

# 可选：监听地址/端口（默认 127.0.0.1:8080）
HOST=127.0.0.1
PORT=8080

# 可选：模式控制（auto=尊重客户端 / quick / expert）
MODE=auto
THINKING=auto
SEARCH=auto
```

完整变量说明见 `.env.example` 与 [AGENTS.md](AGENTS.md)。

### 启动

```bash
# 推荐：使用启动脚本 start.bat（Windows）
#   - 自动定位 Python 3.10+，检测/创建虚拟环境（.venv / venv / env）
#   - 校验依赖，不足则自动安装
#   - WebUI 产物缺失时自动 npm 构建（set WEBUI_REBUILD=1 强制重建）
#   - 只结束本项目的旧进程，绝不误杀占用端口的其他服务
#   - 启动前打印访问地址，默认 3 秒后自动打开浏览器（set WEBUI_OPEN=0 跳过）
start.bat

# 手动启动（已在虚拟环境中）：
#   .venv\Scripts\python -m uvicorn server:app --host 127.0.0.1 --port 8080
```

启动后终端会显示访问地址并自动打开浏览器；日志示例：
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8080 (Press CTRL+C to quit)
```

### 验证

```bash
curl http://localhost:8080/health
# → {"status":"ok"}

curl http://localhost:8080/v1/models \
  -H "Authorization: Bearer sk-your-api-key"
# → {"object":"list","data":[
#      {"id":"deepseek-chat",...},
#      {"id":"deepseek-reasoner",...}   # v3.2.0 起 MODEL_ROUTES 默认启用快速/专家两档
#   ]}
```

### 管理面板

项目内置 Web 管理界面（v3.0.0 起为 React SPA），提供请求统计和账号池管理功能：

```
浏览器打开 http://localhost:8080/webui/
```

> start.bat 会自动构建 WebUI（源码在 `webui-new/`，产物 `webui-new/dist/`）；若手动部署，需先在 `webui-new/` 执行 `npm install && npm run build`。

默认密码为 `.env` 中设置的 `DEEPSEEK_ADMIN_PASSWORD`（未设置则为 `admin`）。公网部署前请务必修改默认密码。

账号池支持两类账号：

- **面板账号（推荐）**：在 WebUI 账号池页添加/编辑/删除，持久化到 `data/accounts.json`，参与轮询分配，可一键重登录。
- **env 兜底（v3.2.0+）**：`.env` 中 `DEEPSEEK_TOKEN/COOKIES`（或 `_1` 多账号格式）作为**只读兜底**——不参与常规轮询，仅当面板账号数为 0 时自动启用，保证池空不 503。
- **概览** — 实时请求统计（总量/成功/失败/延迟/运行时长）+ 账号池状态一览
- **Playground** — 在线测试对话（快速/专家两种模型模式，支持推理过程可视化）
- **设置** — 只读查看当前生效的运行时配置

---

## 非交互式账号池配置（代理 / 自动化工具）

> **给 SDK、脚本、curl、CI、代理用**，不经过 WebUI 面板。要点：v3.0.0+ 账号池的**主配置源是 `data/accounts.json` 文件**，`.env` 只提供单账号只读兜底。要跑**多账号轮询**，非交互场景必须写 `data/accounts.json`。

**`data/accounts.json`（v1 明文）完整格式：**

```json
{
  "version": 1,
  "accounts": [
    {"email": "acc-001", "token": "<token>", "cookies": "<cookies>"},
    {"email": "acc-002", "token": "<token>", "cookies": "<cookies>"}
  ]
}
```

- 必填 `token` + `cookies`；可选 `email`/`id`/`created_at`/`updated_at`
- 文件 `chmod 600`、目录 `chmod 700`（含明文 DeepSeek 凭证，泄露=账号被滥用）
- 服务启动时一次性全量加载；改文件后需重启进程
- **加密**：设 `DEEPSEEK_ENCRYPTION_KEY`(Fernet) 后首次启动自动把明文迁移为 v2 加密，并留 `accounts.json.v1.bak`；此时勿再手写明文

**非交互配置步骤：**

```bash
# 1. 写账号池文件（可脚本生成）
cat > project_dir/data/accounts.json <<'JSON'
{"version":1,"accounts":[{"email":"acc-001","token":"<token>","cookies":"<cookies>"}]}
JSON
chmod 600 project_dir/data/accounts.json && chmod 700 project_dir/data

# 2. 配 API 鉴权（非交互必需，否则 /v1/* → 503）
#    API_KEYS=***    （多个逗号分隔）

# 3. 启动
python -m uvicorn server:app --host 127.0.0.1 --port 8080
```

- **单账号兜底**（不写文件）：直接在 `.env` 设 `DEEPSEEK_TOKEN_1`/`DEEPSEEK_COOKIES_1`（或 legacy `DEEPSEEK_TOKEN`/`DEEPSEEK_COOKIES`），池空自动兜底。
- **改存储路径**：`ACCOUNT_STORE_PATH` 环境变量。

---

## API 文档

### `POST /v1/chat/completions`

OpenAI 兼容的聊天补全接口。

#### 请求体

```json
{
  "model": "deepseek-chat",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "stream": false,
  "temperature": 0.7,
  "top_p": 0.95,
  "max_tokens": null,
  "thinking_mode": false,
  "search_enabled": false,
  "tools": null,
  "tool_choice": "auto"
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | `string` | `"deepseek-chat"` | 模型名称（不影响实际模型，仅用于标识） |
| `messages` | `array` | 必填 | 消息列表，支持 `system`/`user`/`assistant`/`tool` 角色 |
| `stream` | `boolean` | `false` | 是否流式输出 |
| `temperature` | `float` | `null` | 采样温度（传递给 DeepSeek 但效果取决于服务端） |
| `top_p` | `float` | `null` | Top-p 采样 |
| `max_tokens` | `int` | `null` | 最大生成 tokens |
| `thinking_mode` | `boolean` | `false` | 开启专家模式深度推理 |
| `search_enabled` | `boolean` | `false` | 开启联网搜索增强 |
| `tools` | `array` | `null` | OpenAI 格式的工具定义 |
| `tool_choice` | `string\|dict` | `null` | 工具选择策略 |

#### 非流式响应（`stream: false`）

```json
{
  "id": "chatcmpl-a1b2c3d4e5f6",
  "object": "chat.completion",
  "created": 1712345678,
  "model": "deepseek-chat",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "你好！有什么可以帮助你的吗？"
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": -1,
    "completion_tokens": -1,
    "total_tokens": -1
  }
}
```

> **注意**: `usage` 中的 tokens 数返回 `-1`，因为 DeepSeek Chat 不暴露 token 计数。这是已知限制。

#### 流式响应（`stream: true`）

标准 OpenAI SSE 格式，每个事件是一行 `data: {...}\n\n`，以 `data: [DONE]\n\n` 结尾：

```
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"你好"},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"！"},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

---

### `POST /v1/messages`

Anthropic Claude API 兼容的聊天补全接口。

#### 请求体

```json
{
  "model": "claude-3-5-sonnet-20241022",
  "max_tokens": 1024,
  "messages": [
    {"role": "user", "content": "Hello!"}
  ],
  "system": "You are a helpful assistant.",
  "stream": false,
  "thinking": {"type": "enabled", "budget_tokens": 16000},
  "tools": [
    {"name": "get_weather", "description": "获取天气", "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}}}
  ]
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | `string` | `"claude-3-5-sonnet-20241022"` | 模型名称（不影响实际模型，仅用于标识） |
| `messages` | `array` | 必填 | 消息列表，支持 `user`/`assistant` 角色 |
| `system` | `string\|array` | `null` | 系统提示词 |
| `stream` | `boolean` | `false` | 是否流式输出 |
| `thinking` | `object` | `null` | `{"type": "enabled"}` 开启思考模式 |
| `tools` | `array` | `null` | Anthropic 格式的工具定义（`name`/`description`/`input_schema`） |
| `max_tokens` | `int` | `null` | 被忽略（DeepSeek 不支持） |
| `metadata` | `object` | `null` | 被忽略 |
| `stop_sequences` | `array` | `null` | 被忽略 |

#### 非流式响应（`stream: false`）

```json
{
  "id": "msg_xxxxxxxxxxxxxxxxxxxxxxxx",
  "type": "message",
  "role": "assistant",
  "content": [
    {"type": "text", "text": "你好！有什么可以帮助你的吗？"}
  ],
  "model": "deepseek-chat",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {"input_tokens": -1, "output_tokens": -1}
}
```

工具调用时：

```json
"content": [
  {"type": "tool_use", "id": "toolu_xxx", "name": "get_weather", "input": {"city": "北京"}}
],
"stop_reason": "tool_use"
```

#### 流式响应（`stream: true`）

Anthropic 原生 SSE 格式，包含 `message_start`、`content_block_start`、`content_block_delta`、`content_block_stop`、`message_delta`、`message_stop` 事件：

```
event: message_start
data: {"type":"message_start","message":{"id":"msg_...","type":"message","role":"assistant","content":[],"model":"deepseek-chat","stop_reason":null,...}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"推理过程..."}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: content_block_start
data: {"type":"content_block_start","index":1,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"回答内容"}}

event: content_block_stop
data: {"type":"content_block_stop","index":1}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"output_tokens":-1}}

event: message_stop
data: {}
```

> **注意**: Anthropic 端点与 OpenAI 端点共享相同的底层 adapter，MODE/THINKING/SEARCH 环境变量同时影响两个端点。

---

## MODE / THINKING / SEARCH 详解

这三个环境变量是独立的控制维度，共同决定每个请求的行为：

| 环境变量 | 可选值 | 默认值 | 说明 |
|----------|--------|--------|------|
| `MODE` | `auto` / `quick` / `expert` | `auto` | 控制 `model_type`：`"default"`(quick) 或 `"expert"` |
| `THINKING` | `auto` / `enabled` / `disabled` | `auto` | 控制 `thinking_enabled`：`true` / `false` |
| `SEARCH` | `auto` / `enabled` / `disabled` | `auto` | 控制 `search_enabled`（联网搜索）：`true` / `false` |

优先级：环境变量 > 请求参数。当环境变量为 `auto` 时，由客户端请求中的对应字段决定行为。

### 组合示例

| MODE | THINKING | SEARCH | 行为 | 典型场景 |
|------|----------|--------|------|----------|
| `auto` | `auto` | `auto` | 由客户端 `thinking_mode` / `search_enabled` 决定 | 完全由客户端灵活控制 |
| `quick` | `disabled` | `auto` | 强制 V3 快速模式，无推理 | 追求低延迟、不需要深度推理 |
| `expert` | `enabled` | `enabled` | 强制 R1 专家模式 + 思维链 + 联网搜索 | 深度推理 + 实时信息 |
| `quick` | `enabled` | `disabled` | 快速模式 + 思考，关闭联网 | 快速响应但附带推理过程 |

### 环境变量与请求参数互斥

```
MODE=auto, THINKING=auto, SEARCH=auto, 请求 thinking_mode=true  →  quick + 有 reasoning_content
MODE=expert, THINKING=disabled, 请求 thinking_mode=true  →  expert + 无 reasoning_content + 由客户端决定搜索
MODE=quick, THINKING=enabled, SEARCH=disabled  →  quick + 有 reasoning_content + 无联网搜索
```

---

## 思维链（Reasoning / Thinking）

当 `thinking_mode=true`（即 expert 模式）时，流式和非流式响应中推理 tokens 通过 `reasoning_content` 字段暴露。

### 流式响应中的推理

专家模式下 SSE 流先输出推理 tokens，再输出正式回答：

```
data: {"id":"...","choices":[{"index":0,"delta":{"reasoning_content":""},"finish_reason":null}]}

data: {"id":"...","choices":[{"index":0,"delta":{"reasoning_content":"首先"},"finish_reason":null}]}

data: {"id":"...","choices":[{"index":0,"delta":{"reasoning_content":"需要"},"finish_reason":null}]}
...
data: {"id":"...","choices":[{"index":0,"delta":{"content":"您好"},"finish_reason":null}]}

data: {"id":"...","choices":[{"index":0,"delta":{"content":"！"},"finish_reason":null}]}
...
data: {"id":"...","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}
data: [DONE]
```

客户端如 NextChat、Open WebUI 等支持识别 `reasoning_content` 字段并展示思维链。如果客户端不支持，可以设置 `THINKING=disabled` 强制不输出推理过程。

---

## Function Calling（工具调用）

本项目通过 **DSML（DeepSeek Markup Language）** 提示词注入实现工具调用，利用 DeepSeek Chat 对 XML 标签的理解能力。

### 工作原理

1. `tools` 参数中的函数定义被转换为 DSML 格式的系统提示词
2. 提示词指导模型以指定 XML 格式响应工具调用
3. `StreamSieve` 引擎实时从 SSE 流中检测 DSML 标签
4. 匹配的工具调用被转换为 OpenAI 格式的 `tool_calls` 返回

### 使用示例

```python
import openai

client = openai.Client(base_url="http://localhost:8080/v1", api_key="sk-your-api-key")

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "北京的天气怎么样？"}],
    tools=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市的天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称"}
                },
                "required": ["city"]
            }
        }
    }],
    tool_choice="auto",
)
```

### DSML 格式

DSML 使用类似 XML 的标签结构。当模型决定调用工具时，响应格式为：

```xml
<|DSML|tool_calls>
  <|DSML|invoke name="get_weather">
    <|DSML|parameter name="city"><![CDATA[北京]]></|DSML|parameter>
  </|DSML|invoke>
</|DSML|tool_calls>
```

`StreamSieve` 引擎在收到第一个 `<` 标签字符时就转至 "capture" 模式，积累全部 DSML 内容后一起解析。避免了模型"先输出正文再输工具调用"导致的文本污染。

---

## 多轮会话（v2.2.0）

DeepSeek Chat 协议本身支持 `parent_message_id` 串接同 `chat_session_id` 内的消息。v2.2.0 利用此能力为兼容端点提供轻量级多轮支持：

- **Anthropic 客户端**：通过请求体中的 `metadata.user_id` 字段作为会话粘性 key
- **OpenAI 客户端**：通过自定义 HTTP 头 `X-Conversation-Id` 作为会话 key
- **Fallback**：当两者都未设置时，对第一条 user 消息做 SHA-256 摘要作为 key

会话缓存默认 TTL 为 600 秒（`SESSION_CACHE_TTL`），过期后自动开始新会话。设置 `SESSION_CACHE_TTL=0` 完全禁用多轮行为。

```bash
# OpenAI 多轮示例（带 X-Conversation-Id 头）
curl http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer $API_KEY" \
  -H "X-Conversation-Id: user-42-session-7" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[
    {"role":"user","content":"我叫小明"},
    {"role":"user","content":"我叫什么？"}
  ]}'
# 第二条消息会看到第一条的上下文。
```

> **注意**：多轮会话依赖 DeepSeek 上游接受 `parent_message_id`；如果上游对历史消息有长度限制，长会话可能中途被截断。当前的 `_msg_counters` 在 adapter 内是会话级单调递增的，所以即使缓存未命中也不会破坏既有行为。

---

## 模型路由（v2.2.0）

通过 `MODEL_ROUTES` 环境变量，客户端可以发送不同的 `model` 字段让代理自动选择 `model_type`（quick/expert）和默认的 thinking/search 设置：

```bash
# 简单形式 — 字符串值
MODEL_ROUTES={"deepseek-chat":"default","deepseek-reasoner":"expert"}

# 完整形式 — dict 值
MODEL_ROUTES={"deepseek-reasoner":{"model_type":"expert","thinking":"enabled","search":"disabled"}}
```

未命中的 model 名按既有 `MODE` / `THINKING` / `SEARCH` env 变量处理。`/v1/models` 端点会返回 `MODEL_ROUTES` 中声明的所有 model 名。

---

## 客户端限流（v2.2.0）

v2.2.0 内置了基于滑动窗口的双维度限流器：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `ENABLE_RATE_LIMIT` | `true` | 总开关；设为 `false` 完全禁用 |
| `CLIENT_RPM_PER_KEY` | `60` | 每 API key 每分钟请求数（0 = 不限） |
| `CLIENT_RPM_PER_IP` | `120` | 每 IP 每分钟请求数（0 = 不限） |

每个请求需要 **同时** 通过 key 和 IP 两个维度的检查。命中限流时返回 `429 Too Many Requests`，响应头含：

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 47
Retry-After: 47
```

> 限流状态保存在进程内；多 worker 部署（gunicorn -w N）实际限制为 N × 配置值。

---

## 使用量统计（v2.2.0）

`usage` 字段从 v2.1 的硬编码 `-1` 升级为真实 token 数。优先使用 `tiktoken` 的 `cl100k_base` 编码（与 DeepSeek 兼容），未安装时回退到字符启发式（CJK 1 token/字，ASCII 约 1 token/4 字符）。

服务端面板的 `/admin/api/stats` 现在还返回：

| 字段 | 说明 |
|------|------|
| `success_rate` | 0.0..1.0 |
| `p50_latency_ms` / `p95_latency_ms` / `p99_latency_ms` | 最近 1024 次请求的延迟百分位 |
| `latency_window_size` | 当前环形缓冲已用大小 |
| `total_prompt_tokens` / `total_completion_tokens` | 整个进程生命周期的累计 tokens |

---

## 安全建议（生产部署 checklist）

部署到公网前请按顺序检查：

1. **修改默认 admin 密码**：`.env` 中 `DEEPSEEK_ADMIN_PASSWORD=…`（16+ 字符随机）。默认密码 + 公网绑定时服务**会拒绝启动**。
2. **设置 Fernet 加密 key**：`DEEPSEEK_ENCRYPTION_KEY=…`，生成方式 `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`。已有明文 `data/accounts.json` 会在首次启动时自动迁移，原始文件保留为 `accounts.json.v1.bak`。
3. **设置 API key**：`.env` 中 `API_KEYS=sk-real-key-1,sk-real-key-2`（多个用逗号分隔）。`ALLOW_UNAUTHENTICATED_API` 保持 `false`。
4. **配置 CORS 白名单**：`ALLOWED_ORIGINS=https://app.example.com`，而不是依赖默认同源策略。
5. **如果用反向代理**（nginx、Caddy、Traefik）：设置 `TRUSTED_PROXIES=10.0.0.0/8`（你的代理网段）让 admin 限流能正确识别客户端 IP。
6. **绑定地址**：默认 `127.0.0.1`。如果要走反向代理，保持 loopback；如果直连公网，设置 `HOST=0.0.0.0` 并确保前置有 TLS + WAF。
7. **使用 HTTPS**：限流响应头里包含 token 计数和 IP；admin 端点需要 HTTPS 保护。强烈建议配合 Cloudflare / Caddy 等前端使用。
8. **定期轮换**：token / cookie 90 天左右主动续期；`accounts.json` 是敏感文件，确保所在分区权限 `0o700` / NTFS ACL 限制。
9. **限流**：保留默认 `CLIENT_RPM_PER_KEY=60`、`CLIENT_RPM_PER_IP=120`，按你的实际流量调整。
10. **监控**：`GET /health` 适合做存活探针；`/admin/api/stats` 适合做业务指标抓取。

---

## 架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│                          管理面板                                │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐ │
│  │ 前端 SPA (webui/)    │  │ Admin API (admin.py)             │ │
│  │ · 概览面板           │◄─┤ · 密码认证 / 统计 / 账号管理     │ │
│  │ · 账号池管理         │  │ · 重登录触发                     │ │
│  └──────────────────────┘  └───────┬──────────────────────────┘ │
└────────────────────────────────────┼────────────────────────────┘
                                     │
┌──────────────┐     OpenAI 格式      ┌────────▼─────────────────┐
│  客户端应用   │ ◄───── SSE ────────► │   FastAPI Server          │
│ (NextChat,    │                      │   (server.py)             │
│  OpenWebUI,   │                      │                           │
│  custom)      │                      │  ┌─────────────────────┐  │
└──────────────┘                      │  │  AccountPool         │  │
                                      │  │  (account_pool.py)   │  │
                                      │  │  · 多账号轮询选择    │  │
                                      │  │  · 状态追踪          │  │
                                      │  │  · 健康检查          │  │
                                      │  └────────┬────────────┘  │
                                      │           │                │
                                      │  ┌────────▼────────────┐  │
                                      │  │  ChatAdapter         │  │
                                      │  │  (adapter.py)        │  │
                                      │  │  - PoW solving       │  │
                                      │  │  - Session mgmt      │  │
                                      │  │  - SSE parsing       │  │
                                      │  │  - Fragment stm      │  │
                                      │  └────────┬────────────┘  │
                                      │           │                │
                                      │  ┌────────▼────────────┐  │
                                      │  │ StreamSieve          │  │
                                      │  │ (tool_sieve.py)      │  │
                                      │  │ - DSML detection     │  │
                                      │  │ - Real-time sep      │  │
                                      │  └──────────────────────┘  │
                                      │                           │
                                      │  ┌──────────────────────┐  │
                                      │  │ DSML Parser          │  │
                                      │  │ (tool_dsml.py)       │  │
                                      │  │ - XML parsing        │  │
                                      │  │ - Format conv        │  │
                                      │  └──────────────────────┘  │
                                      └──────────┬────────────────┘
                                                 │
                                      DeepSeek 原生协议
                                      (PoW + SSE)
                                                 │
                                      ┌──────────▼────────────┐
                                      │  chat.deepseek.com    │
                                      │  (DeepSeek Chat API)  │
                                      └───────────────────────┘
```

### 核心组件

| 文件 | 职责 |
|------|------|
| `server.py` | FastAPI 服务器，路由分发，MODE/THINKING 控制，OpenAI SSE 格式化 |
| `adapter.py` | DeepSeek 协议适配器 — PoW 挑战求解，会话创建/管理，原生 SSE 解析，fragment 状态机 |
| `anthropic_format.py` | Anthropic `/v1/messages` 格式转换 — 请求解析、响应组装、SSE 生成 |
| `tool_sieve.py` | StreamSieve 流式筛分引擎 — 逐字符检测 DSML 工具调用标签，实时分离正文与工具调用 |
| `tool_dsml.py` | DSML 解析器/生成器 — XML 格式的 DSML ↔ OpenAI tool_calls 双向转换 |
| `account_pool.py` | 多账号管理 — CRUD、状态追踪（idle/busy/error）、轮询分配、健康检查 |
| `admin.py` | 管理后台 API — 密码认证、请求统计、账号池增删查改、重登录触发 |
| `webui/` | 管理面板前端 — 纯静态 SPA，零 build 依赖 |
| `sha3_wasm_bg.wasm` | WASM 二进制，用于 DeepSeekHashV1 工作量证明求解 |

### 请求生命周期

1. **客户端请求** → `/v1/chat/completions` 收到 OpenAI 格式请求
2. **模式解析** → `server.py` 根据环境变量和请求参数确定 `model_type` 和 `thinking_enabled`
3. **DSML 注入** → 如有 `tools`，`build_dsml_tool_prompt()` 生成 DSML 格式系统提示词
4. **PoW 求解** → `adapter.py` 请求并求解 DeepSeekHashV1 挑战
5. **会话创建** → 创建新的 DeepSeek Chat 会话（可选复用）
6. **请求发送** → 以原生格式发送到 `/api/v0/chat/completion`
7. **响应处理**:
   - 非流式：解析 SSE 收集全部内容 → 检测工具调用 → 返回 OpenAI 格式
   - 流式：逐 token 转发 → StreamSieve 实时筛分 → 格式化 OpenAI SSE

---

## 文件结构

```
├── server.py            # FastAPI 服务器主入口
├── adapter.py           # DeepSeek 协议适配器 (PoW, 会话, SSE)
├── anthropic_format.py  # Anthropic /v1/messages 格式转换
├── tool_sieve.py        # StreamSieve 流式工具调用检测引擎
├── tool_dsml.py         # DSML 解析器/生成器
├── account_pool.py      # 多账号池管理 (轮询、状态追踪、健康检查)
├── admin.py             # 管理后台 API 端点
├── webui/               # 管理面板前端 (纯静态 SPA)
│   ├── index.html
│   ├── app.js
│   └── style.css
├── sha3_wasm_bg.wasm    # WASM PoW 求解器
├── requirements.txt     # Python 依赖
├── .env.example         # 环境变量模板
├── .env                 # 你的实际配置（已 .gitignore）
├── start.bat            # Windows 启动脚本
├── AGENTS.md            # AI Agent 参考文档
└── README.md            # 本文件
```

---

## 常见问题

### Q: 启动后请求返回 502 Bad Gateway

原因通常是凭证失效或网络问题：

1. 检查 `.env` 中的 `DEEPSEEK_TOKEN` 和 `DEEPSEEK_COOKIES` 是否仍然有效（登录 chat.deepseek.com 重新提取）
2. 检查能否访问 `chat.deepseek.com`（可能需要代理）
3. 检查控制台日志中的具体错误信息

### Q: 流式输出中只有 reasoning_content 没有 content

在 `thinking_mode=true`（专家模式）下，模型会先输出完整的推理过程再输出回答。如果你看到只有推理没有内容：

1. 等待模型完成推理（响应尚未结束）
2. 如果真是 bug：确认服务端版本，检查 `finish_reason` 是否正常输出。已知旧版本可能缺少 `finish_reason: "stop"` 帧

### Q: 如何关闭思维链/推理展示？

设置环境变量 `THINKING=disabled`，即使请求中 `thinking_mode=true` 也不会输出 `reasoning_content`。

### Q: 一直转圈 / 响应极慢

- 专家模式（`thinking_mode=true`）本身就更慢，模型在做完整推理
- PoW 求解在低性能机器上可能需要数秒
- 检查网络到 `chat.deepseek.com` 的延迟

### Q: Windows 下 curl 请求中文返回 422

Windows bash curl 默认编码为 GBK，发送 JSON 时中文字符可能被错误编码。解决方式：

```bash
# 方式一：将请求体写入 JSON 文件
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d @body.json

# 方式二：用 PowerShell（推荐）
Invoke-RestMethod -Uri http://localhost:8080/v1/chat/completions `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"model":"deepseek-chat","messages":[{"role":"user","content":"你好"}],"stream":true}'
```

### Q: `.env` 修改后没有生效

需要重启服务器进程。FastAPI 的 reload 模式不会重新加载环境变量：

```bash
# 先杀掉旧进程
taskkill /F /IM python.exe
# 再重新启动
python -m uvicorn server:app --host 0.0.0.0 --port 8080
```

### Q: 浏览器插件（如 YouTube 字幕翻译）请求失败，日志显示 405 Method Not Allowed

某些 Chrome 插件在使用 OpenAI 兼容接口前会先发送 `OPTIONS` 预检请求（CORS preflight）来检查服务器是否允许跨域访问。如果服务端未处理 `OPTIONS` 请求，会返回 `405 Method Not Allowed`，导致插件无法正常使用。

**解决方法：** 本项目已内置 CORS 中间件（`CORSMiddleware`），默认允许所有来源、方法和请求头。如果仍遇到跨域问题，请确认版本已包含 `server.py` 中的 CORS 配置。

### Q: 支持多轮对话吗？

不支持。每次请求都是独立的，服务器会创建新的 DeepSeek Chat 会话。多轮会话支持需要在应用层面（如 NextChat）维护上下文。

### Q: 如何查看 PoW 求解过程和调试信息？

适配器使用 `httpx` 发送请求，设置日志级别可查看详细请求/响应：

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Q: Token/凭证多久过期？

DeepSeek 的 Token 有效期不明确。如果遇到 `401` 或 `403` 响应，重新登录 chat.deepseek.com 并更新 `.env` 中的凭证。

---

## 环境变量参考

### 核心配置

| 变量 | 默认值 | 必填 | 说明 |
|------|--------|------|------|
| `HOST` | `127.0.0.1` | 否 | 监听地址。`0.0.0.0` 配合默认 admin 密码时拒绝启动 |
| `PORT` | `8080` | 否 | 服务器监听端口 |
| `API_KEYS` | `""` | 公网部署必填 | 客户端访问 `/v1/*` 的 API Key，支持逗号分隔多个 key |
| `DEEPSEEK_API_KEY` | `""` | 否 | 单个客户端 API Key 别名 |
| `ALLOW_UNAUTHENTICATED_API` | `false` | 否 | 是否允许 `/v1/*` 无鉴权访问；公网部署不要开启 |
| `ALLOW_INSECURE_PUBLIC_DEFAULTS` | `false` | 否 | 显式确认在公网上使用默认密码（不建议） |

### DeepSeek 账号

| 变量 | 默认值 | 必填 | 说明 |
|------|--------|------|------|
| `DEEPSEEK_TOKEN` | `""` | 有 DeepSeek 账号时必填 | DeepSeek API 的 Bearer Token（单账号兼容格式） |
| `DEEPSEEK_COOKIES` | `""` | 有 DeepSeek 账号时必填 | DeepSeek 的 Cookie 值（单账号兼容格式） |
| `DEEPSEEK_TOKEN_N` | `""` | 否 | 第 N 个 DeepSeek 账号 Token，例如 `DEEPSEEK_TOKEN_1` |
| `DEEPSEEK_COOKIES_N` | `""` | 否 | 第 N 个 DeepSeek 账号 Cookies |
| `DEEPSEEK_EMAIL_N` | `"env-N"` | 否 | 第 N 个账号的备注/标识 |
| `ACCOUNT_STORE_PATH` | `data/accounts.json` | 否 | 面板持久化账号保存路径 |

### 模型行为

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MODEL_NAME` | `"deepseek-chat"` | `/v1/models` 默认显示的模型名（`MODEL_ROUTES` 存在时显示路由表） |
| `MODE` | `"auto"` | `auto` / `quick` / `expert` |
| `THINKING` | `"auto"` | `auto` / `enabled` / `disabled` |
| `SEARCH` | `"auto"` | `auto` / `enabled` / `disabled` |
| `MODEL_ROUTES` | `""` | JSON 路由表，按 `model` 字段切换 `model_type`/thinking/search |

### 管理面板

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_ADMIN_PASSWORD` | `"admin"` | 管理面板登录密码（公网部署必须修改） |

### 限流 & 会话

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ENABLE_RATE_LIMIT` | `true` | 客户端限流总开关 |
| `CLIENT_RPM_PER_KEY` | `60` | 每 API key 每分钟请求数 |
| `CLIENT_RPM_PER_IP` | `120` | 每 IP 每分钟请求数 |
| `SESSION_CACHE_TTL` | `600` | 多轮会话缓存 TTL（秒），0 = 禁用多轮 |

### 安全 & 加密

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ALLOWED_ORIGINS` | `""` | CORS 允许的 origin 列表（逗号分隔），空 = 同源 |
| `ALLOW_CORS_CREDENTIALS` | `false` | 是否允许带 credentials 的跨域（需配合 `ALLOWED_ORIGINS`） |
| `TRUSTED_PROXIES` | `""` | 信任的代理 IP/CIDR（设置后 `X-Forwarded-For` 才会被采纳） |
| `DEEPSEEK_ENCRYPTION_KEY` | `""` | Fernet key；设置后 `data/accounts.json` 中的 token/cookies 自动加密 |

### 日志 & 反检测

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR |
| `LOG_FORMAT` | `json` | `json`（生产）或 `text`（开发） |
| `DEEPSEEK_IMPERSONATE` | `chrome131` | curl_cffi TLS 指纹 profile |
| `DEEPSEEK_JITTER_SECS` | `0.0` | 调用间随机抖动（秒） |
| `DSML_MAX_BUFFER_BYTES` | `1048576` | StreamSieve 捕获缓冲上限 |
| `DISABLE_AUTO_RECOVER` | `false` | 设为 true 禁用账号自动恢复 |

### 反检测 — 每个账号的代理

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_PROXY` / `DEEPSEEK_PROXY_N` | 单个 / 第 N 个账号的上游代理 URL |
| `DEEPSEEK_EMAIL` | 旧版单账号格式的邮箱备注 |

---

## 依赖

| 包 | 最低版本 | 用途 |
|----|----------|------|
| `fastapi` | ≥0.100.0 | Web 框架 |
| `uvicorn` | ≥0.20.0 | ASGI 服务器 |
| `httpx` | ≥0.24.0 | HTTP 客户端（用于调用 DeepSeek API） |
| `wasmtime` | ≥14.0.0 | WASM 运行时（PoW 求解） |
| `python-dotenv` | ≥1.0.0 | `.env` 文件加载 |

---

## 许可

本项目使用 **Unlicense** 协议正式发布到公有领域（public domain）。

```
This is free and unencumbered software released into the public domain.
```

你可以自由地复制、修改、发布、使用、编译、出售或分发本软件，无论用于商业或非商业目的，无论以任何形式。

**不提供任何保证**，不保证服务的可用性、准确性、稳定性。使用本项目所产生的任何后果由使用者自行承担。

---

## 致谢

- [DeepSeek](https://deepseek.com) — 优秀的 AI 模型与平台
- OpenAI — API 标准格式参考
- [wasmtime-py](https://github.com/bytecodealliance/wasmtime-py) — WASM 运行时
- [@minhmc2007](https://github.com/minhmc2007) — 贡献多轮会话复用修复（PR #10，v3.3.0）
