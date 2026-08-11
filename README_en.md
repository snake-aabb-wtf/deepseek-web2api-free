# DeepSeek Chat API Proxy

> Convert DeepSeek Chat's (chat.deepseek.com) private API into an **OpenAI / Anthropic compatible** format.

> **🤖 Fully AI-Generated Disclaimer**: This project does not contain a single line of human-written code. All API endpoint design, protocol reverse-engineering, PoW solving, SSE parsing, format mapping, and documentation were produced in collaboration between the **DeepSeek v4 Flash model** and **Claude Code**.

**Disclaimer**: This project is for learning and research purposes only. It is an unofficial project and is not affiliated with DeepSeek. Use at your own risk; stability is not guaranteed.

---

## Features

- **OpenAI-compatible** — `/v1/chat/completions` and `/v1/models` endpoints, supports `stream` mode.
- **Anthropic-compatible** — `/v1/messages` endpoint, supports Claude API format.
- **API key auth** — `/v1/*` supports `Authorization: Bearer` / `x-api-key`, suitable for public deployment.
- **Chain of thought (Reasoning/Thinking)** — in expert mode, reasoning tokens are automatically separated and exposed via the `reasoning_content` field.
- **Expert mode** — enables R1-style deep reasoning; responses contain a THINK→RESPONSE two-stage flow.
- **Quick mode** — V3-style fast answers with low latency.
- **Web search** — enables real-time search enhancement via the `search_enabled` parameter.
- **Function calling** — implements tool calls via DSML (DeepSeek Markup Language) prompt injection.
- **Streaming sieve** — the `StreamSieve` engine detects DSML tool-call tags character-by-character and separates body text from tool calls in real time from the SSE stream.
- **PoW auth** — automatically completes the WASM proof-of-work (DeepSeekHashV1) challenge.
- **Session management** — automatically creates and manages DeepSeek Chat sessions; optional multi-turn session reuse.
- **Multi-account pool** — round-robin allocation, idle/busy/error states, health checks, auto-recovery.
- **Client rate limiting** — sliding window, counted independently per API key and IP; response header `X-RateLimit-*`.
- **Usage statistics** — tiktoken-based estimation of prompt / completion / total tokens.
- **Admin panel** — built-in web management UI supporting request statistics and account pool management (multi-account round-robin / persistent CRUD / re-login).

---

## Quick Start

### Prerequisites

- Python 3.10+
- Network access to `chat.deepseek.com`
- A valid DeepSeek account (free to register)

### Installation

```bash
# 1. Clone / download this project
git clone https://github.com/snake-aabb-wtf/deepseek-web2api-free.git
cd deepseek-web2api-free

# 2. Install dependencies (on Windows, prefer start.bat which auto-creates the venv and installs; manual way:)
pip install -r requirements.txt
```

### Getting Your Credentials

You need to extract your DeepSeek credentials from the browser developer tools:

