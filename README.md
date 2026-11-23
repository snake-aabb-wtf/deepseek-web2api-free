# DeepSeek Chat API Proxy

**v4.2.0** 新增英文管理界面。登录后可在顶栏切换中文或英文，浏览器会记住选择。[发布与升级说明](docs/release-notes/v4.2.0.md)

> 将 DeepSeek Chat (chat.deepseek.com) 的私有 API 转换为 OpenAI / Anthropic 兼容格式。

> **🤖 全 AI 生成声明**: 本项目没有一行人工手写代码。所有的 API 端点设计、协议逆向、PoW 求解、SSE 解析、格式映射、文档编写等等全部由 **DeepSeek v4 Flash 模型** + **Claude Code** 协作完成。

**免责声明**: 本项目仅限学习研究使用。非官方项目，与 DeepSeek 无关。使用需自行承担风险，不保证稳定性。

---

## 功能特性

- **OpenAI 兼容** — `/v1/chat/completions` 与 `/v1/models` 接口，支持 `stream` 模式
- **Responses API** — Python 同步/异步与 JavaScript SDK 验收；文本/图片、具名 SSE、多函数调用与 `previous_response_id` 快照续聊；支持范围与示例见 [Responses 文档](docs/responses-api.md)
- **图片输入** — 两种协议均支持 JPEG / PNG / WebP、base64 / data URL / 公网 HTTP(S) URL，流式与非流式共用上传处理
- **Anthropic 兼容** — `/v1/messages` 接口，支持 Claude API 格式
- **API Key 鉴权** — `/v1/*` 支持 `Authorization: Bearer` / `x-api-key`，适合公网部署
- **思维链（Reasoning/Thinking）** — 开启 `thinking_mode` 后自动分离思维链 tokens 并通过 `reasoning_content` 字段输出
- **思考模式** — DeepSeek 已把「快速模式 / 专家模式」合并为同一个模型（见下方说明），原专家体验现由 `thinking_enabled` 提供，响应含 THINK→RESPONSE 双阶段
- **低延迟直答** — 关闭思考即直接回答，无推理链开销
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
| Token | `Authorization` 请求头 `Bearer` 后的值 | 从请求头复制 |
| Cookies | `Cookie` 请求头的完整值 | 从请求头复制 |

> 将凭证添加到 WebUI「账号池」，或写入 `data/accounts.json`。账号凭证不再从 `.env` 读取。

### 配置

```bash
# 复制环境变量模板
cp .env.example .env
```

编辑 `.env` 文件：

```ini
# 客户端 API Key 在 WebUI「设置」页创建和撤销
# 完整 Key 仅在创建时显示；服务端仅保存哈希
ALLOW_UNAUTHENTICATED_API=false

# 必填：WebUI 管理面板密码（未设置默认 admin，公网部署前必须修改）
DEEPSEEK_ADMIN_PASSWORD=change-me

# DeepSeek 账号只通过 WebUI「账号池」或 data/accounts.json 配置。

# 可选：API 中暴露的模型名称。本代理只服务一个模型，
# 「思考 / 不思考」由下面的 THINKING 决定，不是两个模型。
MODEL_NAME=deepseek-chat

# 可选（高级）：模型路由覆盖。默认不配置——不配置时 /v1/models 只列出 MODEL_NAME，
# 老的 model 名（deepseek-reasoner 等）作为别名照常接受。
# MODEL_ROUTES={"my-model":"thinking"}

# 可选：监听地址/端口（默认 127.0.0.1:8080）
HOST=127.0.0.1
PORT=8080

# 可选：能力开关（auto=尊重客户端 / enabled / disabled）
THINKING=auto
SEARCH=auto

# 已废弃：仅兼容旧配置，expert ≡ THINKING=enabled，quick ≡ THINKING=disabled
# MODE=auto
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
#      {"id":"deepseek-chat",...}   # 只有一个模型；开启思考请设 THINKING=enabled
#   ]}
```

