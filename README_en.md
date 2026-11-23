# DeepSeek Chat API Proxy

Responses API: verified with Python sync/async and JavaScript SDKs for text/images, typed SSE, multiple function calls and immutable `previous_response_id` state. See the [supported subset and examples](docs/responses-api_en.md).

**v4.2.0** adds English to the admin panel. After signing in, choose English or Chinese from the top bar. Your browser remembers your choice. [Release and upgrade notes (Chinese)](docs/release-notes/v4.2.0.md)

> Convert DeepSeek Chat's (chat.deepseek.com) private API into an **OpenAI / Anthropic compatible** format.

> **🤖 Fully AI-Generated Disclaimer**: This project does not contain a single line of human-written code. All API endpoint design, protocol reverse-engineering, PoW solving, SSE parsing, format mapping, and documentation were produced in collaboration between the **DeepSeek v4 Flash model** and **Claude Code**.

**Disclaimer**: This project is for learning and research purposes only. It is an unofficial project and is not affiliated with DeepSeek. Use at your own risk; stability is not guaranteed.

---

## Features

- **OpenAI-compatible** — `/v1/chat/completions` and `/v1/models` endpoints, supports `stream` mode.
- **Image input** — static JPEG/PNG/WebP for both protocols and output modes; base64/data URL and public HTTP(S) URL sources.
- **Anthropic-compatible** — `/v1/messages` endpoint, supports Claude API format.
- **API key auth** — `/v1/*` supports `Authorization: Bearer` / `x-api-key`, suitable for public deployment.
- **Chain of thought (Reasoning/Thinking)** — with thinking enabled, reasoning tokens are automatically separated and exposed via the `reasoning_content` field.
- **Thinking mode** — enables deep reasoning; responses contain a THINK→RESPONSE two-stage flow. DeepSeek upstream has merged the quick/expert modes, so the former expert experience is now just `thinking_enabled`.
- **Low-latency direct answers** — with thinking off the model answers directly, with no reasoning-chain overhead.
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
| Token | Value after `Bearer` in the `Authorization` header | Copy from the request headers |
| Cookies | Full value of the `Cookie` header | Copy from the request headers |

> Add credentials on the WebUI "Account Pool" page or store them in `data/accounts.json`. Account credentials are no longer read from `.env`.

### Configuration

```bash
# Copy the environment variable template
cp .env.example .env
```

Edit the `.env` file:

```ini
# Create and revoke client API keys in WebUI > Settings.
# The full key is shown only once; the server stores only its hash.
ALLOW_UNAUTHENTICATED_API=false

# Required: WebUI admin panel password (defaults to "admin" if unset; MUST change before public deployment)
DEEPSEEK_ADMIN_PASSWORD=***

# DeepSeek accounts are configured only in WebUI > Account Pool or data/accounts.json.

# Optional: model name exposed in the API. This proxy serves ONE model,
# and "thinking / not thinking" is decided by THINKING below — not two models.
MODEL_NAME=deepseek-chat

# Optional (advanced): model routing override. Not configured by default — when unset,
# /v1/models lists MODEL_NAME only, and legacy model names (deepseek-reasoner, etc.) are still accepted as aliases.
# MODEL_ROUTES={"my-model":"thinking"}

# Optional: listen address/port (default 127.0.0.1:8080)
HOST=127.0.0.1
PORT=8080

# Optional: capability switches (auto=respect client / enabled / disabled)
THINKING=auto
SEARCH=auto

# Deprecated: kept for backward compatibility only — expert ≡ THINKING=enabled, quick ≡ THINKING=disabled
# MODE=auto
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
#      {"id":"deepseek-chat",...}   # one model only; enable thinking with THINKING=enabled
#   ]}
```

### Admin Panel

The project ships a built-in web admin UI (React SPA since v3.0.0), providing request statistics and account pool management:

```
Open in browser: http://localhost:8080/webui/
```

> start.bat auto-builds the WebUI (source in `webui-new/`, artifacts in `webui-new/dist/`); if deploying manually, first run `npm install && npm run build` inside `webui-new/`.

Default password is `DEEPSEEK_ADMIN_PASSWORD` set in `.env` (defaults to `admin` if unset). Be sure to change the default password before public deployment.

Accounts are loaded only from `data/accounts.json`. Changes made in the WebUI Account Pool page are saved to this file; you can also maintain the JSON file directly.