1. Open [chat.deepseek.com](https://chat.deepseek.com) in a browser and log in.
2. Press `F12` to open developer tools and switch to the **Network** tab.
3. Send any message on the page.
4. Click any request in the list (e.g. `chat/completion`).
5. Find the following two values in the request headers:

| Credential | Location | Example |
|------|------|------|
| `DEEPSEEK_TOKEN` | Bearer value of the `Authorization` header | `eyJhbGciOiJIUzI1NiIs...` |
| `DEEPSEEK_COOKIES` | Full value of the `Cookie` header | `cf_clearance=xxx; session=yyy; ...` |

> **Two usage modes**: ① fill them into `.env` as the pool-empty fallback; ② log into the WebUI and add them on the "Account Pool" page (recommended — supports CRUD + one-click re-login).

### Configuration

```bash
# Copy the environment variable template
cp .env.example .env
```

Edit the `.env` file:

```ini
# Required: client API keys, used to protect /v1/* public endpoints
API_KEYS=***
ALLOW_UNAUTHENTICATED_API=false

# Required: WebUI admin panel password (defaults to "admin" if unset; MUST change before public deployment)
DEEPSEEK_ADMIN_PASSWORD=***

# Optional: DeepSeek account credentials (fallback when pool is empty since v3.2.0)
# No longer preloaded into the pool for round-robin; only used as a read-only fallback when the panel has 0 accounts.
# Recommended: log into the WebUI and add accounts on the "Account Pool" page (persisted to data/accounts.json, CRUD supported).
DEEPSEEK_TOKEN=eyJhbG…
DEEPSEEK_COOKIES=cf_clearance=xxx; session=yyy; ...
# Multi-account format is the same (DEEPSEEK_TOKEN_1/COOKIES_1/EMAIL_1, first valid one used as fallback)

# Optional: model routing (enabled by default — Playground shows quick/expert modes)
MODEL_ROUTES={"deepseek-chat":"default","deepseek-reasoner":"expert"}

# Optional: model name exposed in the API (does not affect the actual model used)
MODEL_NAME=deepseek-chat

# Optional: listen address/port (default 127.0.0.1:8080)
HOST=127.0.0.1
PORT=8080

# Optional: mode control (auto=respect client / quick / expert)
MODE=auto
THINKING=auto
SEARCH=auto
```

For the full list of variables, see `.env.example` and [AGENTS.md](AGENTS.md).

### Startup

```bash
# Recommended: use start.bat (Windows)
#   - Auto-locates Python 3.10+, detects/creates the venv (.venv / venv / env)
#   - Validates dependencies, auto-installs if missing
#   - Auto-runs npm build when WebUI artifacts are missing (set WEBUI_REBUILD=1 to force rebuild)
#   - Only kills this project's own old processes, never kills other services on the port
#   - Prints the access URL before startup, auto-opens the browser after 3s (set WEBUI_OPEN=0 to skip)
start.bat

# Manual startup (already in venv):
#   .venv\Scripts\python -m uvicorn server:app --host 127.0.0.1 --port 8080
```

After startup the terminal shows the access URL and auto-opens the browser; sample logs:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8080 (Press CTRL+C to quit)
```

### Verification

```bash
curl http://localhost:8080/health
# → {"status":"ok"}

curl http://localhost:8080/v1/models \
  -H "Authorization: Bearer ***"
# → {"object":"list","data":[
#      {"id":"deepseek-chat",...},
#      {"id":"deepseek-reasoner",...}   # quick/expert two tiers enabled by default since v3.2.0 MODEL_ROUTES
#   ]}
```

### Admin Panel

The project ships a built-in web admin UI (React SPA since v3.0.0), providing request statistics and account pool management:

```
Open in browser: http://localhost:8080/webui/
```

> start.bat auto-builds the WebUI (source in `webui-new/`, artifacts in `webui-new/dist/`); if deploying manually, first run `npm install && npm run build` inside `webui-new/`.

Default password is `DEEPSEEK_ADMIN_PASSWORD` set in `.env` (defaults to `admin` if unset). Be sure to change the default password before public deployment.

The account pool supports two kinds of accounts:

- **Panel accounts (recommended)**: add/edit/delete on the WebUI Account Pool page, persisted to `data/accounts.json`, participate in round-robin allocation, one-click re-login.
- **env fallback (v3.2.0+)**: `DEEPSEEK_TOKEN/COOKIES` (or the `_1` multi-account format) in `.env` act as a **read-only fallback** — not part of normal round-robin; only auto-enabled when the panel has 0 accounts, ensuring the pool is never 503.
- **Overview** — live request statistics (total/success/failure/latency/uptime) + account pool status overview.
- **Playground** — online test chat (quick/expert model modes, supports reasoning process visualization).
- **Settings** — read-only view of the currently effective runtime configuration.
---

## API Documentation

### `POST /v1/chat/completions`

OpenAI-compatible chat completion endpoint.

#### Request Body

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

| Parameter | Type | Default | Description |
|------|------|--------|------|
| `model` | `string` | `"deepseek-chat"` | Model name (does not affect the actual model; only for identification) |
| `messages` | `array` | required | Message list, supports `system`/`user`/`assistant`/`tool` roles |
| `stream` | `boolean` | `false` | Whether to stream output |
| `temperature` | `float` | `null` | Sampling temperature (passed to DeepSeek but effect depends on the server) |
| `top_p` | `float` | `null` | Top-p sampling |
| `max_tokens` | `int` | `null` | Maximum generated tokens |
| `thinking_mode` | `boolean` | `false` | Enable expert-mode deep reasoning |
| `search_enabled` | `boolean` | `false` | Enable web search enhancement |
| `tools` | `array` | `null` | OpenAI-format tool definitions |
| `tool_choice` | `string\|dict` | `null` | Tool selection strategy |

#### Non-streaming response (`stream: false`)

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
      "content": "Hello! How can I help you?"
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

> **Note**: token counts in `usage` return `-1` because DeepSeek Chat does not expose token counts. This is a known limitation.

#### Streaming response (`stream: true`)

Standard OpenAI SSE format; each event is a line `data: {...}\n\n`, ending with `data: [DONE]\n\n`:

```
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

---

### `POST /v1/messages`

Anthropic Claude API-compatible chat completion endpoint.

#### Request Body

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
    {"name": "get_weather", "description": "Get weather", "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}}}
  ]
}
```

| Parameter | Type | Default | Description |
|------|------|--------|------|
| `model` | `string` | `"claude-3-5-sonnet-20241022"` | Model name (does not affect the actual model; only for identification) |
| `messages` | `array` | required | Message list, supports `user`/`assistant` roles |
| `system` | `string\|array` | `null` | System prompt |
| `stream` | `boolean` | `false` | Whether to stream output |
| `thinking` | `object` | `null` | `{"type": "enabled"}` enables thinking mode |
| `tools` | `array` | `null` | Anthropic-format tool definitions (`name`/`description`/`input_schema`) |
| `max_tokens` | `int` | `null` | Ignored (DeepSeek does not support it) |
| `metadata` | `object` | `null` | Ignored |
| `stop_sequences` | `array` | `null` | Ignored |

#### Non-streaming response (`stream: false`)

```json
{
  "id": "msg_xxxxxxxxxxxxxxxxxxxxxxxx",
  "type": "message",
  "role": "assistant",
  "content": [
    {"type": "text", "text": "Hello! How can I help you?"}
  ],
  "model": "deepseek-chat",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {"input_tokens": -1, "output_tokens": -1}
}
```

When a tool is called:

```json
"content": [
  {"type": "tool_use", "id": "toolu_xxx", "name": "get_weather", "input": {"city": "Beijing"}}
],
"stop_reason": "tool_use"
```

#### Streaming response (`stream: true`)

Native Anthropic SSE format, containing `message_start`, `content_block_start`, `content_block_delta`, `content_block_stop`, `message_delta`, `message_stop` events:

```
event: message_start
data: {"type":"message_start","message":{"id":"msg_...","type":"message","role":"assistant","content":[],"model":"deepseek-chat","stop_reason":null,...}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"reasoning process..."}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: content_block_start
data: {"type":"content_block_start","index":1,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"reply content"}}