### 管理面板

项目内置 Web 管理界面（v3.0.0 起为 React SPA），提供请求统计和账号池管理功能：

```
浏览器打开 http://localhost:8080/webui/
```

> start.bat 会自动构建 WebUI（源码在 `webui-new/`，产物 `webui-new/dist/`）；若手动部署，需先在 `webui-new/` 执行 `npm install && npm run build`。

默认密码为 `.env` 中设置的 `DEEPSEEK_ADMIN_PASSWORD`（未设置则为 `admin`）。公网部署前请务必修改默认密码。

账号只从 `data/accounts.json` 加载。WebUI 账号池中的增删改操作会写入该文件；也可以直接维护该 JSON 文件。

WebUI 其他功能包括：

- **概览** — 实时请求统计（总量/成功/失败/延迟/运行时长）+ 账号池状态一览
- **Playground** — 在线测试对话（单个模型 + 「思考模式」/「联网搜索」两个开关，支持推理过程可视化）
- **设置** — 只读查看当前生效的运行时配置

---

## 非交互式账号池配置（代理 / 自动化工具）

> **给 SDK、脚本、curl、CI、代理用**，不经过 WebUI 面板。账号凭证统一存储在 `data/accounts.json`；`.env` 不读取账号凭证。非交互场景直接维护该文件即可。

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
#    首次启动后登录 WebUI，在「设置」页创建 API Key

# 3. 启动
python -m uvicorn server:app --host 127.0.0.1 --port 8080
```

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
| `model` | `string` | `"deepseek-chat"` | 本代理只有一个模型，此字段不影响上游模型；老名字（`deepseek-reasoner` 等）作为别名照常接受。是否思考看 `thinking_mode` 或服务端 `THINKING` |
| `messages` | `array` | 必填 | 消息列表，支持 `system`/`user`/`assistant`/`tool` 角色 |
| `stream` | `boolean` | `false` | 是否流式输出 |
| `temperature` | `float` | `null` | 兼容字段；当前忽略，不转发上游 |
| `top_p` | `float` | `null` | 兼容字段；当前忽略，不转发上游 |
| `max_tokens` | `int` | `null` | 兼容字段；当前忽略，不截断输出 |
| `thinking_mode` | `boolean` | `false` | 开启深度推理（上游 `thinking_enabled`，即原「专家模式」） |
| `search_enabled` | `boolean` | `false` | 开启联网搜索增强 |
| `user` | `string` | `null` | 多轮会话标识（与 `X-Conversation-Id` 二选一，见「多轮对话」） |
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
    "prompt_tokens": 10,
    "completion_tokens": 15,
    "total_tokens": 25
  }
}
```

> **注意**：以上数值仅展示响应结构。OpenAI 非流式 usage 按拼接后的文字 prompt 与可见正文在本地估算，不是上游计费值，也不包含准确的视觉 token。流式块不附带 usage；Anthropic usage 仍返回 `-1`。

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

### `/v1/responses`

支持创建响应，以及按 ID 检索和删除已存储响应。兼容 Codex CLI 的缓存、客户端元数据和推理提示参数；已验证关闭扩展工具后的普通函数回合。标准 SDK 示例、Codex 配置和能力边界，见 [Responses 文档](docs/responses-api.md)。

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

## THINKING / SEARCH 详解（含已废弃的 MODE）

> **v3.3.8 起：DeepSeek 已合并「快速模式 / 专家模式」，本项目也只服务一个模型。**
> 网页端 `client/settings?scope=model` 现在返回
> `{"model_type":"default","enabled":true,"switchable":true}`、
> `{"model_type":"expert","enabled":false,"switchable":false}`、
> `{"model_type":"vision","enabled":false,"switchable":false}`，
> 且上游会把请求体里的 `model_type` 一律改写回 `"default"`（可在 `event: ready` 帧看到）。
> 也就是说**只有一个对话模型**，原来的「专家体验」完全由 `thinking_enabled` 提供。
> 实测 `model_type=default` 与 `expert` 在同一 prompt 下输出逐字相同、时延无差异、工具调用表现一致。