Other WebUI features include:

- **Overview** — live request statistics (total/success/failure/latency/uptime) + account pool status overview.
- **Playground** — online test chat (thinking/search toggles, supports reasoning process visualization).
- **Settings** — read-only view of the currently effective runtime configuration.
---

## Non-interactive Account Pool Configuration (for proxies / automation)

> For SDKs, scripts, curl, CI, and proxies that do **not** go through the WebUI panel. Account credentials are stored only in `data/accounts.json`; `.env` does not load account credentials. Maintain this file directly for non-interactive setups.

**Full `data/accounts.json` format (v1 plaintext):**

```json
{
  "version": 1,
  "accounts": [
    {"email": "acc-001", "token": "<token>", "cookies": "<cookies>"},
    {"email": "acc-002", "token": "<token>", "cookies": "<cookies>"}
  ]
}
```

- `token` + `cookies` are required; optional `email`/`id`/`created_at`/`updated_at`.
- `chmod 600` the file and `chmod 700` its directory (it holds plaintext DeepSeek credentials; leaking them means account abuse).
- The pool loads the file once at startup; restart the process after editing.
- **Encryption**: set `DEEPSEEK_ENCRYPTION_KEY` (Fernet); on first startup plaintext is migrated to encrypted v2 automatically, leaving `accounts.json.v1.bak`. Do not hand-write plaintext afterward.

**Non-interactive setup steps:**

```bash
# 1. Write the account pool file (can be script-generated)
cat > project_dir/data/accounts.json <<'JSON'
{"version":1,"accounts":[{"email":"acc-001","token":"<token>","cookies":"<cookies>"}]}
JSON
chmod 600 project_dir/data/accounts.json && chmod 700 project_dir/data

# 2. Configure API auth (required for non-interactive use, else /v1/* → 503)
#    After startup, log into the WebUI and create an API key in Settings.

# 3. Start
python -m uvicorn server:app --host 127.0.0.1 --port 8080
```

- **Change the store path**: `ACCOUNT_STORE_PATH` environment variable.

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
| `model` | `string` | `"deepseek-chat"` | This proxy serves one model only, and this field does not select an upstream model; legacy names (`deepseek-reasoner`, etc.) are still accepted as aliases. Whether the model thinks is decided by `thinking_mode` or the server-side `THINKING` |
| `messages` | `array` | required | Message list, supports `system`/`user`/`assistant`/`tool` roles |
| `stream` | `boolean` | `false` | Whether to stream output |
| `temperature` | `float` | `null` | Accepted for compatibility; currently ignored and not forwarded |
| `top_p` | `float` | `null` | Accepted for compatibility; currently ignored and not forwarded |
| `max_tokens` | `int` | `null` | Accepted for compatibility; currently ignored, without output truncation |
| `thinking_mode` | `boolean` | `false` | enable deep reasoning (upstream `thinking_enabled`, the former expert mode) |
| `search_enabled` | `boolean` | `false` | Enable web search enhancement |
| `user` | `string` | `null` | Conversation identifier for session reuse (alternative to `X-Conversation-Id`; see Multi-turn Conversation) |
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
    "prompt_tokens": 10,
    "completion_tokens": 15,
    "total_tokens": 25
  }
}
```

> **Note**: the numbers above only illustrate the response shape. OpenAI non-streaming usage is estimated locally from the assembled text prompt and visible answer; it is not an upstream token count and excludes accurate visual-token accounting. Streaming chunks do not include usage. Anthropic usage still returns `-1`.

#### Streaming response (`stream: true`)

Standard OpenAI SSE format; each event is a line `data: {...}\n\n`, ending with `data: [DONE]\n\n`:

```
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

---

### `/v1/responses`

Create responses and retrieve or delete stored responses by ID. Codex CLI cache, client metadata and reasoning hints are accepted; ordinary function roundtrips are verified with extension tools disabled. For SDK examples, Codex configuration and capability limits, see the [Responses guide](docs/responses-api_en.md).

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

> **Note**: the Anthropic endpoint shares the same underlying adapter as the OpenAI endpoint; the THINKING/SEARCH environment variables (and the deprecated `MODE`) affect both endpoints.

---

## THINKING / SEARCH explained (MODE deprecated)