event: content_block_stop
data: {"type":"content_block_stop","index":1}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"output_tokens":-1}}

event: message_stop
data: {}
```

> **Note**: the Anthropic endpoint shares the same underlying adapter as the OpenAI endpoint; the MODE/THINKING/SEARCH environment variables affect both endpoints.

---

## MODE / THINKING / SEARCH explained

These three environment variables are independent control dimensions that together decide each request's behavior:

| Env var | Values | Default | Description |
|----------|--------|------|------|
| `MODE` | `auto` / `quick` / `expert` | `auto` | controls `model_type`: `"default"`(quick) or `"expert"` |
| `THINKING` | `auto` / `enabled` / `disabled` | `auto` | controls `thinking_enabled`: `true` / `false` |
| `SEARCH` | `auto` / `enabled` / `disabled` | `auto` | controls `search_enabled` (web search): `true` / `false` |

Priority: environment variable > request parameter. When an env var is `auto`, the corresponding field in the client request decides the behavior.

### Combination examples

| MODE | THINKING | SEARCH | Behavior | Typical use case |
|------|----------|--------|----------|----------|
| `auto` | `auto` | `auto` | decided by client `thinking_mode` / `search_enabled` | fully flexible client control |
| `quick` | `disabled` | `auto` | force V3 quick mode, no reasoning | low latency, no deep reasoning needed |
| `expert` | `enabled` | `enabled` | force R1 expert mode + chain of thought + web search | deep reasoning + real-time info |
| `quick` | `enabled` | `disabled` | quick mode + thinking, search off | fast responses with reasoning attached |

### Env var / request parameter interplay

```
MODE=auto, THINKING=auto, SEARCH=auto, request thinking_mode=true  →  quick + has reasoning_content
MODE=expert, THINKING=disabled, request thinking_mode=true  →  expert + no reasoning_content + search decided by client
MODE=quick, THINKING=enabled, SEARCH=disabled  →  quick + has reasoning_content + no web search
```

---

## Chain of Thought (Reasoning / Thinking)

When `thinking_mode=true` (i.e., expert mode), reasoning tokens are exposed via the `reasoning_content` field in both streaming and non-streaming responses.

### Reasoning in streaming responses

In expert mode the SSE stream first outputs reasoning tokens, then the final answer:

```
data: {"id":"...","choices":[{"index":0,"delta":{"reasoning_content":""},"finish_reason":null}]}