因此现在的两个真正开关是：

| 环境变量 | 可选值 | 默认值 | 说明 |
|----------|--------|--------|------|
| `THINKING` | `auto` / `enabled` / `disabled` | `auto` | 控制 `thinking_enabled`：`true` / `false`，即原「专家模式」 |
| `SEARCH` | `auto` / `enabled` / `disabled` | `auto` | 控制 `search_enabled`（联网搜索）：`true` / `false` |
| `MODE`（已废弃） | `auto` / `quick` / `expert` | `auto` | **仅为兼容旧配置保留**：`expert` ≡ `THINKING=enabled`，`quick` ≡ `THINKING=disabled`，`auto` 不介入。新配置请直接用 `THINKING` |

`model_type` 仍然会随请求发送（保持与浏览器一致的请求形态），但它是**协议字段**而非能力选择：默认值 `"default"`，只在 `MODEL_ROUTES` 的字典形式里显式指定时才改变（留给上游将来重新放开 `vision` 之类的场景）。

优先级：环境变量 > 请求参数。当环境变量为 `auto` 时，由客户端请求中的对应字段决定行为。

### 组合示例

| THINKING | SEARCH | 行为 | 典型场景 |
|----------|--------|------|----------|
| `auto` | `auto` | 由客户端 `thinking_mode` / `search_enabled` 决定 | 完全由客户端灵活控制 |
| `disabled` | `auto` | 强制关闭思考，直接作答 | 追求低延迟、不需要深度推理 |
| `enabled` | `enabled` | 强制思维链 + 联网搜索 | 深度推理 + 实时信息 |
| `enabled` | `disabled` | 思维链但关闭联网 | 快速响应但附带推理过程 |

### 环境变量与请求参数互斥

```
THINKING=auto,    SEARCH=auto, 请求 thinking_mode=true  →  有 reasoning_content，搜索由客户端决定
THINKING=disabled,              请求 thinking_mode=true  →  无 reasoning_content（服务端强制关闭）
THINKING=enabled, SEARCH=disabled                        →  有 reasoning_content + 无联网搜索
MODE=expert（旧写法）                                    →  等价于 THINKING=enabled
```

---

## 思维链（Reasoning / Thinking）

当 `thinking_mode=true`（或 `THINKING=enabled`）时，流式和非流式响应中推理 tokens 通过 `reasoning_content` 字段暴露。

### 流式响应中的推理

开启思考后，SSE 流先输出推理 tokens，再输出正式回答：

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
- **OpenAI 客户端**：通过自定义 HTTP 头 `X-Conversation-Id` 或顶层 `user` 字段作为会话 key
- **隔离与账号绑定**：缓存同时绑定调用方和创建会话的 DeepSeek 账号；同一上游 session 不会跨账号提交。
- **无显式标识时**：不复用会话。不会再根据第一条消息推断 key，以避免不同用户因首句相同而串话。

聊天补全和 Anthropic 的会话缓存默认 TTL 为 1800 秒（`SESSION_CACHE_TTL`），过期后自动开始新会话。设置 `SESSION_CACHE_TTL=0` 只禁用这两种接口的会话缓存复用；客户端仍可重发完整历史来重建上下文。Responses 的 `previous_response_id` 使用独立的有界内存状态，不受此设置控制。

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

> **注意**：多轮会话依赖 DeepSeek 上游接受 `parent_message_id`；如果上游对历史消息有长度限制，长会话可能中途被截断。账号繁忙或不可用时，代理会安全地改用新会话，而不是用其他账号继续旧会话。

---

## 模型路由（v2.2.0；v3.3.8 起为可选的高级覆盖）