> **Since v3.3.8: DeepSeek upstream has merged "quick mode" / "expert mode", and this proxy serves a single model too.**
> The web client `client/settings?scope=model` now returns
> `{"model_type":"default","name":"快速模式","enabled":true,"switchable":true}`,
> `{"model_type":"expert","name":"专家模式","enabled":false,"switchable":false}`,
> `{"model_type":"vision","name":"识图模式","enabled":false,"switchable":false}`,
> and upstream rewrites the `model_type` in the request body back to `"default"` unconditionally (visible in the `event: ready` frame).
> In other words there is **only one chat model**, and the former "expert experience" is provided entirely by `thinking_enabled`.
> A/B tests show `model_type=default` and `expert` produce character-for-character identical output for the same prompt, with no latency difference and identical DSML tool-calling behavior.

So the two real capability switches now are:

| Env var | Values | Default | Description |
|----------|--------|------|------|
| `THINKING` | `auto` / `enabled` / `disabled` | `auto` | controls `thinking_enabled`: `true` / `false`, i.e. the former expert mode |
| `SEARCH` | `auto` / `enabled` / `disabled` | `auto` | controls `search_enabled` (web search): `true` / `false` |

`MODE` is **deprecated** and kept only for compatibility with old configs: `expert` ≡ `THINKING=enabled`, `quick` ≡ `THINKING=disabled`, `auto` does not interfere. Use `THINKING` directly in new configurations.

`model_type` is still sent with each request (keeping the request shape identical to the browser), but it is a **protocol field** rather than a capability selector: it defaults to `"default"` and only changes when explicitly set in the dict form of `MODEL_ROUTES` (leaving room for upstream re-enabling something like `vision` later).

Priority: environment variable > request parameter. When an env var is `auto`, the corresponding field in the client request decides the behavior.

### Combination examples

| THINKING | SEARCH | Behavior | Typical use case |
|----------|--------|----------|----------|
| `auto` | `auto` | decided by client `thinking_mode` / `search_enabled` | fully flexible client control |
| `disabled` | `auto` | force thinking off, answer directly | low latency, no deep reasoning needed |
| `enabled` | `enabled` | force chain of thought + web search | deep reasoning + real-time info |
| `enabled` | `disabled` | chain of thought, search off | fast responses with reasoning attached |

### Env var / request parameter interplay

```
THINKING=auto, SEARCH=auto, request thinking_mode=true  →  has reasoning_content, search decided by client
THINKING=disabled, request thinking_mode=true  →  no reasoning_content (force-disabled by the server)
THINKING=enabled, SEARCH=disabled  →  has reasoning_content + no web search
MODE=expert (legacy spelling)  →  equivalent to THINKING=enabled
```

---

## Chain of Thought (Reasoning / Thinking)

When `thinking_mode=true` (with thinking enabled), reasoning tokens are exposed via the `reasoning_content` field in both streaming and non-streaming responses.

### Reasoning in streaming responses

With thinking enabled the SSE stream first outputs reasoning tokens, then the final answer:

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
- **OpenAI clients**: use the custom HTTP header `X-Conversation-Id` or the top-level `user` field as the session key.
- **Isolation and account binding**: cached sessions are scoped to the caller and bound to the DeepSeek account that created them; an upstream session is never submitted with another account's credentials.
- **Without an explicit identifier**: sessions are not reused. The proxy never infers a key from the first message, since unrelated users often share the same opener.

The chat completions and Anthropic session cache TTL defaults to 1800 seconds (`SESSION_CACHE_TTL`); a new session starts after expiry. `SESSION_CACHE_TTL=0` disables session-cache reuse for those endpoints; clients can still resend complete history. Responses `previous_response_id` uses separate bounded in-memory state and is unaffected by this setting.

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

> **Note**: multi-turn sessions depend on DeepSeek upstream accepting `parent_message_id`; if the upstream has a length limit on history, long sessions may be truncated mid-way. When the original account is busy or unavailable, the proxy safely starts a new session instead of continuing the old one with another account.

---

## Model routing (v2.2.0; optional advanced override since v3.3.8)