data: {"id":"...","choices":[{"index":0,"delta":{"reasoning_content":"First"},"finish_reason":null}]}

data: {"id":"...","choices":[{"index":0,"delta":{"reasoning_content":"we"},"finish_reason":null}]}
...
data: {"id":"...","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"...","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}
...
data: {"id":"...","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}
data: [DONE]
```

Clients such as NextChat and Open WebUI recognize the `reasoning_content` field and display the chain of thought. If your client does not support it, set `THINKING=disabled` to force suppression of reasoning output.

---

## Function Calling (Tool Calls)

This project implements tool calls via **DSML (DeepSeek Markup Language)** prompt injection, leveraging DeepSeek Chat's understanding of XML tags.

### How it works

1. The function definitions in the `tools` parameter are converted into a DSML-format system prompt.
2. The prompt guides the model to respond to tool calls in a specific XML format.
3. The `StreamSieve` engine detects DSML tags in real time from the SSE stream.
4. Matching tool calls are converted to OpenAI-format `tool_calls` and returned.

### Usage example

```python
import openai

client = openai.Client(base_url="http://localhost:8080/v1", api_key="***")

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "What's the weather in Beijing?"}],
    tools=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the weather for a given city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"}
                },
                "required": ["city"]
            }
        }
    }],
    tool_choice="auto",
)
```

### DSML format

DSML uses an XML-like tag structure. When the model decides to call a tool, the response format is:

```xml
<|DSML|tool_calls>
  <|DSML|invoke name="get_weather">
    <|DSML|parameter name="city"><![CDATA[Beijing]]></|DSML|parameter>
  </|DSML|invoke>
</|DSML|tool_calls>
```

The `StreamSieve` engine switches to "capture" mode upon receiving the first `<` tag character, accumulates all DSML content, then parses it together. This avoids the text pollution caused by the model first outputting body text and then outputting tool calls.

---

## Multi-turn sessions (v2.2.0)

The DeepSeek Chat protocol itself supports chaining messages within the same `chat_session_id` via `parent_message_id`. v2.2.0 leverages this for lightweight multi-turn support on the compatible endpoints:

- **Anthropic clients**: use the `metadata.user_id` field in the request body as the session stickiness key.
- **OpenAI clients**: use the custom HTTP header `X-Conversation-Id` as the session key.
- **Fallback**: when neither is set, a SHA-256 digest of the first user message is used as the key.

The session cache TTL defaults to 600 seconds (`SESSION_CACHE_TTL`); a new session starts automatically after expiry. Set `SESSION_CACHE_TTL=0` to fully disable multi-turn behavior.

```bash
# OpenAI multi-turn example (with X-Conversation-Id header)
curl http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer $API_KEY" \
  -H "X-Conversation-Id: user-42-session-7" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[
    {"role":"user","content":"My name is Xiao Ming"},
    {"role":"user","content":"What is my name?"}
  ]}'