**默认不配置。** 本代理只服务一个模型：`/v1/models` 只列出 `MODEL_NAME`（默认 `deepseek-chat`），「思考 / 不思考」由 `THINKING`（或请求里的 `thinking_mode`）决定——**不是两个模型**。由于上游已合并快速/专家模式，model 名也不可能选出不同的上游模型。

写死老名字的客户端（`deepseek-reasoner` 等）不会 404：这些名字经 `model_router.LEGACY_MODEL_ALIASES` 归一到 `deepseek-chat`，照常服务，但**不改变行为**（旧版它们等于「开思考」，现在要思考请设 `THINKING=enabled`）。

确实需要按 model 名分流时才配置 `MODEL_ROUTES`；配置后 `/v1/models` 会改为列出它的键：

```bash
# 简单形式 — 字符串值（能力预设）
#   "default"  → 关闭思考（直答）
#   "thinking" → 开启思考（原「专家体验」）
#   "expert"   → thinking 的旧别名，兼容 3.3.8 之前的配置
#   "quick"    → default 的旧别名
MODEL_ROUTES={"my-model":"thinking"}

# 完整形式 — dict 值（可显式指定 model_type 协议字段与 search）
MODEL_ROUTES={"my-model":{"thinking":"enabled","search":"disabled"}}
```

未命中的 model 名按 `THINKING` / `SEARCH` env 变量处理（`MODE` 已废弃，仍兼容）。

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

OpenAI 非流式 `usage` 使用 `tiktoken` / `cl100k_base` 在本地估算文字，无法加载时回退到字符启发式，不是 DeepSeek 计费值。响应统计拼接后的 prompt 和可见正文；内部 OpenAI 统计还可包含推理。流式响应不发送 usage 块，Anthropic 的 `input_tokens` / `output_tokens` 仍为 `-1`。图片只贡献文字标记，不提供准确的视觉 token。

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
3. **设置 API key**：登录 WebUI，在「设置」页创建客户端 Key，并将创建时显示的完整值保存到调用方。Key 哈希保存在 `data/api_keys.sqlite3`；`ALLOW_UNAUTHENTICATED_API` 保持 `false`。
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
│  │ 前端 (webui-new/)    │  │ Admin API (admin.py)             │ │
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
| `chat_service.py` / `chat_runtime.py` | 协议无关的聊天执行、事件及取消安全的资源管理 |
| `responses_routes.py` / `responses_format.py` / `responses_stream.py` | Responses 请求、响应和流式事件适配 |
| `responses_tools.py` / `response_store.py` | Responses 工具调用校验和有界快照状态 |
| `image_inputs.py` / `image_sources.py` / `deepseek_files.py` | 图片规范化、来源校验、上传与处理轮询 |
| `adapter.py` | DeepSeek 协议适配器 — PoW 挑战求解，会话创建/管理，原生 SSE 解析，fragment 状态机 |
| `anthropic_format.py` | Anthropic `/v1/messages` 格式转换 — 请求解析、响应组装、SSE 生成 |
| `tool_sieve.py` | StreamSieve 流式筛分引擎 — 逐字符检测 DSML 工具调用标签，实时分离正文与工具调用 |
| `tool_dsml.py` | DSML 解析器/生成器 — XML 格式的 DSML ↔ OpenAI tool_calls 双向转换 |
| `account_pool.py` | 多账号管理 — CRUD、状态追踪（idle/busy/error）、轮询分配、健康检查 |
| `admin.py` | 管理后台 API — 密码认证、请求统计、账号池增删查改、重登录触发 |
| `webui-new/` | Vite + React 管理面板源码；构建产物位于 `webui-new/dist/` |
| `sha3_wasm_bg.wasm` | WASM 二进制，用于 DeepSeekHashV1 工作量证明求解 |

### 聊天补全请求生命周期