**Not configured by default.** This proxy serves a single model: `/v1/models` lists only `MODEL_NAME` (default `deepseek-chat`), and "thinking / not thinking" is decided by `THINKING` (or the request's `thinking_mode`) — **there are not two models**. Since upstream has merged the quick/expert modes, a model name cannot select a different upstream model either.

Clients that hardcode the old names (`deepseek-reasoner`, etc.) do not get a 404: those names are normalized to `deepseek-chat` through `model_router.LEGACY_MODEL_ALIASES` and keep working, but they **no longer change behaviour** (they used to mean "thinking on"; set `THINKING=enabled` when you want reasoning now).

Configure `MODEL_ROUTES` only when you really want per-model-name routing; once configured, `/v1/models` lists its keys instead:

```bash
# Simple form — string value (capability preset)
#   "default"  → thinking off (direct answer)
#   "thinking" → thinking on (the former "expert experience")
#   "expert"   → legacy alias of "thinking", for configs from before v3.3.8
#   "quick"    → legacy alias of "default"
MODEL_ROUTES={"my-model":"thinking"}

# Full form — dict value (search and the `model_type` protocol field can be set explicitly)
MODEL_ROUTES={"my-model":{"thinking":"enabled","search":"disabled"}}
```

Model names not matched are handled by the `THINKING` / `SEARCH` env variables (`MODE` is deprecated but still accepted).

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

OpenAI non-streaming `usage` contains local text estimates using `tiktoken` / `cl100k_base`, with a character heuristic fallback. These are not DeepSeek billing counts. The response counts the assembled prompt and visible answer; internal OpenAI statistics can also count reasoning. Streaming responses do not emit a usage chunk, and Anthropic `input_tokens` / `output_tokens` remain `-1`. Images contribute text markers but no accurate visual-token count.

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
3. **Set API keys**: log into the WebUI, create a client key on the Settings page, and save its one-time value in your client. Only the key hash is stored in `data/api_keys.sqlite3`; keep `ALLOW_UNAUTHENTICATED_API` as `false`.
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
│  │ Frontend (webui-new) │  │ Admin API (admin.py)             │ │
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
| `server.py` | FastAPI server, routing, THINKING/SEARCH capability control, OpenAI SSE formatting |
| `chat_service.py` / `chat_runtime.py` | Protocol-neutral chat execution, events and cancellation-safe resource ownership |
| `responses_routes.py` / `responses_format.py` / `responses_stream.py` | Responses request, response and streaming event adapters |
| `responses_tools.py` / `response_store.py` | Responses function-call validation and bounded snapshot state |
| `image_inputs.py` / `image_sources.py` / `deepseek_files.py` | Image normalization, source validation, upload and processing polling |
| `adapter.py` | DeepSeek protocol adapter — PoW challenge solving, session create/manage, native SSE parsing, fragment state machine |
| `anthropic_format.py` | Anthropic `/v1/messages` format conversion — request parsing, response assembly, SSE generation |
| `tool_sieve.py` | StreamSieve streaming sieve engine — character-by-character DSML tool-call tag detection, real-time separation of body text and tool calls |
| `tool_dsml.py` | DSML parser/generator — bidirectional XML-format DSML ↔ OpenAI tool_calls conversion |
| `account_pool.py` | Multi-account management — CRUD, state tracking (idle/busy/error), round-robin allocation, health checks |
| `admin.py` | Admin backend API — password auth, request stats, account pool CRUD, re-login trigger |
| `webui-new/` | Vite + React admin panel source; build output is in `webui-new/dist/` |
| `sha3_wasm_bg.wasm` | WASM binary for DeepSeekHashV1 proof-of-work solving |

### Chat completions request lifecycle

1. **Client request** → `/v1/chat/completions` receives an OpenAI-format request.
2. **Capability resolution** → `resolve_model_controls()` picks `thinking_enabled` / `search_enabled` (`model_type` is a protocol field, always `"default"`).
3. **DSML injection** → if there are `tools`, `build_dsml_tool_prompt()` generates a DSML-format system prompt.
4. **PoW solving** → `adapter.py` requests and solves the DeepSeekHashV1 challenge.
5. **Session creation** → creates a new DeepSeek Chat session (optionally reused).
6. **Request sending** → sends to `/api/v0/chat/completion` in native format.
7. **Response handling**:
   - Non-streaming: parse SSE to collect all content → detect tool calls → return OpenAI format.
   - Streaming: forward token by token → StreamSieve filters in real time → format OpenAI SSE.

Responses uses its own protocol adapter and snapshot state, replaying history in a new upstream session on the original account; see the [Responses guide](docs/responses-api_en.md).

---

## File Structure

```
├── server.py            # FastAPI server main entry
├── adapter.py           # DeepSeek protocol adapter (PoW, sessions, SSE)
├── chat_service.py      # Protocol-neutral chat execution and events
├── responses_*.py       # Responses protocol, tool validation and streaming
├── response_store.py    # Bounded in-memory Responses snapshots
├── anthropic_format.py  # Anthropic /v1/messages format conversion
├── image_*.py           # Image normalization, source validation and HTTP boundary
├── deepseek_files.py    # Upstream image upload and processing polling
├── tool_sieve.py        # StreamSieve streaming tool-call detection engine
├── tool_dsml.py         # DSML parser/generator
├── account_pool.py      # Multi-account pool management (round-robin, state tracking, health checks)
├── admin.py             # Admin backend API endpoints
├── webui-new/           # Vite + React admin source; dist/ is the build output
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

1. Check the account status in WebUI > Account Pool; for non-interactive deployments, verify the credentials in `data/accounts.json` are still valid.
2. Check that `chat.deepseek.com` is reachable (may need a proxy).
3. Check the specific error in the console logs.

### Q: Streaming output only has reasoning_content, no content

With thinking enabled (`thinking_mode=true`), the model outputs the full reasoning process first, then the answer. If you see only reasoning without content:

1. Wait for the model to finish reasoning (the response is not over).
2. Upstream occasionally ends the turn after only the THINK fragment (reproducible in practice); `content` is then empty while `finish_reason` is normal. This is upstream behavior — just retry.
3. If it's a real bug: confirm the server version and check whether `finish_reason` is output normally. Known older versions may lack the `finish_reason: "stop"` frame.

### Q: How do I disable chain-of-thought / reasoning display?

Set `THINKING=disabled`; then even if `thinking_mode=true` in the request, `reasoning_content` will not be output.

### Q: Constantly loading / very slow responses

- With thinking enabled (`thinking_mode=true`) responses are inherently slower; the model is doing full reasoning.
- PoW solving can take seconds on low-performance machines.
- Check network latency to `chat.deepseek.com`.

### Q: The model "forgets" what was said in earlier turns

First confirm how you call it — both styles are supported, with different requirements:

| Calling style | Requirement | Behavior |
|---|---|---|
| Resend the full `messages` every turn (OpenAI spec) | include `X-Conversation-Id` or `user` to reuse the upstream session | from the second turn on, only the **new** part is sent upstream, saving tokens |
| Send only the **latest** user message each turn | `X-Conversation-Id` or `user` is required | the same session and parent-message chain are reused, and the full prompt is re-sent once to fill in the context |

Troubleshooting checklist:

1. For chat completions or Anthropic, did you pass `X-Conversation-Id` (or the OpenAI top-level `user` / Anthropic `metadata.user_id`)? Without it each turn starts a new session and must resend complete history. For Responses, check `previous_response_id` and whether its state is still available.
2. For chat completions/Anthropic, did more than `SESSION_CACHE_TTL` (default 1800 seconds) pass between turns? For Responses, check `RESPONSES_TTL` and whether ancestor snapshots remain available.
3. For chat completions or Anthropic, are you switching between streaming and non-streaming? Since v3.3.8 those modes share one session cache; earlier versions created one session per mode.
4. For chat completions/Anthropic, a `session_prompt_diverged` log is a normal hint that this turn kept the session and resent the full prompt.

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

**Solution:** set `ALLOWED_ORIGINS` to the extension/client origin and restart. With an empty list, the default is same-origin and CORS middleware is not installed. Configured origins allow all methods/headers; credentialed cross-origin requests additionally need `ALLOW_CORS_CREDENTIALS=true`.

### Q: Does it support multi-turn conversations?

Yes. Send full message history to reconstruct context, and optionally use `X-Conversation-Id`, OpenAI `user`, or Anthropic `metadata.user_id` to reuse a caller-scoped, account-bound upstream session. Without an explicit identifier, each request creates a new session. Minimal latest-message-only clients depend on the existing parent chain; resend complete text/images if that chain cannot be reused.

### Q: How do I view the PoW solving process and debug info?

Upstream traffic uses `curl_cffi`. Set `LOG_LEVEL=DEBUG` for project diagnostics; this does not promise raw request/response logging. Avoid printing tokens, cookies or signed image URLs:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Q: How long do tokens/credentials last?

DeepSeek's token validity is unclear. Authentication can fail with HTTP 401/403 or HTTP 200 plus business code 40003. Re-login and update credentials in the WebUI account pool or `data/accounts.json`; account credentials are not read from `.env`.

---

## Environment Variable Reference

### Core config

| Variable | Default | Required | Description |
|------|--------|------|------|
| `HOST` | `127.0.0.1` | no | Listen address. `0.0.0.0` refuses to start with default admin password |
| `PORT` | `8080` | no | Server listen port |
| `ALLOW_UNAUTHENTICATED_API` | `false` | no | whether to allow unauthenticated `/v1/*` access; do NOT enable for public |
| `ALLOW_INSECURE_PUBLIC_DEFAULTS` | `false` | no | explicitly confirm using default password on public internet (not recommended) |

Client API keys are managed in WebUI > Settings, and only hashes are stored in SQLite. Legacy `.env` values from `API_KEYS` / `DEEPSEEK_API_KEY` are imported once when the key database is first created; remove the old entries from `.env` after confirming clients still work.

### Account pool storage

| Variable | Default | Required | Description |
|------|--------|------|------|
| `ACCOUNT_STORE_PATH` | `data/accounts.json` | no | panel-persisted account save path |

### Model behavior

| Variable | Default | Description |
|------|--------|------|
| `MODEL_NAME` | `"deepseek-chat"` | the **single** model name this proxy serves; used by `/v1/models` and API responses |
| `THINKING` | `"auto"` | `auto` / `enabled` / `disabled` — controls `thinking_enabled` (the former expert-mode switch; **this** is what decides whether the model thinks) |
| `SEARCH` | `"auto"` | `auto` / `enabled` / `disabled` — controls `search_enabled` |
| `MODEL_ROUTES` | `""` | optional advanced override: a JSON route table mapping a model name to thinking/search capability presets. When set, `/v1/models` lists its keys; when unset only `MODEL_NAME` is listed and legacy names such as `deepseek-reasoner` are still accepted as aliases |
| `MODE` | `"auto"` | **deprecated**, kept only for old configs: `expert` ≡ `THINKING=enabled`, `quick` ≡ `THINKING=disabled` |

### Admin panel

| Variable | Default | Description |
|------|--------|------|
| `DEEPSEEK_ADMIN_PASSWORD` | `"admin"` | admin panel login password (must change for public deployment) |
| `API_KEY_STORE_PATH` | `data/api_keys.sqlite3` | API key database path; relative paths are resolved from the repository directory |

### Rate limiting & sessions

| Variable | Default | Description |
|------|--------|------|
| `ENABLE_RATE_LIMIT` | `true` | client rate-limit master switch |
| `CLIENT_RPM_PER_KEY` | `60` | requests per minute per API key |
| `CLIENT_RPM_PER_IP` | `120` | requests per minute per IP |
| `SESSION_CACHE_TTL` | `1800` | chat completions/Anthropic session cache TTL (seconds), 0 = disable cache reuse |
| `SESSION_CACHE_MAX` | `10000` | maximum chat completions/Anthropic session-cache entries |
| `DEEPSEEK_MAX_CONCURRENCY` | `2` | upstream request concurrency limit shared across accounts |
| `DEEPSEEK_RATE_LIMIT_RETRY_DELAYS` | `5,15` | comma-separated backoff delays in seconds after upstream rate limiting |

Responses TTL, record count, byte and history-depth limits are configured separately; see [Responses state settings](docs/responses-api_en.md).

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
| `DEEPSEEK_JITTER_SECS` | `0.4` | random jitter between calls (seconds) |
| `DSML_MAX_BUFFER_BYTES` | `1048576` | StreamSieve capture buffer cap |
| `DISABLE_AUTO_RECOVER` | `false` | set true to disable account auto-recovery |

---

## Dependencies

Install `requirements.txt`; the declared minimum versions are:

| Package | Minimum version | Purpose |
| --- | --- | --- |
| `fastapi` | ≥0.115.0 | Web framework |
| `uvicorn` | ≥0.30.0 | ASGI server |
| `curl_cffi` | ≥0.7.1 | DeepSeek upstream transport |
| `wasmtime` | ≥15.0.0 | PoW WASM runtime |
| `python-dotenv` | ≥1.0.0 | Runtime configuration |
| `Pillow` | ≥10.4.0 | Image validation |
| `jsonschema` | ≥4.23.0 | Responses function parameter validation |
| `referencing` | ≥0.28.4 | Local schema references with offline resolution |
| `openai` | ≥2.0.0 | Standard SDK compatibility tests |
| `httpx2` | ≥2.0.0 | Test transport compatibility |
| `httpx` | ≥0.27.0 | Test transport compatibility |
| `cryptography` | ≥42.0.0 | Credential encryption |
| `tiktoken` | ≥0.7.0 | Local text token estimates |
| `pytest` | ≥8.0.0 | Offline tests |

---

## License

This project is released into the **public domain** under the **Unlicense**.

```
This is free and unencumbered software released into the public domain.
```

You are free to copy, modify, publish, use, compile, sell, or distribute this software, in either source code form or as a compiled binary, for any purpose, commercial or non-commercial, and by any means.

**This software is provided without any warranty**, without guarantee of service availability, accuracy, or stability. Any consequences arising from the use of this project are the sole responsibility of the user.

---

## Image input

Both `/v1/chat/completions` and `/v1/messages` accept static JPEG, PNG and WebP images in streaming and nonstreaming requests. Continue using `deepseek-chat`; a separate vision model is unnecessary. Upload and processing finish before the response stream starts.

OpenAI user content accepts `{"type":"image_url","image_url":{"url":"data:image/png;base64,<base64>"}}` or a public HTTP(S) image URL. Anthropic user content accepts `{"type":"image","source":{"type":"base64","media_type":"image/png","data":"<base64>"}}` or `{"type":"image","source":{"type":"url","url":"https://public.example/image.png"}}`. Nested images in Anthropic user `tool_result.content` are supported. Combine these blocks with text in attachment order.

System/assistant images, animations, document/audio/video input and Files API IDs are unsupported. OpenAI `detail` has no upstream equivalent. Remote downloads carry no DeepSeek credentials and use no environment proxy. Every destination/redirect must resolve to public IPs; only HTTP(S) on ports 80/443 is allowed. Send local/private images as base64.
Fake-IP DNS environments may resolve public hosts to non-global addresses such as `198.18.0.0/15`; URL input then returns 400. Use real public DNS for the image host or send base64. Address checks are not bypassed.

| Environment setting | Default |
| --- | --- |
| `IMAGE_MAX_IMAGES` | 8 blocks per request, including history |
| `IMAGE_MAX_BYTES` | 10485760 bytes per image |
| `IMAGE_MAX_TOTAL_BYTES` | 33554432 image bytes per request |
| `IMAGE_MAX_REQUEST_BYTES` | 41943040 JSON request bytes for `/v1/chat/completions`, `/v1/messages`, and `/v1/responses` |
| `IMAGE_MAX_PIXELS` | 25000000 pixels per image |
| `IMAGE_DOWNLOAD_TIMEOUT` | 15 seconds per download |
| `IMAGE_PROCESSING_TIMEOUT` | 60 seconds for each upload HTTP request / processing poll deadline; excludes PoW and completion |

These are local resource policies, not upstream capacity claims. Chat completions and Anthropic keep up to 64 file references per caller-scoped, account/credential-bound conversation until its TTL expires; use an explicit conversation ID to reuse them. Responses stores account-bound references in separate snapshot state via `previous_response_id` and replays historical references in a new session; see [Responses state](docs/responses-api_en.md). Neither mechanism persists image bytes, so keep originals for history reconstruction. Image-aware history and fresh-session retries retain available references. OpenAI non-streaming usage remains a text/marker estimate; Anthropic usage remains `-1`. Neither reports accurate visual-token accounting.

Invalid decoded image content returns 400, unsupported formats 415, exceeded limits 413, file-service throttling 429, upstream file failures 502 and processing poll timeouts 504. Chat completions and Anthropic schema errors may return FastAPI validation errors (422); invalid Responses request fields return 400. Image failures do not automatically mark credentials as invalid.

## Acknowledgments

- [DeepSeek](https://deepseek.com) — fine AI models and platform
- OpenAI — API standard format reference
- [wasmtime-py](https://github.com/bytecodealliance/wasmtime-py) — WASM runtime
- [@minhmc2007](https://github.com/minhmc2007) — contributed the multi-turn session reuse fix (PR #10, v3.3.0)
- [@Zhangkc](https://github.com/Zhangkc) — contributed the request-trend chart fix: stats sampler read a nonexistent avg_latency_ms attribute (PR #14, v3.3.2)