# The second message will see the context of the first.
```

> **Note**: multi-turn sessions depend on DeepSeek upstream accepting `parent_message_id`; if the upstream has a length limit on history, long sessions may be truncated mid-way. The current `_msg_counters` is session-level monotonically increasing within the adapter, so existing behavior is not broken even on cache misses.

---

## Model routing (v2.2.0)

Through the `MODEL_ROUTES` environment variable, clients can send different `model` fields to let the proxy auto-select `model_type` (quick/expert) and default thinking/search settings:

```bash
# Simple form — string value
MODEL_ROUTES={"deepseek-chat":"default","deepseek-reasoner":"expert"}

# Full form — dict value
MODEL_ROUTES={"deepseek-reasoner":{"model_type":"expert","thinking":"enabled","search":"disabled"}}
```

Model names not matched fall back to the existing `MODE` / `THINKING` / `SEARCH` env variables. The `/v1/models` endpoint returns all model names declared in `MODEL_ROUTES`.

---

## Client rate limiting (v2.2.0)

v2.2.0 ships a sliding-window dual-dimension rate limiter:

| Env var | Default | Description |
|----------|--------|------|
| `ENABLE_RATE_LIMIT` | `true` | Master switch; set `false` to fully disable |
| `CLIENT_RPM_PER_KEY` | `60` | requests per minute per API key (0 = unlimited) |
| `CLIENT_RPM_PER_IP` | `120` | requests per minute per IP (0 = unlimited) |

Each request must **simultaneously** pass both the key and IP dimension checks. On rate limit, returns `429 Too Many Requests` with headers:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 47
Retry-After: 47
```

> Rate-limit state is kept in-process; multi-worker deployments (gunicorn -w N) effectively enforce N × configured values.

---

## Usage statistics (v2.2.0)

The `usage` field was upgraded from the hardcoded `-1` in v2.1 to real token counts. It prefers `tiktoken`'s `cl100k_base` encoding (DeepSeek-compatible), and falls back to a character heuristic (CJK 1 token/char, ASCII ~1 token/4 chars) when tiktoken is not installed.

The server panel's `/admin/api/stats` now also returns:

| Field | Description |
|------|------|
| `success_rate` | 0.0..1.0 |
| `p50_latency_ms` / `p95_latency_ms` / `p99_latency_ms` | latency percentiles of the last 1024 requests |
| `latency_window_size` | currently used ring-buffer size |
| `total_prompt_tokens` / `total_completion_tokens` | cumulative tokens over the entire process lifetime |

---

## Security recommendations (production checklist)

Before deploying to the public internet, check in order:

1. **Change the default admin password**: `DEEPSEEK_ADMIN_PASSWORD=***` in `.env` (random characters). The service **refuses to start** when using the default password with a public binding.
2. **Set a Fernet encryption key**: `DEEPSEEK_ENCRYPTION_KEY=***` (generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`). Existing plaintext `data/accounts.json` is auto-migrated on first startup; the original is kept as `accounts.json.v1.bak`.
3. **Set API keys**: `API_KEYS=***,***` in `.env` (comma-separated for multiple). Keep `ALLOW_UNAUTHENTICATED_API` as `false`.
4. **Configure the CORS whitelist**: `ALLOWED_ORIGINS=https://app.example.com`, rather than relying on the default same-origin policy.
5. **If using a reverse proxy** (nginx, Caddy, Traefik): set `TRUSTED_PROXIES=10.0.0.0/8` (your proxy's CIDR) so admin rate limiting correctly identifies client IPs.
6. **Bind address**: default `127.0.0.1`. If using a reverse proxy, keep loopback; if exposing directly to the internet, set `HOST=0.0.0.0` and ensure TLS + WAF in front.
7. **Use HTTPS**: rate-limit response headers contain token counts and IPs; admin endpoints need HTTPS protection. Strongly recommended with a front like Cloudflare / Caddy.
8. **Rotate regularly**: proactively renew tokens / cookies around every 90 days; `accounts.json` is sensitive — ensure its partition permissions are `0o700` / NTFS ACL restricted.
9. **Rate limiting**: keep the defaults `CLIENT_RPM_PER_KEY=60`, `CLIENT_RPM_PER_IP=120` and adjust as needed.
10. **Monitoring**: `GET /health` suits liveness probes; `/admin/api/stats` suits business-metric scraping.
---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                          Admin Panel                            │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐ │
│  │ Frontend SPA (webui) │  │ Admin API (admin.py)             │ │
│  │ · Overview           │◄─┤ · Password auth / stats / acct mgmt │
│  │ · Account pool mgmt  │  │ · Re-login trigger               │ │
│  └──────────────────────┘  └───────┬──────────────────────────┘ │
└────────────────────────────────────┼────────────────────────────┘
                                     │
┌──────────────┐     OpenAI format    ┌────────▼─────────────────┐
│  Client apps  │ ◄───── SSE ────────► │   FastAPI Server          │
│ (NextChat,    │                      │   (server.py)             │
│  OpenWebUI,   │                      │                           │
│  custom)      │                      │  ┌─────────────────────┐  │
└──────────────┘                      │  │  AccountPool         │  │
                                      │  │  (account_pool.py)   │  │
                                      │  │  · multi-acct round-  │  │
                                      │  │    robin select      │  │
                                      │  │  · state tracking    │  │
                                      │  │  · health checks     │  │
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
                                      DeepSeek native protocol
                                      (PoW + SSE)
                                                 │
                                      ┌──────────▼────────────┐
                                      │  chat.deepseek.com    │
                                      │  (DeepSeek Chat API)  │
                                      └───────────────────────┘
```

### Core components

| File | Responsibility |
|------|------|
| `server.py` | FastAPI server, routing, MODE/THINKING control, OpenAI SSE formatting |
| `adapter.py` | DeepSeek protocol adapter — PoW challenge solving, session create/manage, native SSE parsing, fragment state machine |
| `anthropic_format.py` | Anthropic `/v1/messages` format conversion — request parsing, response assembly, SSE generation |
| `tool_sieve.py` | StreamSieve streaming sieve engine — character-by-character DSML tool-call tag detection, real-time separation of body text and tool calls |
| `tool_dsml.py` | DSML parser/generator — bidirectional XML-format DSML ↔ OpenAI tool_calls conversion |
| `account_pool.py` | Multi-account management — CRUD, state tracking (idle/busy/error), round-robin allocation, health checks |
| `admin.py` | Admin backend API — password auth, request stats, account pool CRUD, re-login trigger |
| `webui/` | Admin panel frontend — pure static SPA, zero build dependency |
| `sha3_wasm_bg.wasm` | WASM binary for DeepSeekHashV1 proof-of-work solving |

### Request lifecycle

1. **Client request** → `/v1/chat/completions` receives an OpenAI-format request.
2. **Mode parsing** → `server.py` determines `model_type` and `thinking_enabled` based on env vars and request params.
3. **DSML injection** → if there are `tools`, `build_dsml_tool_prompt()` generates a DSML-format system prompt.
4. **PoW solving** → `adapter.py` requests and solves the DeepSeekHashV1 challenge.
5. **Session creation** → creates a new DeepSeek Chat session (optionally reused).
6. **Request sending** → sends to `/api/v0/chat/completion` in native format.
7. **Response handling**:
   - Non-streaming: parse SSE to collect all content → detect tool calls → return OpenAI format.
   - Streaming: forward token by token → StreamSieve filters in real time → format OpenAI SSE.

---

## File Structure

```
├── server.py            # FastAPI server main entry
├── adapter.py           # DeepSeek protocol adapter (PoW, sessions, SSE)
├── anthropic_format.py  # Anthropic /v1/messages format conversion
├── tool_sieve.py        # StreamSieve streaming tool-call detection engine
├── tool_dsml.py         # DSML parser/generator
├── account_pool.py      # Multi-account pool management (round-robin, state tracking, health checks)
├── admin.py             # Admin backend API endpoints
├── webui/               # Admin panel frontend (pure static SPA)
│   ├── index.html
│   ├── app.js
│   └── style.css
├── sha3_wasm_bg.wasm    # WASM PoW solver
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
├── .env                 # Your actual config (gitignored)
├── start.bat            # Windows startup script
├── AGENTS.md            # AI Agent reference docs
└── README.md            # This file
```

---

## FAQ

### Q: Requests return 502 Bad Gateway after startup

Usually invalid credentials or a network issue:

1. Check that `DEEPSEEK_TOKEN` and `DEEPSEEK_COOKIES` in `.env` are still valid (re-extract by logging into chat.deepseek.com).
2. Check that `chat.deepseek.com` is reachable (may need a proxy).
3. Check the specific error in the console logs.

### Q: Streaming output only has reasoning_content, no content

When `thinking_mode=true` (expert mode), the model outputs the full reasoning process first, then the answer. If you see only reasoning without content:

1. Wait for the model to finish reasoning (the response is not over).
2. If it's a real bug: confirm the server version and check whether `finish_reason` is output normally. Known older versions may lack the `finish_reason: "stop"` frame.

### Q: How do I disable chain-of-thought / reasoning display?

Set `THINKING=disabled`; then even if `thinking_mode=true` in the request, `reasoning_content` will not be output.

### Q: Constantly loading / very slow responses

- Expert mode (`thinking_mode=true`) is inherently slower; the model is doing full reasoning.
- PoW solving can take seconds on low-performance machines.
- Check network latency to `chat.deepseek.com`.

### Q: curl on Windows returns 422 for Chinese requests

Windows bash curl defaults to GBK encoding, and Chinese characters in JSON may be mis-encoded. Solutions:

```bash
# Option 1: write the request body to a JSON file
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d @body.json

# Option 2: use PowerShell (recommended)
Invoke-RestMethod -Uri http://localhost:8080/v1/chat/completions `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"model":"deepseek-chat","messages":[{"role":"user","content":"你好"}],"stream":true}'
```

### Q: Changes to `.env` don't take effect

You need to restart the server process. FastAPI's reload mode does not reload environment variables:

```bash
# First kill the old process
taskkill /F /IM python.exe
# Then restart
python -m uvicorn server:app --host 0.0.0.0 --port 8080
```

### Q: Browser extensions (e.g. YouTube subtitle translation) fail, logs show 405 Method Not Allowed

Some Chrome extensions send an `OPTIONS` preflight request (CORS preflight) before using the OpenAI-compatible API to check whether the server allows cross-origin access. If the server does not handle `OPTIONS`, it returns `405 Method Not Allowed`, breaking the extension.

**Solution:** this project ships a built-in CORS middleware (`CORSMiddleware`) allowing all origins, methods, and headers by default. If you still hit CORS issues, confirm the version includes the CORS config in `server.py`.

### Q: Does it support multi-turn conversations?

No. Each request is independent; the server creates a new DeepSeek Chat session. Multi-turn support needs to be maintained at the application level (e.g. NextChat) by keeping context.

### Q: How do I view the PoW solving process and debug info?

The adapter uses `httpx` to send requests; set the log level to view detailed requests/responses:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Q: How long do tokens/credentials last?

DeepSeek's token validity is unclear. If you encounter `401` or `403` responses, re-log into chat.deepseek.com and update the credentials in `.env`.

---

## Environment Variable Reference

### Core config

| Variable | Default | Required | Description |
|------|--------|------|------|
| `HOST` | `127.0.0.1` | no | Listen address. `0.0.0.0` refuses to start with default admin password |
| `PORT` | `8080` | no | Server listen port |
| `API_KEYS` | `""` | required for public | API keys for client access to `/v1/*`, comma-separated for multiple |
| `DEEPSEEK_API_KEY` | `""` | no | single client API key alias |
| `ALLOW_UNAUTHENTICATED_API` | `false` | no | whether to allow unauthenticated `/v1/*` access; do NOT enable for public |
| `ALLOW_INSECURE_PUBLIC_DEFAULTS` | `false` | no | explicitly confirm using default password on public internet (not recommended) |

### DeepSeek accounts

| Variable | Default | Required | Description |
|------|--------|------|------|
| `DEEPSEEK_TOKEN` | `""` | required if using an account | DeepSeek API Bearer token (single-account format) |
| `DEEPSEEK_COOKIES` | `""` | required if using an account | DeepSeek cookie value (single-account format) |
| `DEEPSEEK_TOKEN_N` | `""` | no | Nth DeepSeek account token, e.g. `DEEPSEEK_TOKEN_1` |
| `DEEPSEEK_COOKIES_N` | `""` | no | Nth DeepSeek account cookies |
| `DEEPSEEK_EMAIL_N` | `"env-N"` | no | Nth account remark/identifier |
| `ACCOUNT_STORE_PATH` | `data/accounts.json` | no | panel-persisted account save path |

### Model behavior

| Variable | Default | Description |
|------|--------|------|
| `MODEL_NAME` | `"deepseek-chat"` | model name shown in `/v1/models` by default (shows route table if `MODEL_ROUTES` exists) |
| `MODE` | `"auto"` | `auto` / `quick` / `expert` |
| `THINKING` | `"auto"` | `auto` / `enabled` / `disabled` |
| `SEARCH` | `"auto"` | `auto` / `enabled` / `disabled` |
| `MODEL_ROUTES` | `""` | JSON route table, switches `model_type`/thinking/search by `model` field |

### Admin panel

| Variable | Default | Description |
|------|--------|------|
| `DEEPSEEK_ADMIN_PASSWORD` | `"admin"` | admin panel login password (must change for public deployment) |

### Rate limiting & sessions

| Variable | Default | Description |
|------|--------|------|
| `ENABLE_RATE_LIMIT` | `true` | client rate-limit master switch |
| `CLIENT_RPM_PER_KEY` | `60` | requests per minute per API key |
| `CLIENT_RPM_PER_IP` | `120` | requests per minute per IP |
| `SESSION_CACHE_TTL` | `600` | multi-turn session cache TTL (seconds), 0 = disable multi-turn |

### Security & encryption

| Variable | Default | Description |
|------|--------|------|
| `ALLOWED_ORIGINS` | `""` | CORS allowed origin list (comma-separated), empty = same-origin |
| `ALLOW_CORS_CREDENTIALS` | `false` | whether to allow credentialed cross-origin (needs `ALLOWED_ORIGINS`) |
| `TRUSTED_PROXIES` | `""` | trusted proxy IP/CIDR (when set, `X-Forwarded-For` is honored) |
| `DEEPSEEK_ENCRYPTION_KEY` | `""` | Fernet key; when set, token/cookies in `data/accounts.json` are auto-encrypted |

### Logging & anti-detection

| Variable | Default | Description |
|------|--------|------|
| `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR |
| `LOG_FORMAT` | `json` | `json` (production) or `text` (development) |
| `DEEPSEEK_IMPERSONATE` | `chrome131` | curl_cffi TLS fingerprint profile |
| `DEEPSEEK_JITTER_SECS` | `0.0` | random jitter between calls (seconds) |
| `DSML_MAX_BUFFER_BYTES` | `1048576` | StreamSieve capture buffer cap |
| `DISABLE_AUTO_RECOVER` | `false` | set true to disable account auto-recovery |

### Anti-detection — per-account proxy

| Variable | Description |
|------|------|
| `DEEPSEEK_PROXY` / `DEEPSEEK_PROXY_N` | upstream proxy URL for a single / the Nth account |
| `DEEPSEEK_EMAIL` | legacy single-account email remark |

---

## Dependencies

| Package | Minimum version | Purpose |
|----|----------|----|
| `fastapi` | ≥0.100.0 | Web framework |
| `uvicorn` | ≥0.20.0 | ASGI server |
| `httpx` | ≥0.24.0 | HTTP client (for calling the DeepSeek API) |
| `wasmtime` | ≥14.0.0 | WASM runtime (PoW solving) |
| `python-dotenv` | ≥1.0.0 | `.env` file loading |

---

## License

This project is released into the **public domain** under the **Unlicense**.

```
This is free and unencumbered software released into the public domain.
```

You are free to copy, modify, publish, use, compile, sell, or distribute this software, in either source code form or as a compiled binary, for any purpose, commercial or non-commercial, and by any means.

**This software is provided without any warranty**, without guarantee of service availability, accuracy, or stability. Any consequences arising from the use of this project are the sole responsibility of the user.

---

## Acknowledgments

- [DeepSeek](https://deepseek.com) — fine AI models and platform
- OpenAI — API standard format reference
- [wasmtime-py](https://github.com/bytecodealliance/wasmtime-py) — WASM runtime
- [@minhmc2007](https://github.com/minhmc2007) — contributed the multi-turn session reuse fix (PR #10, v3.3.0)