1. **客户端请求** → `/v1/chat/completions` 收到 OpenAI 格式请求
2. **能力解析** → `server.py: resolve_model_controls()` 按 `MODEL_ROUTES` → `THINKING`/`SEARCH` → 请求参数的顺序确定 `thinking_enabled` / `search_enabled`（`model_type` 仅作协议字段，恒为 `"default"`）
3. **DSML 注入** → 如有 `tools`，`build_dsml_tool_prompt()` 生成 DSML 格式系统提示词
4. **PoW 求解** → `adapter.py` 请求并求解 DeepSeekHashV1 挑战
5. **会话创建** → 创建新的 DeepSeek Chat 会话（可选复用）
6. **请求发送** → 以原生格式发送到 `/api/v0/chat/completion`
7. **响应处理**:
   - 非流式：解析 SSE 收集全部内容 → 检测工具调用 → 返回 OpenAI 格式
   - 流式：逐 token 转发 → StreamSieve 实时筛分 → 格式化 OpenAI SSE

Responses 使用独立的协议适配与快照状态，续聊时在原账号上新建上游会话并重放历史；详见 [Responses 文档](docs/responses-api.md)。

---

## 文件结构

```
├── server.py            # FastAPI 服务器主入口
├── adapter.py           # DeepSeek 协议适配器 (PoW, 会话, SSE)
├── chat_service.py      # 协议无关的聊天执行与事件
├── responses_*.py       # Responses 协议、工具校验与流式事件
├── response_store.py    # Responses 有界内存快照
├── anthropic_format.py  # Anthropic /v1/messages 格式转换
├── image_*.py           # 图片规范化、来源校验和 HTTP 边界
├── deepseek_files.py    # 上游图片上传与处理轮询
├── tool_sieve.py        # StreamSieve 流式工具调用检测引擎
├── tool_dsml.py         # DSML 解析器/生成器
├── account_pool.py      # 多账号池管理 (轮询、状态追踪、健康检查)
├── admin.py             # 管理后台 API 端点
├── webui-new/           # Vite + React 管理面板源码，dist/ 为构建产物
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

1. 在 WebUI「账号池」检查账号凭证状态；非交互部署则检查 `data/accounts.json` 中的凭证是否仍然有效
2. 检查能否访问 `chat.deepseek.com`（可能需要代理）
3. 检查控制台日志中的具体错误信息

### Q: 流式输出中只有 reasoning_content 没有 content

在 `thinking_mode=true` 下，模型会先输出完整的推理过程再输出回答。如果你看到只有推理没有内容：

1. 等待模型完成推理（响应尚未结束）
2. 上游偶尔只回 THINK 片段就结束（实测可复现），此时 `content` 为空但 `finish_reason` 正常，属上游行为，重试即可
3. 旧版本还可能漏掉 RESPONSE 片段首帧自带的短答案；当前解析器已修复。若仍有问题，检查上游是否实际发送正文，以及客户端是否正确处理 `finish_reason: "stop"`

### Q: 如何关闭思维链/推理展示？

设置环境变量 `THINKING=disabled`，即使请求中 `thinking_mode=true` 也不会输出 `reasoning_content`。

### Q: 一直转圈 / 响应极慢

- 开启思考（`thinking_mode=true`）本身就更慢，模型在做完整推理
- PoW 求解在低性能机器上可能需要数秒
- 检查网络到 `chat.deepseek.com` 的延迟

### Q: 多轮对话里模型「失忆」，不记得上一轮说的话

先确认调用方式，两种都支持，但要求不同：

| 调用风格 | 要求 | 行为 |
|---|---|---|
| 每轮重发完整 `messages`（OpenAI 规范） | 带上 `X-Conversation-Id` 或 `user` 才会复用上游会话 | 第二轮起只把**新增的**那部分发给上游，省 token |
| 每轮只发**最新一条** user 消息 | 必须带 `X-Conversation-Id` 或 `user` | 复用同一会话与父消息链，整段 prompt 重发一次以补齐上下文 |

排查清单：

1. 聊天补全或 Anthropic 调用是否带了 `X-Conversation-Id`（或 OpenAI 顶层 `user` / Anthropic `metadata.user_id`）？不带时每轮新建会话，需要重发完整历史；Responses 请检查 `previous_response_id` 和其状态是否仍可用。
2. 聊天补全/Anthropic 的两轮之间是否超过 `SESSION_CACHE_TTL`（默认 1800 秒）？Responses 应检查 `RESPONSES_TTL` 及祖先快照是否仍可用。
3. 聊天补全或 Anthropic 是否在流式/非流式之间来回切换？v3.3.8 起这两种模式共用同一会话缓存，此前的版本会因此各建一个会话。
4. 聊天补全/Anthropic 日志中出现 `session_prompt_diverged` 是正常提示，表示这一轮走了「保留会话 + 重发全文」的路径。

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

**解决方法：** 将插件/客户端的 origin 加入 `ALLOWED_ORIGINS` 后重启。默认列表为空，采用同源策略，不安装 CORS 中间件。配置来源后允许所有方法和请求头；若需带凭证跨域，另设 `ALLOW_CORS_CREDENTIALS=true`。

### Q: 支持多轮对话吗？

支持。客户端发送完整消息历史可重建上下文；使用 `X-Conversation-Id`、OpenAI 顶层 `user` 或 Anthropic `metadata.user_id`，还可复用调用方隔离、账号绑定的上游会话。无显式标识时每次新建会话。只发送最新消息的客户端依赖已有 parent 链，链无法复用时应重发完整文字和图片。

### Q: 如何查看 PoW 求解过程和调试信息？

上游请求使用 `curl_cffi`。设置 `LOG_LEVEL=DEBUG` 可查看项目诊断日志，不代表会输出原始请求/响应；诊断时不要打印 token、cookies 或签名图片 URL：

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Q: Token/凭证多久过期？

DeepSeek 的 Token 有效期不明确。认证失败可能是 HTTP 401/403，也可能是 HTTP 200 加业务码 40003。重新登录后，在 WebUI 账号池或 `data/accounts.json` 更新凭证；账号凭证不从 `.env` 读取。

---

## 环境变量参考

### 核心配置

| 变量 | 默认值 | 必填 | 说明 |
|------|--------|------|------|
| `HOST` | `127.0.0.1` | 否 | 监听地址。`0.0.0.0` 配合默认 admin 密码时拒绝启动 |
| `PORT` | `8080` | 否 | 服务器监听端口 |
| `ALLOW_UNAUTHENTICATED_API` | `false` | 否 | 是否允许 `/v1/*` 无鉴权访问；公网部署不要开启 |
| `ALLOW_INSECURE_PUBLIC_DEFAULTS` | `false` | 否 | 显式确认在公网上使用默认密码（不建议） |

客户端 API Key 在 WebUI「设置」页管理，SQLite 文件中只保存哈希。旧版 `.env` 的 `API_KEYS` / `DEEPSEEK_API_KEY` 仅在首次创建 Key 数据库时导入一次；确认客户端已可用后，可从 `.env` 删除旧配置。

### 账号池存储

| 变量 | 默认值 | 必填 | 说明 |
|------|--------|------|------|
| `ACCOUNT_STORE_PATH` | `data/accounts.json` | 否 | 面板持久化账号保存路径 |

### 模型行为

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MODEL_NAME` | `"deepseek-chat"` | 本代理服务的**唯一**模型名；`/v1/models` 与 API 响应都用它 |
| `THINKING` | `"auto"` | `auto` / `enabled` / `disabled` — 控制 `thinking_enabled`（原「专家模式」开关，**这里**决定思考与否） |
| `SEARCH` | `"auto"` | `auto` / `enabled` / `disabled` — 控制 `search_enabled` |
| `MODEL_ROUTES` | `""` | 可选高级覆盖：JSON 路由表，把 model 名映射到 thinking/search 能力预设。配置后 `/v1/models` 列出其键；不配置时只列 `MODEL_NAME`，老的 `deepseek-reasoner` 等作为别名照常接受 |
| `MODE` | `"auto"` | **已废弃**，仅兼容旧配置：`expert` ≡ `THINKING=enabled`，`quick` ≡ `THINKING=disabled` |

### 管理面板

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_ADMIN_PASSWORD` | `"admin"` | 管理面板登录密码（公网部署必须修改） |
| `API_KEY_STORE_PATH` | `data/api_keys.sqlite3` | API key 数据库路径；相对路径以仓库目录为基准 |

### 限流 & 会话

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ENABLE_RATE_LIMIT` | `true` | 客户端限流总开关 |
| `CLIENT_RPM_PER_KEY` | `60` | 每 API key 每分钟请求数 |
| `CLIENT_RPM_PER_IP` | `120` | 每 IP 每分钟请求数 |
| `SESSION_CACHE_TTL` | `1800` | 聊天补全/Anthropic 会话缓存 TTL（秒），0 = 禁用缓存复用 |
| `SESSION_CACHE_MAX` | `10000` | 聊天补全/Anthropic 会话缓存的最大条目数 |
| `DEEPSEEK_MAX_CONCURRENCY` | `2` | 所有账号共享的上游请求并发上限 |
| `DEEPSEEK_RATE_LIMIT_RETRY_DELAYS` | `5,15` | 上游限流后的重试等待秒数，逗号分隔 |

Responses 的 TTL、记录数量、字节和历史深度限制独立配置，见 [Responses 状态配置](docs/responses-api.md#状态隔离与限制)。

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
| `DEEPSEEK_JITTER_SECS` | `0.4` | 调用间随机抖动（秒） |
| `DSML_MAX_BUFFER_BYTES` | `1048576` | StreamSieve 捕获缓冲上限 |
| `DISABLE_AUTO_RECOVER` | `false` | 设为 true 禁用账号自动恢复 |

---

## 依赖

以 `requirements.txt` 为安装依据，最低版本如下：

| 包 | 最低版本 | 用途 |
| --- | --- | --- |
| `fastapi` | ≥0.115.0 | Web 框架 |
| `uvicorn` | ≥0.30.0 | ASGI 服务器 |
| `curl_cffi` | ≥0.7.1 | DeepSeek 上游 HTTP 客户端 |
| `wasmtime` | ≥15.0.0 | PoW WASM 运行时 |
| `python-dotenv` | ≥1.0.0 | 运行配置加载 |
| `Pillow` | ≥10.4.0 | 图片格式与像素校验 |
| `jsonschema` | ≥4.23.0 | Responses 函数参数校验 |
| `referencing` | ≥0.28.4 | 本地 schema 引用与离线解析 |
| `openai` | ≥2.0.0 | 标准 SDK 兼容性验收测试 |
| `httpx2` | ≥2.0.0 | 测试传输兼容 |
| `httpx` | ≥0.27.0 | 测试传输兼容 |
| `cryptography` | ≥42.0.0 | 账号凭证加密 |
| `tiktoken` | ≥0.7.0 | 本地文字 token 估算 |
| `pytest` | ≥8.0.0 | 离线测试 |

---

## 许可

本项目使用 **Unlicense** 协议正式发布到公有领域（public domain）。

```
This is free and unencumbered software released into the public domain.
```

你可以自由地复制、修改、发布、使用、编译、出售或分发本软件，无论用于商业或非商业目的，无论以任何形式。

**不提供任何保证**，不保证服务的可用性、准确性、稳定性。使用本项目所产生的任何后果由使用者自行承担。

---

## 图片输入与多模态

使用已有 `deepseek-chat` 模型即可，无需切换到 `vision`。图片使用本次选定的账号上传，等待处理成功后再提交聊天；`stream=true` 也会先完成这一步。

OpenAI `/v1/chat/completions`：

```json
{
  "model": "deepseek-chat",
  "stream": false,
  "messages": [{"role": "user", "content": [
    {"type": "text", "text": "描述这张图片"},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,<图片base64>"}}
  ]}]
}
```

Anthropic `/v1/messages`：

```json
{
  "model": "deepseek-chat",
  "max_tokens": 1024,
  "messages": [{"role": "user", "content": [
    {"type": "text", "text": "描述这张图片"},
    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "<图片base64>"}}
  ]}]
}
```

OpenAI 的 `image_url.url` 也可使用公网 HTTP(S) 图片地址；Anthropic 对应 `{"type":"image","source":{"type":"url","url":"https://公开地址/image.png"}}`。Anthropic 用户消息内的 `tool_result.content` 支持嵌套图片。system/assistant 图片、动画图、PDF、音视频和 Files API 文件 ID 不在支持范围。OpenAI `detail` 不映射为上游参数。

远程图片下载不携带 DeepSeek 凭证、不使用环境代理，只允许解析到公网 IP 的 HTTP(S) 地址和 80/443 端口，并对每次重定向重新检查。内网图片请由调用方读取后发送 base64。
使用 fake-IP DNS 的代理环境可能将公网域名解析为 `198.18.0.0/15` 等非公网地址，此时 URL 输入会返回 400。请为图片域名使用真实公网 DNS，或发送 base64；程序不会绕过地址校验。

| 环境变量 | 默认值 | 含义 |
| --- | --- | --- |
| `IMAGE_MAX_IMAGES` | `8` | 请求图片部件数量，含历史和工具结果 |
| `IMAGE_MAX_BYTES` | `10485760` | 单图解码后文件字节数（10 MiB） |
| `IMAGE_MAX_TOTAL_BYTES` | `33554432` | 请求内全部图片文件字节数（32 MiB） |
| `IMAGE_MAX_REQUEST_BYTES` | `41943040` | `/v1/chat/completions`、`/v1/messages`、`/v1/responses` 的 JSON 请求体上限（40 MiB） |
| `IMAGE_MAX_PIXELS` | `25000000` | 单图像素上限 |
| `IMAGE_DOWNLOAD_TIMEOUT` | `15` | 单图远程下载限制，秒 |
| `IMAGE_PROCESSING_TIMEOUT` | `60` | 每次上传 HTTP 请求/批量处理轮询各自的超时，秒；不包含 PoW 和聊天 |

这些是本服务的资源策略，不是上游最大能力声明。聊天补全和 Anthropic 每个会话最多缓存 64 个文件引用，与调用方、账号及凭证绑定，随会话 TTL 过期；使用显式会话标识（如 `X-Conversation-Id`）可复用引用。Responses 通过 `previous_response_id` 在独立快照状态中保存账号绑定的引用，并在新会话中重放历史图片引用，详见 [Responses 状态说明](docs/responses-api.md#状态隔离与限制)。两种机制均不在磁盘持久化图片；客户端仍应保留原图以便重建历史。历史比较包含图片哈希，重试换会话保留可用图片引用。

无法解码/损坏的图片返回 400、不支持格式 415、超限 413、文件服务限流 429、上游文件失败 502、处理轮询超时 504。聊天补全和 Anthropic 的请求结构不符合 schema 时可能返回 FastAPI 的 422；Responses 的无效请求字段返回 400。图片输入错误不会把账号池标记为失效。OpenAI 非流式 `usage` 是文字与附件标记的估算；Anthropic usage 仍为 `-1`，两者均不提供准确的视觉 token 统计。

## 致谢

- [DeepSeek](https://deepseek.com) — 优秀的 AI 模型与平台
- OpenAI — API 标准格式参考
- [wasmtime-py](https://github.com/bytecodealliance/wasmtime-py) — WASM 运行时
- [@minhmc2007](https://github.com/minhmc2007) — 贡献多轮会话复用修复（PR #10，v3.3.0）
- [@Zhangkc](https://github.com/Zhangkc) — 贡献请求趋势图修复：stats 采样器读取不存在的 avg_latency_ms 属性（PR #14，v3.3.2）
