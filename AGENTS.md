# AGENTS.md — DeepSeek Chat API Proxy (Preview)

> 本文档面向后续维护本项目的 AI 智能体，完整阐述项目的实现原理、协议细节、代码架构和已知问题。**请先全文阅读本文档再开始任何修改**。

---

## v3.0.0 → v3.2.3 变更摘要

### v3.2.3（2026-08-08）：多轮会话复用修复（parent 链维护）

- **根因**：v3.2.2 遗留问题——同模式多轮复用 session 时，缓存的 `parent_message_id` 未随轮次更新（始终为 `0`），第二次请求发 `parent_message_id=0` → 上游返回空响应，失败一次后才自愈
- **修复**：adapter 从 SSE `event: ready` 帧提取 `response_message_id`（非流式同时兼容 `v.response.message_id`），通过新增的 `ready_out` 回调参数返回给 server；`AcquiredAccount.record_message_id()` 将真实 message_id + 实际使用 session 写回 `SESSION_CACHE`（重试换新会话时同步更新 `chat_session_id`），并修复 `create_session()` 未保存 `_cached_session` 引用导致记录失效的问题
- **接入点**：4 条路径全部接线（OpenAI/Anthropic × 流式/非流式），工具调用分支同样记录
- 完整清单：`docs/release-notes/v3.2.3.md`

### v3.2.1（2026-08-03）：空响应根因修复

- **根因**：请求过频时上游返回 HTTP 200 + SSE `event: hint`（`type=error`，`finish_reason=rate_limit_reached`，"消息发送过于频繁，请稍后重试"）且**无任何 content token**；adapter 原先不解析 `hint` 事件 → 限流被当成"空内容"返回
- **修复**：新增 `RateLimitError`/`UpstreamHintError`，非流式 `_scan_hint_errors()` + 流式内联检测 hint（与 toast 同构）；`server` 映射 **429**（限流）/ 502（其他 hint 错误）
- 完整清单：`docs/release-notes/v3.2.1.md`

### v3.2.2（2026-08-03）：限流自适应 + hif 发送 + 测试覆盖 + 会话缓存修复

- **上游限流自适应**：`RateLimitError` 退避重试（`DEEPSEEK_RATE_LIMIT_RETRY_DELAYS` 默认 `5,15`，每次退避后换新会话）；`DEEPSEEK_JITTER_SECS` 默认 `0.4`（降低触发限流概率）
- **hif 签名头发送**：`_HifProvider` 拉取 `hif-leim/hif-dliq.deepseek.com/query`（`data.biz_data.value`，`x-hif-ttl` 缓存默认 600s），completion 请求附加 `X-Hif-Leim/Dliq`（create_session 不带）；失败静默降级（不加头）
- **测试覆盖**：`tests/test_adapter.py`（15 用例，hint/toast/空响应重试/退避/hif）+ `tests/test_account_pool.py`（10 用例，env 兜底/池空/只读保护/持久化），全套 81 测试
- 流式 toast/hint 检测修复：上游错误 data 为顶层 dict（非 `v` 包装），两者均检查
- **SESSION_CACHE 模式隔离**：缓存 key 按流式/非流式区分（`stream:`/`nonstream:`），修复"流式创建 session 被非流式复用 → 空响应"；限流/空响应时 `invalidate` 缓存（失败一次后自愈）
- **已知遗留 → 已修复（v3.2.3）**：同模式多轮复用 session 第二次请求 parent 错误导致的空响应，已通过 SSE `ready` 事件提取 `response_message_id` 维护 parent 链解决（见 v3.2.3 摘要）

### v3.2.0（2026-08-02）：维护版本

- **start.bat 重构**：自动定位 Python 3.10+、检测/创建虚拟环境（`.venv`/`venv`/`env`）、`pip install --dry-run` 校验依赖并自动安装、WebUI dist 缺失时自动 `npm` 构建（`WEBUI_REBUILD=1` 强制重建）、启动前打印访问地址并默认 3s 后自动打开浏览器（`WEBUI_OPEN=0` 跳过）、端口占用只杀本项目进程（PowerShell `Get-CimInstance` 读命令行替代已废弃的 `wmic`；GBK+CRLF 编码）
- **WebUI**：静态资源 404 修复（vite `base: '/webui/'` + router `basename: '/webui'`）、7 处 bug 修复与界面美化、Playground 重写（参数对应后端真实转发字段、移除无效温度滑块、`reasoning_content` 可视化）、快速/专家两种模型模式（`MODEL_ROUTES` 默认启用）
- **鉴权**：`/v1/*` 接受有效 admin 会话 token（`verify_admin_token`）
- **账号池**：env 凭证改为**池空只读兜底**（`_env_fallback`，面板账号优先；不再预加载进池）
- **上游空响应加固**：`UpstreamEmptyError` + 换新会话重试 1 次 + 502/错误帧
- **适配器**：`X-Client-Version` 2.0.0 → 2.3.0、删除过时的 `X-App-Version`（HAR 比对确认浏览器不再发送）
- **hif 签名头**（逆向记录）：浏览器发 `x-hif-leim`/`x-hif-dliq`（值来自 `hif-leim/hif-dliq.deepseek.com/query`，TTL 600s，localStorage 缓存）；v3.2.2 起 adapter 通过 `_HifProvider` 自动拉取并发送（失败静默降级，见 7.13）
- **已知环境事实**：`wmic` 已在 Win11 24H2+ 移除；`timeout` 命令与 Git Bash GNU coreutils 冲突（脚本用 `ping -n 2` 延时）
- 完整清单：`docs/release-notes/v3.2.0.md`

### v3.0.0（2026-06）：React WebUI 重写

- 管理面板从 vanilla JS 重写为 **Vite + React 18 + TypeScript + shadcn/ui** SPA（`webui-new/`），6 个页面（登录 / 概览 / 账号池 / Playground / 设置 / 404）
- 新增 `stats_history.py`（30s 快照滚动窗口）、`GET /admin/api/history`、`GET /admin/api/env`
- WebUI 产物位于 `webui-new/dist/`，由 `server.py` 在 `/webui/*` 下伺服；旧 `webui/` 已删除
- **构建要求**：vite `base: '/webui/'` + react-router `basename: '/webui'`，两者缺失会导致资源 404 白屏

---

## v2.2.0 变更摘要（2026-06）

新增模块：`logger.py`、`crypto.py`、`ip_utils.py`、`token_counter.py`、
`rate_limiter.py`、`model_router.py`、`session_cache.py`。

主要变化：

- **安全**：默认 `HOST=127.0.0.1`；公网 + 默认密码启动时 `SystemExit(2)`；结构化 JSON 日志；`data/accounts.json` 可选 Fernet 加密（启动时透明迁移）；CORS 严格化（空 = 同源）；XFF 白名单 (`TRUSTED_PROXIES`)；安全响应头。
- **Bug**：`adapter.chat()` 现在返回 `(content, thinking)` 元组；`anthropic_format.build_nonstream_response` 接收 `thinking_text`；`StreamSieve` 改为迭代式排空、`feed("")` 递归被替换为 `while`、捕获缓冲硬上限 1 MB（可配置 `DSML_MAX_BUFFER_BYTES`）；账号错误达到 3 次后自动后台 `check_health` 恢复。
- **新功能**：`MODEL_ROUTES` 模型路由；`SESSION_CACHE_TTL` 多轮会话（OpenAI `X-Conversation-Id` 头 / Anthropic `metadata.user_id` / 消息摘要 fallback）；`CLIENT_RPM_PER_KEY` / `CLIENT_RPM_PER_IP` 双维度滑动窗口限流；`usage` 字段返回真实 token 数（tiktoken cl100k_base，缺失时字符启发式）；`/admin/api/stats` 增加 p50/p95/p99 + 成功率。
- **工程化**：`tests/test_*.py` 56 个 pytest 用例；CI 矩阵 (3.10/3.11/3.12)；SSE 错误帧（OpenAI 流末尾发 `data: {"error":...}` 后 `data: [DONE]`）替代直接抛 500。

---

## 目录

1. [项目概述](#1-项目概述)
2. [目录结构](#2-目录结构)
3. [核心数据流](#3-核心数据流)
4. [PoW 反爬机制](#4-pow-反爬机制)
5. [会话管理](#5-会话管理)
6. [SSE 协议格式](#6-sse-协议格式)
7. [专家模式 (Expert Mode)](#7-专家模式-expert-mode)
8. [工具调用 (DSML)](#8-工具调用-dsml)
9. [StreamSieve 流式筛分引擎](#9-streamsieve-流式筛分引擎)
10. [OpenAI 兼容层](#10-openai-兼容层)
11. [Anthropic 兼容层](#11-anthropic-兼容层)
12. [多轮对话与消息组装](#12-多轮对话与消息组装)
13. [ContentPart 支持](#13-contentpart-支持)
14. [配置系统](#14-配置系统)
15. [账号池 (AccountPool)](#15-账号池-accountpool)
16. [管理后台 (Admin API)](#16-管理后台-admin-api)
17. [关键算法细节](#17-关键算法细节)
18. [已知限制与边界情况](#18-已知限制与边界情况)
19. [常见调试方法](#19-常见调试方法)
20. [协议变更预警](#20-协议变更预警)

---

## 1. 项目概述

本项目将 DeepSeek Chat 网页版（https://chat.deepseek.com）反向代理为 OpenAI 兼容 API。

### 1.1 解决的问题

- DeepSeek 官方 API 需要付费且对非中国大陆用户受限
- DeepSeek Chat 网页版免费但使用其私有协议，不兼容 OpenAI SDK
- 网页版有 PoW（Proof of Work）反爬机制，需要自动求解
- DeepSeek 提供"快速模式"和"专家模式"两种对话能力，接口行为不同

### 1.2 核心能力

| 能力 | 状态 | 说明 |
|------|------|------|
| OpenAI 兼容接口 | ✅ | `/v1/chat/completions`, `/v1/models`, `/health` |
| Anthropic 兼容接口 | ✅ | `/v1/messages` — Anthropic Claude API 格式 |
| 流式输出 (SSE) | ✅ | OpenAI chunk 格式 + Anthropic SSE 格式 |
| 非流式输出 | ✅ | 完整响应 |
| 多轮对话 | ✅ | 客户端通过 messages 数组管理上下文 |
| 普通对话 | ✅ | 快速模式 |
| 专家模式 | ✅ | DeepSeek 推理模型，含 thinking tokens |
| 工具调用 | ✅ | 基于 DSML 提示词注入（非原生） |
| ContentPart 数组 | ✅ | content 支持 str 和 array 格式 |
| PoW 自动求解 | ✅ | WASM 本地求解，0.1-0.3s |
| 会话管理 | ✅ | 每次请求新建 DeepSeek 会话 |
| 联网搜索 | ⚠️ | 参数透传，行为取决于 DeepSeek 服务端 |
| MODE 环境变量控制 | ✅ | 通过 `.env` 强制模式：`auto`/`quick`/`expert` |
| THINKING 环境变量控制 | ✅ | 通过 `.env` 强制思考：`auto`/`enabled`/`disabled` |
| SEARCH 环境变量控制 | ✅ | 通过 `.env` 强制联网搜索：`auto`/`enabled`/`disabled` |
| model_type 与 thinking_enabled 解耦 | ✅ | 两者独立，所有 4 种组合均有效 |
| finish_reason SSE 结束帧 | ✅ | 流式响应末尾发送 `delta: {}, finish_reason: "stop"` |

### 1.3 项目版本

- 当前主线：`v3.2.3`（2026-08）— 基础功能 + 工具调用 + 专家模式 + 联网搜索 + React WebUI 管理面板 + 上游限流提示解析 + 多轮会话复用
- 自 v3.0.0 起开源版与预览版已合并为单一主线，无独立 `--pre` 分支

---

## 2. 目录结构

```
D:\the llaa\DS反代 --pre\
├── server.py              # FastAPI 服务入口（路由、请求模型、SSE 组装）
├── adapter.py             # DeepSeek API 适配器（PoW、会话、SSE 解析）
├── anthropic_format.py    # Anthropic /v1/messages 格式转换层
├── account_pool.py        # 多账号池管理（CRUD、状态追踪、轮询分配、健康检查）
├── admin.py               # 管理后台 API（密码认证、请求统计、账号池管理）
├── tool_dsml.py           # DSML 格式解析器（工具调用协议）
├── tool_sieve.py          # 流式筛分引擎（实时检测工具调用标签）
├── sha3_wasm_bg.wasm      # PoW 哈希引擎 WASM 二进制
├── start.bat              # Windows 一键启动脚本（自动 venv/依赖/WebUI/开浏览器）
├── webui-new/             # 管理面板前端（v3.0.0+，React SPA，需 npm 构建）
│   └── dist/              #   构建产物（gitignored），server.py 伺服于 /webui/*
├── .env                   # 环境配置（含 TOKEN/COOKIE，不提交）
├── .env.example           # 配置模板（提交到仓库）
├── requirements.txt       # Python 依赖
├── README.md              # 用户文档
└── AGENTS.md              # 本文件
```

### 2.1 文件详细说明

#### 核心模块

| 文件 | 职责 | 不负责 |
|------|------|--------|
| `server.py` | HTTP 路由、请求/响应模型、OpenAI 格式组装、工具调用协调 | PoW 求解、原生 SSE 解析 |
| `adapter.py` | 与 DeepSeek API 通信、PoW 求解、SSE 流解析、会话创建 | HTTP 路由、OpenAI/Anthropic 格式 |
| `anthropic_format.py` | Anthropic `/v1/messages` 请求解析、响应组装、SSE 生成 | DeepSeek 协议、HTTP 路由 |
| `account_pool.py` | 多账号 CRUD、状态追踪（idle/busy/error）、轮询分配、健康检查/重登录 | HTTP 路由、DeepSeek 协议 |
| `admin.py` | 管理后台 API 端点（密码认证、统计查询、账号池 CRUD、重登录触发） | 前端渲染、DeepSeek 协议 |
| `tool_dsml.py` | DSML XML 解析与生成、工具提示词构建 | 流式检测、HTTP |
| `tool_sieve.py` | 流式文本中实时检测 DSML 工具调用标签 | 协议解析、HTTP |

**核心原则：** `adapter.py` 的输出是"裸 token 流"（str 或 dict），`server.py` 和 `anthropic_format.py` 分别负责包装成特定 API 格式。`adapter.py` 不知道任何 API 格式的存在。

#### 辅助文件

| 文件 | 用途 |
|------|------|
| `sha3_wasm_bg.wasm` | PoW 哈希引擎 WASM 二进制，从 DeepSeek 前端 JavaScript 中提取。通过 `wasmtime` 加载，导出 `wasm_solve` 等函数。版本与 DeepSeek 前端发布绑定。 |
| `start.bat` | Windows 一键启动脚本（GBK 编码 + CRLF，勿改编码）。流程：定位 Python 3.10+ → 检测/创建虚拟环境（`.venv`/`venv`/`env`）→ `pip install --dry-run` 校验依赖（缺失自动安装）→ WebUI dist 缺失时自动 `npm` 构建 → 端口检查（只杀命令行匹配 `uvicorn`/`server:app`/`server.py`/`ds2api` 的本项目进程，其他进程拒绝杀并提示）→ 打印访问地址并默认 3s 后自动打开浏览器（`WEBUI_OPEN=0` 跳过）。支持 `PORT`/`HOST` 环境变量覆盖。 |
| `webui-new/` | 管理面板前端（v3.0.0+，Vite + React 18 + TypeScript + shadcn/ui SPA）。源码构建产物在 `webui-new/dist/`（gitignored），由 `server.py` 伺服于 `/webui/*`。**必须**以 `base: '/webui/'` + react-router `basename: '/webui'` 构建，否则资源 404。旧版 `webui/`（vanilla）已删除。 |
| `requirements.txt` | Python 依赖声明。关键依赖版本要求见下表。 |
| `.env.example` | 环境配置模板。复制为 `.env` 后填入凭证。提交到仓库但不含敏感信息。 |

**依赖版本说明：**

| 包 | 最低版本 | 用途 | 备注 |
|---|---------|------|------|
| `fastapi` | 0.100.0 | Web 框架 | 0.100+ 支持 Pydantic v2 |
| `uvicorn` | 0.20.0 | ASGI 服务器 | 0.20+ 支持 lifespan |
| `httpx` | 0.24.0 | HTTP 客户端 | 0.24+ 修复关键连接池 bug |
| `wasmtime` | 14.0.0 | WASM 运行时 | 14.0+ 是首个稳定支持 Windows 的版本 |
| `python-dotenv` | 1.0.0 | .env 加载 | 1.0+ 行为稳定 |

### 2.2 开发环境搭建

```bash
# 1. 克隆/进入项目目录
cd "D:\the llaa\DS反代 --pre"

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置凭证（从浏览器 DevTools 获取）
copy .env.example .env
# 编辑 .env: 填入 DEEPSEEK_TOKEN 和 DEEPSEEK_COOKIES

# 4. 启动服务
python server.py
# 或
start.bat

# 5. 测试
curl http://localhost:8080/health
```

**热重载开发（推荐）：**
```bash
uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080} --reload
```
`--reload` 会在文件变更时自动重启，但注意它不会自动清理 `__pycache__`（见 §18.5）。

### 2.3 预览版 vs 开源版差异

> **v3.0.0 起已合并**：以下对比仅作历史参考。当前主线同时具备左右两列全部能力（OpenAI + Anthropic + 专家模式 + 联网搜索 + 工具调用 + React WebUI）。

| 维度 | 开源版 (`v2.0.0`) | 预览版 (`v2.2.0-pre`) |
|------|-------------------|----------------------|
| `adapter.py` 请求体 | 基本字段：`chat_session_id`, `prompt`, `ref_file_ids`, `stream` | 新增：`parent_message_id`, `model_type`, `thinking_enabled`, `search_enabled`, `preempt` |
| 请求头 | `X-App-Version: 0.0.1` | `X-App-Version: 20241129.1` + 5 个额外版本头 |
| 会话创建 | 只处理 `biz_data.id` 格式 | 双格式兼容（`id` 或 `chat_session.id`） |
| `chat()` | 只解析 `response/content APPEND` | 完整 fragment 状态机支持两种模式 |
| `chat_stream()` | 简单 token 透传 | fragment 状态机 + `__type: "thinking"` 字典输出 |
| `_msg_counters` | 无 | 新增，追踪 `parent_message_id` |
| `httpx.Client` 超时 | 60s | 120s |
| server.py 端点 | 标准 OpenAI | 同上 + `thinking_mode`, `search_enabled` 参数 |
| SSE 输出 | `content` delta | 同上 + `reasoning_content` delta + `finish_reason: "stop"` 结束帧 |
| MODE 环境变量 | 无 | `auto`/`quick`/`expert`，通过 `.env` 配置 |
| THINKING 环境变量 | 无 | `auto`/`enabled`/`disabled`，通过 `.env` 配置 |
| SEARCH 环境变量 | 无 | `auto`/`enabled`/`disabled`，通过 `.env` 配置 |
| PORT 环境变量 | 无 | 可配置监听端口（默认 8080），通过 `.env` 或环境变量 |
| model_type 控制 | 与 thinking_enabled 绑定 | 完全解耦，由 MODE 独立控制 |
| WASM 线程安全 | 无锁 | `threading.Lock` 保护 Store 并发访问 |

---

## 3. 核心数据流

### 3.1 请求完整链路

```
客户端 (OpenAI SDK)
  │  POST /v1/chat/completions  (OpenAI 格式 JSON)
  ▼
server.py: chat_completions()
  │  _build_prompt() → 拼接 messages 为纯文本
  │  如有 tools → build_dsml_tool_prompt() → 注入 system message
  ▼
adapter.py: create_session()
  │  POST /api/v0/chat/create_pow_challenge → 获取 challenge
  │  WASM 求解 PoW nonce
  │  POST /api/v0/chat_session/create → 获取 session_id
  ▼
adapter.py: chat() 或 chat_stream()
  │  POST /api/v0/chat/completion (含 PoW Header + 请求体)
  │  带 thinking_enabled、search_enabled、model_type、preempt 等参数
  ▼
  SSE 流解析 (逐行)
  │  处理 event: ready → 提取 request_message_id / response_message_id
  │  处理 data: {"v": {"response": {...}}} → 首个响应事件
  │  处理 data: {"p":"response/fragments/-1/content","o":"APPEND","v":"..."}
  │  处理 data: {"v":"token"} → 纯 token 事件
  │  处理 data: {"p":"response/status"} → 状态变更
  ▼
server.py: event_stream() / _handle_nonstream()
  │  adapter 产出 → str (普通token) 或 dict (control/thinking/status)
  │  StreamSieve 筛分工具调用
  │  非流式 → 组装完整 JSON 响应
  │  流式 → yield OpenAI SSE chunk
  ▼
客户端收到 OpenAI 格式响应
```

### 3.2 数据格式转换

```
客户端发送 → OpenAI JSON → server.py 转成纯文本 prompt
↓
adapter.py 发送 → DeepSeek SSE → adapter.py 解析为 token 流
↓
server.py 接收 → token 流 → 组装 OpenAI SSE chunk
↓
客户端收到 → OpenAI JSON
```

---

## 4. PoW 反爬机制

### 4.1 原理

DeepSeek Chat 的 API 使用 Proof of Work 防止滥用。每次请求前必须先求解一个哈希难题。

**约束条件：**
- challenge 有 `expire_at`（Unix 时间戳），过期后不可用
- 每个 challenge 仅对指定 `target_path` 有效
- 难度通过 `difficulty` 参数控制（浮点数，越大越难）
- 签名验证机制确保 challenge 不被篡改

### 4.2 通信流程

```
1. POST /api/v0/chat/create_pow_challenge
   → 请求体: {"target_path": "/api/v0/chat/completion"}
   → 响应体: {
       "data": {
         "biz_data": {
           "challenge": {
             "algorithm": "DeepSeekHashV1",
             "challenge": "53251cf4a7b50ee99952f509374be35b",
             "salt": "ca1264f7b684cbfb7c1a",
             "signature": "33503f082bfd15492d17755c3781ba1b...",
             "difficulty": 262140,
             "expire_at": 1778077771,
             "target_path": "/api/v0/chat/completion"
           }
         }
       }
     }

2. WASM 求解 nonce
   - 输入: challenge, salt, expire_at, difficulty
   - 输出: nonce (int) — 满足难度条件的值
   
3. 构造 PoW Token
   → base64(json({"algorithm":"DeepSeekHashV1","challenge":...,"salt":...,"answer":<nonce>,"signature":...,"target_path":...}))
   → 放入请求头: X-DS-PoW-Response
```

### 4.3 WASM 求解器 (`_WASMSolver`)

`_WASMSolver` 封装 wasmtime 运行时，加载 DeepSeek 官方 WASM 二进制。

**WASM 导出函数：**
| 函数 | 参数 | 说明 |
|------|------|------|
| `wasm_solve` | (stack_ptr, chal_ptr, chal_len, prefix_ptr, prefix_len, difficulty) | 核心求解函数 |
| `memory` | — | WASM 线性内存 |
| `__wbindgen_add_to_stack_pointer` | offset | WASM 栈指针调整 |
| `__wbindgen_export_0` | (len, align) → ptr | WASM 内存分配（malloc） |
| `__wbindgen_export_1` | (ptr, old_len, new_len, align) → ptr | WASM 内存重分配（realloc） |
| `__wbindgen_export_2` | (ptr, len, align) | WASM 内存释放（free） |

**导出函数验证：** 三个 wasm-bindgen 导出函数的签名通过 wasmtime API 程序化验证：
- `export_0` (malloc): 2个 i32 参数 → 返回 i32（ptr）
- `export_1` (realloc): 4个 i32 参数 → 返回 i32（ptr）
- `export_2` (free): 3个 i32 参数 → 无返回值（void）

**内存管理：** `_encode()` 每次调用通过 `malloc` 分配 WASM 内存，分配记录在 `_allocations` 列表中。`solve()` 的 `finally` 块中通过 `__wbindgen_export_2` 释放所有分配。确保即使求解失败也不会内存泄漏。

**线程安全：** 使用 `threading.Lock` 保护 `solve()` 方法。WASM `Store` 实例不可跨线程共享，但通过锁确保同一时刻只有一个线程操作 `Store`。在 FastAPI 的多线程 ASGI 模式下（如使用多个 uvicorn worker），每个 worker 有独立的 `DeepSeekAdapter` 和 `_WASMSolver` 实例，互不干扰。

**求解算法（`solve` 方法）：**
```
prefix = salt + "_" + expire_at + "_"
stack_ptr = add_to_stack(-16)         // 为返回值分配栈空间
chal_ptr, chal_len = encode(challenge) // 将 challenge 写入 WASM 内存
prefix_ptr, prefix_len = encode(prefix) // 将 prefix 写入 WASM 内存
wasm_solve(stack_ptr, chal_ptr, chal_len, prefix_ptr, prefix_len, difficulty)
// 从栈上读取结果:
//   bytes[stack_ptr:stack_ptr+4] → 成功标志 (0=失败)
//   bytes[stack_ptr+8:stack_ptr+16] → nonce (f64)
add_to_stack(16)                       // 恢复栈指针
```

**崩溃安全：** WASM 求解失败（`ret == 0`）时抛出 `PoWError`，调用方需重试整个流程。

### 4.4 性能

- 单次求解约 0.1-0.3s（取决于 difficulty）
- `_WASMSolver` 实例被 `DeepSeekAdapter` 懒加载且复用（单例）
- WASM `Store` 实例不可跨线程共享，但本项目为单线程运行

### 4.5 局限性

- 算法为 DeepSeek 定制版 `DeepSeekHashV1`（修改版 Keccak/SHA3）
- WASM 二进制 `sha3_wasm_bg.wasm` 从 DeepSeek 前端提取，可能随前端更新而变化
- 某些情况下 challenge 可能返回空或格式变更，需 `_get_challenge` 的错误处理

---

## 5. 会话管理

### 5.1 设计决策：无状态

**核心决策：** 每次 API 请求都创建全新 DeepSeek 会话，请求结束后不保留上下文。

**原因：**
- 对齐 OpenAI API 行为：客户端通过完整 `messages` 数组管理上下文
- 简化服务端状态管理：无需处理会话过期、并发冲突
- DeepSeek 会话有 TTL（约 259200 秒/3 天），维持活跃会增加复杂度

### 5.2 Session 创建

```python
# adapter.py
def create_session(self) -> str:
    headers = self._pow_headers("/api/v0/chat/completion")
    resp = self._client.post(
        f"{BASE_URL}/api/v0/chat_session/create",
        json={"target_path": "/api/v0/chat/completion"},
        headers=headers,
    )
    data = resp.json()
    # 响应格式分两种（取决于 X-App-Version）:
    #   V0.0.1: biz_data.id
    #   V20241129.1: biz_data.chat_session.id
```

**响应格式兼容性**（历史观察：早期 `X-App-Version` 不同值时 create_session 返回两种格式；当前适配器 `create_session()` 对两种格式均兼容，见 5.2）：

旧版本头 (`X-App-Version: 0.0.1`)：
```json
{"data": {"biz_data": {"id": "session-uuid"}}}
```

新版本头 (`X-App-Version: 20241129.1`)：
```json
{"data": {"biz_data": {"chat_session": {"id": "session-uuid", "model_type": "default", ...}}}}
```

### 5.3 Session 存储

```python
# server.py — 内存 dict
_sessions: dict[str, str] = {}
# key:   proxy session UUID (由 server.py 生成)
# value: DeepSeek session ID (由 adapter.create_session() 返回)
```

`_get_session()` 生成代理 session ID，调用 adapter 创建真实 session，建立映射。
`_get_ds_session()` 根据代理 session ID 查找真实 session。

### 5.4 消息 ID 追踪

对于专家模式，每个会话内的消息需要递增 `parent_message_id`。

```python
# adapter.py
self._msg_counters: dict[str, int] = {}  # key: session_id, value: count
```

- 每次 `_send_completion` 调用时自增
- 首次请求: `parent_message_id: null`
- 后续请求: `parent_message_id: 1, 2, 3...`

**注意：** 当前 session-per-request 设计下，`parent_message_id` 始终为 `null`（因为每次都是新 session 的第一条消息）。但保留递增逻辑以支持未来的会话复用。如果将来改为复用 session，`parent_message_id` 将变为必需——DeepSeek 服务端用它来关联上下文。

### 5.5 Session 存储策略

当前 `_sessions` 使用**简单的内存 dict**：

```python
# server.py
_sessions: dict[str, str] = {}
```

每次请求创建一个新 session（`_get_session()`），键值对保留在字典中。历史上曾尝试添加 TTL 自动清理，但由于以下原因**选择不实现**：
- session-per-request 设计下，单个请求生命周期极短，session 不会被复用
- DeepSeek 服务端的 session TTL 约 3 天（259200s），旧 session ID 无实际危害
- Python dict 的内存效率足以应付常规负载（100 万次请求约 150MB）
- 增加清理逻辑增加了代码复杂度，且对正确性无帮助

---



## 6. SSE 协议格式

### 6.1 DeepSeek 自定义 SSE

DeepSeek Chat 使用自定义 SSE 格式（非标准 OpenAI SSE）。每条数据行形如：

```
event: ready   ← 可选事件类型
data: {...}    ← JSON 数据
```

**核心数据结构：**

事件以 JSON 格式在 `data:` 行传输，常见结构：

```
A. 普通 token:    {"v": "Hello"}
B. 操作事件:      {"p": "response/content", "o": "APPEND", "v": "World"}
C. 响应元数据:    {"v": {"response": {"message_id": 4, ...}}}
D. 状态变更:      {"p": "response/status", "o": "SET", "v": "FINISHED"}
E. 批量更新:      {"p": "response", "o": "BATCH", "v": [...]}
F. 准备事件:      {"request_message_id": 1, "response_message_id": 2, "model_type": "expert"}
```

### 6.2 事件类型详解

#### type A: 纯 token 事件
```json
{"v": "Hello"}
```
- 无 `p` 和 `o` 字段
- `v` 值为字符串 → 追加到当前 fragment 的内容
- 在快速模式中等效为普通回复内容
- 在专家模式中，归属由当前 `frag_type` 状态决定

#### type B: 操作路径事件
```json
{"p": "response/content", "o": "APPEND", "v": "World"}
```
- `p`: 路径（类比文件系统路径）
- `o`: 操作（APPEND/SET/BATCH）
- `v`: 值

常见路径和操作组合：

| `p` | `o` | `v` 类型 | 含义 |
|-----|-----|---------|------|
| `response/content` | `APPEND` | string | 快速模式内容追加 |
| `response/fragments/-1/content` | `APPEND` | string | 专家模式当前 fragment 内容追加 |
| `response/fragments/-1/content` | — | string | 无操作字段时同上 |
| `response/fragments/-1/elapsed_secs` | `SET` | number | fragment 耗时 |
| `response/fragments` | `APPEND` | array | 新 fragment 追加（切换类型） |
| `response/status` | `SET` | string | 状态变更（FINISHED 等） |
| `accumulated_token_usage` | `SET` | number | token 用量 |
| `response` | `BATCH` | array | 批量更新（多个 `{p,v}` 对） |

#### type C: 响应元数据
```json
{"v": {"response": {"message_id": 4, "parent_id": 3, "fragments": [...], "thinking_enabled": true, ...}}}
```
- 出现在 SSE 流的早期（首个 data 事件）
- 包含完整的响应元数据：message_id、parent_id、fragments、状态等
- `fragments` 数组包含初始片段信息
- `status: "WIP"` 表示生成中，`"FINISHED"` 表示完成

#### type D: 准备事件（event: ready）
```
event: ready
data: {"request_message_id": 1, "response_message_id": 2, "model_type": "expert"}
```
- 仅在 `event: ready` 行之后出现
- 告知请求/响应的 message_id 映射关系
- `model_type` 指示实际使用的模型类型（`"default"` 或 `"expert"`）

### 6.3 快速模式 SSE 事件序列

```
event: ready
data: {"request_message_id":1,"response_message_id":2,"model_type":"default"}

event: update_session
data: {"updated_at": ...}

data: {"v": {"response": {"message_id":2, "status":"WIP", "content":"", ...}}}

data: {"p":"response/content","o":"APPEND","v":"Hello"}
data: {"v":" World"}
data: {"v":"!"}
data: {"p":"response/status","o":"SET","v":"FINISHED"}

event: update_session
data: {"updated_at": ...}

event: close
data: {"click_behavior":"none","auto_resume":false}
```

### 6.4 专家模式 SSE 事件序列

专家模式使用 **Fragment 系统**，响应内容由多个 fragment 组成（THINK → RESPONSE）。

```
event: ready
data: {"request_message_id":1,"response_message_id":2,"model_type":"expert"}

event: update_session
data: {"updated_at": ...}

// 初始化响应，带 fragments[0] = THINK
data: {"v":{"response":{"message_id":2, "fragments":[{"id":2,"type":"THINK","content":"初始思考内容"}], "thinking_enabled":true, ...}}}

// 思考阶段的 token（归属当前 THINK fragment）
data: {"v":"思考"}
data: {"p":"response/fragments/-1/content","o":"APPEND","v":"的过程"}
data: {"v":"中的推理"}

// fragment 切换：追加 RESPONSE 片段
data: {"p":"response/fragments","o":"APPEND","v":[{"id":3,"type":"RESPONSE","content":"","references":[],"stage_id":1}]}
data: {"p":"response/fragments/-1/elapsed_secs","o":"SET","v":7.21}

// 正式回答阶段的 token（归属 RESPONSE fragment）
data: {"p":"response/fragments/-1/content","v":"最终"}
data: {"v":"回答"}
data: {"v":"内容"}

// 批量更新（token 用量 + 状态）
data: {"p":"response","o":"BATCH","v":[{"p":"accumulated_token_usage","v":457},{"p":"quasi_status","v":"FINISHED"}]}

// 最终状态
data: {"p":"response/status","o":"SET","v":"FINISHED"}

event: update_session
data: {"updated_at": ...}

event: close
data: {"click_behavior":"none","auto_resume":false}
```

### 6.5 Fragment 类型

| 类型 | 含义 | 包含内容 |
|------|------|---------|
| `THINK` | 推理/思考过程 | 模型的内部推理链，用户可见 |
| `RESPONSE` | 最终回答 | 面向用户的正式回复 |
| `TEXT` | 文本片段 | 通用文本（少见） |

### 6.5 SSE 事件类型参考

#### `event: ready`

SSE 流中的第一个事件，携带请求/响应的 message_id 映射：

```
event: ready
data: {"request_message_id": 1, "response_message_id": 2, "model_type": "expert"}
```

- `request_message_id` — DeepSeek 服务端分配的请求 ID
- `response_message_id` — DeepSeek 服务端分配的响应 ID（后续的 `{"v": {"response": {...}}}` 中的 `message_id` 与此一致）
- `model_type` — 实际使用的模型类型（`"default"` 或 `"expert"`），与请求体中的 `model_type` 一致

#### `event: update_session`

会话更新事件，在关键节点（响应开始、响应结束）之间出现：

```
event: update_session
data: {"updated_at": 1778077771}
```

- 通常出现两次：一次在 ready 之后，一次在 close 之前
- `updated_at` 是服务端更新会话时间戳
- 当前实现中**忽略此事件**，不执行任何操作

#### `event: close`

SSE 流结束事件：

```
event: close
data: {"click_behavior": "none", "auto_resume": false}
```

- `click_behavior` — 网页端点击行为（"none" 或 "resume"）
- `auto_resume` — 是否自动恢复
- 当前实现中**忽略此事件**，不执行任何操作
- 流关闭后不应再有 data 行

#### `BATCH` 操作类型

operation 值为 `"BATCH"` 时，`v` 是一个数组，包含多个 `{p, v}` 对：

```json
{"p": "response", "o": "BATCH", "v": [
  {"p": "accumulated_token_usage", "v": 457},
  {"p": "quasi_status", "v": "FINISHED"}
]}
```

BATCH 中常见的 `p` 值：

| 路径 | v 类型 | 含义 |
|------|--------|------|
| `accumulated_token_usage` | number | 累积 token 用量 |
| `quasi_status` | string | 准状态（"FINISHED" 等） |
| `response/fragments/-1/elapsed_secs` | number | 当前 fragment 耗时 |
| `response/status` | string | 状态（"WIP", "FINISHED"） |
| `response/content` | string | 完整或增量内容 |

BATCH 通常在快速模式中出现，专家模式中使用较少。当前实现中对 BATCH 事件**不做特殊处理**（没有对应的解析分支），但非流式模式通过 `_parse_sse()` 捕获所有事件。

#### `accumulated_token_usage`

出现在 BATCH 或独立 SET 事件中，代表当前已消耗的 token 总数（注意：不是本次响应的完整数量，而是累积值）。当前未作为 `usage` 返回给客户端（`server.py` 的 `usage` 字段硬编码为 `-1`）。

#### `quasi_status`

DeepSeek 内部使用的状态字段，与 `response/status` 同步。值为 `"FINISHED"` 时表示响应结束。当前实现中不处理此字段，依赖 `response/status SET` 事件。

### 6.6 非流式 SSE 解析器 `_parse_sse()`

`adapter.py` 的 `_parse_sse()` 用于非流式模式，与 `chat_stream()` 的流式解析器有几点不同：

| 特性 | `_parse_sse()` (非流式) | `chat_stream()` (流式) |
|------|------------------------|----------------------|
| 输入 | 完整响应文本 (str) | `resp.iter_lines()` 生成器 |
| 解析时机 | 一次性解析所有事件 | 逐行实时处理 |
| event 追踪 | 追踪 `current_event` 但未使用 | 追踪 `current_event` 但未使用 |
| JSON 失败处理 | 存储原始字符串 | 跳过该行 |
| 输出 | `list[(event_type, data)]` | `yield str/dict` |
| Fragment 状态机 | 在 `chat()` 中实现（遍历事件列表） | 内联在解析循环中 |

`_parse_sse()` 是一个**通用解析器**，不关心具体业务逻辑。fragment 状态机等业务逻辑在调用方（`chat()`）中实现。这是与流式模式的架构差异——流式模式在解析循环中直接嵌入状态机。

---

## 7. MODE / THINKING / SEARCH 控制系统

### 7.1 设计思路

DeepSeek 的 API 有三个独立参数控制模型行为：
- **`model_type`**: `"default"`（快速模式）或 `"expert"`（专家模式）
- **`thinking_enabled`**: `true/false` — 是否输出推理过程
- **`search_enabled`**: `true/false` — 是否启用联网搜索

**关键认知：这三个参数完全独立。**

历史版本曾错误地将 `thinking_enabled=true` 等同于专家模式。实际 `model_type="default"`（快速模式）+ `thinking_enabled=true` 也是有效组合——快速模式可以同时开启思考。同样，`search_enabled` 与 `model_type`、`thinking_enabled` 完全独立。

项目通过三个 `.env` 环境变量暴露这三个自由度：

| 环境变量 | 控制参数 | 可选值 |
|---------|---------|-------|
| `MODE` | `model_type` | `auto` / `quick` / `expert` |
| `THINKING` | `thinking_enabled` | `auto` / `enabled` / `disabled` |
| `SEARCH` | `search_enabled` | `auto` / `enabled` / `disabled` |

`auto` 表示"由客户端 request 中的对应字段决定"，非 `auto` 值会覆盖客户端传参。

### 7.2 实现方式（`server.py`）

```python
# server.py 模块级
MODE = os.environ.get("MODE", "auto").strip().lower()
THINKING = os.environ.get("THINKING", "auto").strip().lower()
SEARCH = os.environ.get("SEARCH", "auto").strip().lower()

# chat_completions() 中
if MODE == "expert":
    model_type = "expert"
else:  # "quick" 或 "auto"
    model_type = "default"

if THINKING == "enabled":
    thinking = True
elif THINKING == "disabled":
    thinking = False
else:  # "auto"
    thinking = req.thinking_mode or False

if SEARCH == "enabled":
    search = True
elif SEARCH == "disabled":
    search = False
else:  # "auto"
    search = req.search_enabled or False
```

注意 `model_type` 在非 `MODE=expert` 时设为 `"default"`（非 `None`）。这与 DeepSeek 原生请求格式一致。

### 7.3 八种组合及 OpenAI SSE 行为

| MODE | THINKING | SEARCH | model_type | thinking_enabled | search_enabled | 实际效果 |
|------|----------|--------|------------|-----------------|---------------|---------|
| quick | disabled | auto | `"default"` | `false` | 由客户端 | 快速模式，无思考 |
| quick | enabled | disabled | `"default"` | `true` | `false` | 快速模式 + 思考，关闭搜索 |
| quick | enabled | enabled | `"default"` | `true` | `true` | 快速 + 思考 + 搜索 |
| expert | disabled | auto | `"expert"` | `false` | 由客户端 | 专家模式，无思考 |
| expert | enabled | auto | `"expert"` | `true` | 由客户端 | 完整专家模式 |
| expert | enabled | enabled | `"expert"` | `true` | `true` | 专家 + 思考 + 搜索 |
| auto | auto | auto | `"default"` | `req.thinking_mode` | `req.search_enabled` | 完全由客户端决定 |
| quick | auto | enabled | `"default"` | `req.thinking_mode` | `true` | 快速模式 + 强制搜索 |

所有组合均已通过原始 SSE 抓包验证。

**MODE=auto 时的回退行为：**
- MODE=auto → model_type="default"（快速模式）
- THINKING=auto → thinking = req.thinking_mode or False
- SEARCH=auto → search = req.search_enabled or False

### 7.4 SEARCH 环境变量详解

`SEARCH` 控制 `search_enabled` 参数，决定模型是否可以联网搜索实时信息。

| 值 | 效果 | search_enabled |
|----|------|---------------|
| `auto` | 由客户端请求中的 `search_enabled` 决定 | `req.search_enabled or False` |
| `enabled` | 强制开启联网搜索 | `True` |
| `disabled` | 强制关闭联网搜索 | `False` |

**注意：**
- `search_enabled` 只是告知模型"可以联网搜索"，模型自主决定是否需要搜索
- 搜索结果以 `[citation:N]` 引用标记形式出现在回复中，这些标记会被 `_clean_dsml_text()` 自动去除
- 该参数与 `model_type`、`thinking_enabled` 完全独立，所有 2×2×2=8 种组合均有效

### 7.5 "快速模式 + 思考" 的 SSE 格式

快速模式也使用 Fragment 系统（无需 `model_type: "expert"`），所以 SSE 格式与专家模式无异：

```
// 初始响应带 fragments[0] = THINK
data: {"v":{"response":{"fragments":[{"type":"THINK","content":"思考过程..."}],...}}}

// 思考 token
data: {"v":"思考"}
data: {"p":"response/fragments/-1/content","o":"APPEND","v":"推理中"}

// 切换到 RESPONSE
data: {"p":"response/fragments","o":"APPEND","v":[{"type":"RESPONSE",...}]}

// 内容 token
data: {"v":"最终"}

// 结束
data: {"p":"response/status","o":"SET","v":"FINISHED"}
```

### 7.6 Expert Mode（专家模式）核心区别

当 `model_type="expert"` 时，除 MODE 控制外，还有以下额外差异：

| 维度 | 快速模式 | 专家模式 |
|------|---------|---------|
| `model_type` | `"default"` | `"expert"` |
| SSE 内容格式 | 同上（均可能用 fragments） | 同上（均可能用 fragments） |
| Fragment 系统 | 可选（模型自主决定） | 一定有 THINK → RESPONSE |
| `reasoning_content` | 取决于 THINKING | 取决于 THINKING |
| 请求头要求 | 宽松 | 需 `X-Client-Version: 2.3.0` 等（见 7.7） |

实际上 DeepSeek 的快速模式和专家模式在 SSE 协议层差异极小，`model_type` 主要影响模型的选择与其推理深度。

### 7.7 请求头要求（2026-08 现状）

从 HAR 抓包（2026-08-02，浏览器 Chrome 150）确认的当前请求头：

```
X-Client-Version: 2.3.0          ← 当前浏览器版本（旧 2.0.0 时代已过）
X-Client-Platform: web
X-Client-Locale: zh_CN
X-Client-Timezone-Offset: 28800
x-client-bundle-id: com.deepseek.chat
X-Hif-Leim / X-Hif-Dliq          ← 签名头（v3.2.2 起 adapter 通过 _HifProvider 自动发送，见 7.13）
```

**`X-App-Version` 已废弃**：2026-08 真实浏览器不再发送该头（旧版本 `20241129.1`/`2.0.0` 时代已过）。adapter 自 v3.2.0 起已删除该头。

> 历史：v2.x 时代 `X-App-Version: 0.0.1` 会导致服务端返回 `"Update to the latest version to use Expert."`（toast 事件，v3.2.0 已解析透出）。当前上游的"版本过旧"判断主要基于 `X-Client-Version`。

其他浏览器自动发送的 `sec-ch-ua`、`sec-fetch-*` 头未被严格校验（但 TLS/JA3 指纹疑似被检测——自动化指纹（curl_cffi/tls-client）在高频时会被上游限流，见 v3.2.1 摘要）。

### 7.8 状态机（`chat_stream` 中的 `frag_type`）

```python
frag_type = None  # 状态: None | 'thinking' | 'content'
```

状态转换：

```
[初始] None
  │
  ├─ 收到响应中 fragments[0].type == "THINK" → frag_type = "thinking"
  │    │
  │    ├─ 收到 "response/fragments APPEND" 且 type="RESPONSE" → frag_type = "content"
  │    │    │
  │    │    └─ 后续 token 作为 content 发出
  │    │
  │    └─ 期间所有 token 作为 __type="thinking" 发出
  │
  └─ 收到响应中 fragments 为空或无 THINK → frag_type = "content"
```

状态机在两种模式下都运行——无论是 `model_type="default"`（快速模式）还是 `model_type="expert"`（专家模式），DeepSeek 都可能返回 THINK fragment。区别在于专家模式下 THINK fragment 几乎一定会出现，而快速模式下由模型自主决定。

### 7.9 SSE `reasoning_content` 字段

OpenAI 的 Stream Options 中，`reasoning_content` 是一个非标准但被多个厂商使用的字段（DeepSeek 官方 API、OpenAI o1 等）。本项目在流式输出中：

1. **首个 thinking token 时发出 `{"reasoning_content": ""}`**（空帧，标志着 thinking 开始）
2. 后续每个 thinking token 发出 `{"reasoning_content": "..."}`
3. 切换到 content 阶段后恢复 `{"content": "..."}`
4. **流结束时发出 `{"finish_reason": "stop"}`**（§7.10）

**空 `reasoning_content: ""` 的陷阱：**

初始版本无条件在首次 content 前发射空帧。当 THINKING=disabled 时，这个空帧被部分客户端（如 Claude Code）解释为"响应只有空 reasoning"，导致 `parts: []`、`finish: "other"`——整个回复消失。

**修复（2026-05-06）：** 在流式处理中，`reasoning_content: ""` 只会在满足以下条件时发射：
1. 正在处理 thinking token（`adapter` 产出 `__type:"thinking"` 字典）→ 无条件发射（已在 thinking 流程中，合理）
2. 正在处理 content token 且 `role_sent=False` → **仅当 `thinking_mode=True` 时发射**

```python
# server.py _handle_stream event_stream()

# Thinking 路径：无条件发射空帧（因为已经在 thinking 块里）
if not role_sent:
    yield _openai_chunk(proxy_id, reasoning_content="")
    role_sent = True
yield _openai_chunk(proxy_id, reasoning_content=content)

# Text 路径：只有 thinking_mode=True 时才发射空帧
if not role_sent:
    if thinking_mode:
        yield _openai_chunk(proxy_id, reasoning_content="")
    role_sent = True
yield _openai_chunk(proxy_id, content=evt.data)
```

### 7.10 `finish_reason: "stop"` 结束帧

**问题：** 流式响应中缺少 `finish_reason` 结束帧。标准 OpenAI SSE 格式要求在 `[DONE]` 之前发送一个空 delta + `finish_reason`：

```json
data: {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}

data: [DONE]
```

原代码只在 tool_calls 路径中由 `_emit_tool_calls_chunks` 发送了 `finish_reason: "tool_calls"`，而正常结束路径直接发 `[DONE]`，缺少 `finish_reason: "stop"`。

**影响：** 部分客户端将缺少 `finish_reason` 的流标记为 `finish: "other"`，可能导致响应处理异常（如只取到 reasoning 部分、不显示 content 等）。

**修复（2026-05-07）：** 在正常结束路径添加：

```python
yield _openai_chunk(proxy_id, finish=True)
yield "data: [DONE]\n\n"
```

`_openai_chunk(proxy_id, finish=True)` 产出：
```json
{"delta": {}, "finish_reason": "stop"}
```

**涉及位置：** 1 处（正常结束路径）。tool_calls 路径（3 处）已有 `finish_reason: "tool_calls"`，无需修改。

### 7.11 非流式模式的限制

`adapter.chat()` 在非流式模式下只返回 `response/content` 或 `response/fragments/-1/content` 中的 **RESPONSE 部分内容**。THINK 内容不会在返回值中包含。这是因为非流式模式下：

- 如果使用 `response/content APPEND`，内容已包含最终回复
- 如果使用 fragments 方式，`chat()` 只收集 RESPONSE fragment 的内容

如需要非流式模式同时返回 thinking 和 content，需修改 `chat()` 方法支持结构化返回。

### 7.12 请求体字段详解

完整请求体包含以下字段（`adapter.py:171-181`）：

```json
{
  "chat_session_id": "<session-uuid>",
  "parent_message_id": null,
  "model_type": "default",
  "prompt": "User: 你好",
  "ref_file_ids": [],
  "stream": true,
  "thinking_enabled": false,
  "search_enabled": false,
  "preempt": false
}
```

| 字段 | 类型 | 快速模式 | 专家模式 | 说明 |
|------|------|---------|---------|------|
| `chat_session_id` | string | 必填 | 必填 | `create_session()` 返回的会话 ID |
| `parent_message_id` | int/null | null | null | 上一条消息的 ID，首条为 null |
| `model_type` | string | `"default"` | `"expert"` | **关键开关**，由 MODE 环境变量决定 |
| `prompt` | string | 必填 | 必填 | 拼接后的纯文本 prompt |
| `ref_file_ids` | list | `[]` | `[]` | 文件引用 ID，始终为空（不支持文件上传） |
| `stream` | bool | 按需 | 按需 | 服务端 SSE 流式开关 |
| `thinking_enabled` | bool | 由 THINKING 决定 | 由 THINKING 决定 | 启用推理过程输出 |
| `search_enabled` | bool | 由 SEARCH 决定 | 由 SEARCH 决定 | 启用联网搜索 |
| `preempt` | bool | false | false | 抢占模式，始终为 false |

**`model_type`、`thinking_enabled`、`search_enabled` 的协作：**

| 场景 | model_type | thinking_enabled | search_enabled | 说明 |
|------|-----------|-----------------|---------------|------|
| 纯快速模式 | `"default"` | `false` | `false` | 基础模式 |
| 快速+思考 | `"default"` | `true` | `false` | 快速响应但附带推理过程 |
| 快速+搜索 | `"default"` | `false` | `true` | 快速响应 + 联网搜索 |
| 专家无思考 | `"expert"` | `false` | `false` | 专家模型但不输出推理（罕见） |
| 完整专家 | `"expert"` | `true` | `true` | 专家模型 + 完整推理 + 联网搜索 |

#### `preempt` 字段

`preempt: false` 表示不抢占当前正在进行的响应。如果设为 `true`，理论上可以中断同一会话中正在生成的回复并开始新回复。当前实现始终为 `false`。误设为 `true` 可能导致未定义行为。

#### `ref_file_ids` 字段

DeepSeek Chat 网页版支持上传文件（如图片、PDF），上传后文件会获得一个 ID，通过此字段附加到对话中。当前适配器不支持文件上传，因此始终传空数组。如需要实现，需要：
1. 额外端点：文件上传 → 获取 file_id
2. 将 file_id 传入 `ref_file_ids`
3. 清理服务端的文件关联

#### `search_enabled` 行为

`search_enabled: true` 告诉 DeepSeek 模型在需要时可以联网搜索。此参数透传给服务端后：
- 服务端决定是否搜索（模型自主判断）
- 搜索结果会以 `[citation:N]` 形式出现在回复中
- 当前实现中 `_clean_dsml_text()` 会去除 `[citation:N]` 标记
- 目前在联网模式下**未大规模测试**，被标记为 ⚠️ 状态

#### `stream` 字段行为

注意 `stream` 在 `adapter.py` 和 `server.py` 中的含义不同：
- **adapter 层**：`stream=True` 时服务端以 SSE 流返回；`stream=False` 时一次性返回完整响应体
- **server 层**：streaming 由 `server.py` 的路由选择 `_handle_stream` 还是 `_handle_nonstream`，但内部始终调用 `adapter.chat_stream()`（流式）或 `adapter.chat()`（非流式），不存在 "用非流式 adapter 实现流式 server" 的路径

### 7.13 透传参数全景：客户端 → server → 上游 DeepSeek

> 本节回答一个问题：**客户端发的每个字段，最终以什么形态、什么值打到 `chat.deepseek.com` 上游**。所有信息对应 `adapter.py` 实际代码（请求体构造、`_base_headers`）。

#### 上游三个端点（BASE_URL = `https://chat.deepseek.com`）

| 端点 | 用途 | 请求体 |
|------|------|--------|
| `POST /api/v0/chat/create_pow_challenge` | 获取 PoW 挑战 | `{"target_path": "/api/v0/chat/completion"}` |
| `POST /api/v0/chat_session/create` | 创建会话 | `{"target_path": "/api/v0/chat/completion"}` |
| `POST /api/v0/chat/completion` | 对话（流式/非流式共用） | 见下 |

#### `/api/v0/chat/completion` 请求体（adapter 实际发送，逐字段）

| 字段 | 值来源 | 说明 |
|------|--------|------|
| `chat_session_id` | `create_session()` 返回 | 会话 UUID |
| `parent_message_id` | adapter `_msg_counters` 或 server 会话缓存 | 首条 `null`；多轮由 server 层 `SESSION_CACHE_TTL` 缓存回传 |
| `model_type` | server 决策（MODEL_ROUTES/MODE） | `"default"`（快速）\| `"expert"`（专家），**关键开关** |
| `prompt` | server `_build_prompt()` | 客户端 messages 拼接后的纯文本 |
| `ref_file_ids` | 固定 `[]` | 不支持文件上传 |
| `stream` | server 层 `req.stream` | `true`=SSE 流式 / `false`=一次性返回 |
| `thinking_enabled` | server 决策（THINKING/客户端） | 推理过程开关，**与 `model_type` 独立** |
| `search_enabled` | server 决策（SEARCH/客户端） | 联网搜索开关 |
| `preempt` | 固定 `false` | 抢占模式；勿设 `true`（未定义行为） |

#### 请求头（`_base_headers`，模拟真实浏览器）

| 头 | 值 |
|----|----|
| `User-Agent` / `Sec-Ch-Ua` / `Sec-Ch-Ua-Mobile` / `Sec-Ch-Ua-Platform` | Chrome 指纹（`DEEPSEEK_IMPERSONATE` 关联 curl_cffi 指纹） |
| `Accept` / `Accept-Encoding` / `Accept-Language` | 浏览器风格（`gzip, deflate, br, zstd` / `zh-CN,...`） |
| `Content-Type` | `application/json` |
| `Authorization` | `Bearer <DEEPSEEK_TOKEN>`（账号凭证） |
| `Origin` / `Referer` | `https://chat.deepseek.com/` |
| `Priority` | `u=1, i` |
| `Sec-Fetch-Dest` / `Sec-Fetch-Mode` / `Sec-Fetch-Site` | `empty` / `cors` / `same-origin` |
| `X-App-Version` / `X-Client-Version` | `2.0.0`（过低会被上游拒绝专家模式） |
| `X-Client-Platform` / `X-Client-Locale` / `X-Client-Timezone-Offset` | `web` / `zh_CN` / `28800` |
| `x-client-bundle-id` | `com.deepseek.chat` |
| `X-DS-PoW-Response` | **动态**：每次请求前求解，`base64(json PoW token)` |

#### 客户端参数 → 上游字段映射链

**OpenAI `/v1/chat/completions`：**

| 客户端字段 | server 决策（优先级从高到低） | 上游字段 |
|-----------|------------------------------|---------|
| `model` | `MODEL_ROUTES` 命中 → 对应 model_type；否则 `MODE=expert` → `"expert"`；否则 `"default"` | `model_type` |
| `thinking_mode` | `MODEL_ROUTES.thinking` → `THINKING=enabled/disabled` → 客户端 `thinking_mode` | `thinking_enabled` |
| `search_enabled` | `MODEL_ROUTES.search` → `SEARCH=enabled/disabled` → 客户端 `search_enabled` | `search_enabled` |
| `stream` | 直接 | `stream` |
| `temperature` / `top_p` / `max_tokens` | **读取后丢弃**，不参与透传 | — |
| `tools` / `tool_choice` | server 层转 DSML 注入 `prompt`（见第 8 章） | 不单独成字段 |

**Anthropic `/v1/messages`：**

| 客户端字段 | server 决策 | 上游字段 |
|-----------|------------|---------|
| `model` | 同 OpenAI | `model_type` |
| `thinking.type="enabled"` | 映射为 `thinking_mode` 再走同上链路 | `thinking_enabled` |
| `metadata.user_id` | 会话缓存键（`SESSION_CACHE_TTL`） | `parent_message_id`（多轮） |
| `system` / `messages` | `_build_prompt()` 拼接 | `prompt` |
| `max_tokens` / `stop_sequences` / `temperature` | **忽略** | — |

#### 环境变量优先级总结（最高 → 最低）

```
MODEL_ROUTES 命中（按 model 名）→ MODE / THINKING / SEARCH env → 客户端字段（thinking_mode / search_enabled）
```

`MODE`/`THINKING`/`SEARCH` 均为 `auto` 时，`model_type` 恒为 `"default"`、thinking/search 由客户端决定；`MODEL_ROUTES` 只影响匹配到的模型名，未匹配模型回退到 env 逻辑（见 7.12 协作表）。

---



## 8. 工具调用 (DSML)

### 8.1 原理

DeepSeek Chat 的 API 原生不支持 tool calling（function calling）。本项目通过 **DSML（DeepSeek Markup Language）提示词注入** 方案实现。

核心思想：将工具定义转化为文本指令注入 system message，让模型理解指令后以 XML 格式回复，再解析回 OpenAI 标准格式。

### 8.2 流程

```
客户端发送 tools 数组
  │
  ▼
server.py: build_dsml_tool_prompt(tools)
  │  将工具定义转为 DSML 格式文本：
  │  "You have access to tools. When you need to call a tool,
  │   respond with EXACTLY this format — no markdown fences...
  │   Available tools:
  │     get_weather: 获取指定城市的天气
  │     search_web: 搜索网络信息"
  │
  ▼ 注入到 system message
_build_prompt() 将 DSML 指令拼入 prompt 开头
  │
  ▼
DeepSeek 模型理解指令，可能以 DSML XML 回复：
  ├─ 正常回复 ("北京今天25度")
  └─ 工具调用 (<|DSML|tool_calls>...)
        │
        ▼
      流式: StreamSieve 实时检测 DSML 标签
      非流式: parse_dsml_tool_calls() 全量解析
        │
        ▼
      转为 OpenAI 标准 tool_calls 格式
```

### 8.3 DSML XML 格式

```xml
<|DSML|tool_calls>
  <|DSML|invoke name="get_weather">
    <|DSML|parameter name="city"><![CDATA[北京]]></|DSML|parameter>
  </|DSML|invoke>
</|DSML|tool_calls>
```

注意事项：
- 每个 `parameter` 的 value 如果为字符串，必须使用 CDATA 包裹
- 数值、布尔值、null 直接以文本形式写入
- 不支持嵌套对象（使用 JSON.stringify 后以 CDATA 传递）
- `invoke` 的 `name` 属性需要 XML 转义（`&` > `&amp;` 等）

### 8.4 DSML 解析 (`tool_dsml.py`)

**`strip_dsml_markup(text)`** — 去除 `|DSML|` 前缀，保留纯 XML 结构。逐字符扫描，处理 CDATA 内容和 `|DSML|` 前缀标签。

**`parse_dsml_tool_calls(text, tool_names)`** — 从文本中提取工具调用。

解析策略：
1. 调用 `strip_dsml_markup()` 标准化文本
2. 匹配 `<tool_calls>...</tool_calls>` 或 `<tool_call>...</tool_call>` 块
3. 无外层 wrapper 时直接匹配裸 `<invoke>`
4. 每个 invoke 内的 `<parameter>` 提取参数
5. 参数值尝试 JSON.parse，失败后用 `_auto_type` 智能转换

**`_auto_type(val)`** — 智能类型推断：

| 输入 | 输出 |
|------|------|
| `"true"` | `True` (bool) |
| `"false"` | `False` (bool) |
| `"null"`, `"none"` | `None` |
| `"42"` | `42` (int) |
| `"3.14"` | `3.14` (float) |
| `"hello"` | `"hello"` (str) |

**`format_tool_calls_for_prompt(tool_calls_raw)`** — 将 OpenAI tool_calls 转回 DSML 格式，用于历史消息回传。

**`build_dsml_tool_prompt(tools)`** — 生成工具指令提示词。

### 8.5 工具调用历史回传

多轮对话中，如果之前的 assistant 回复包含工具调用，需要在下一轮请求时将其转回 DSML 格式并拼入 prompt：

```
Assistant: 让我查一下天气。 format_tool_calls_for_prompt(...)
Tool result: {"temperature": 25}
User: 那湿度呢？
```

`_build_prompt()` 中处理 `assistant` 角色的 `tool_calls` 字段，通过 `format_tool_calls_for_prompt()` 转为 DSML 格式附加到消息文本后。

### 8.6 已知限制

- **不支持并行工具调用**：每次只能调用一个工具
- **`tool_choice` 不可靠**：模型可能选择不调用工具
- **格式不稳定**：依赖模型按 DSML 格式精确输出，少标签或多空格都可能导致解析失败
- **DSML 解析失败回退**：如果 DSML 解析失败，工具调用内容会被清理后作为普通文本返回

### 8.7 DSML 内部函数参考

#### `extract_cdata(text)` — CDATA 提取

```python
def extract_cdata(text: str) -> str:
    text = text.strip()
    if text.startswith("<![CDATA[") and text.endswith("]]>"):
        return text[len("<![CDATA["):-len("]]>")]
    return text
```

从参数值文本中提取 CDATA 包裹的内容。如果文本不是 CDATA 格式，原样返回。

#### `_auto_type(val)` — 智能类型推断

用于将 DSML 参数中的字符串值转换为 Python 原生类型。转换优先级：

1. 布尔值：`"true"` → `True`，`"false"` → `False`
2. Null：`"null"`, `"none"` → `None`
3. 整数：`"42"` → `42`
4. 浮点数：`"3.14"` → `3.14`
5. 字符串：其他情况原样返回

**注意：** 此函数在 CDATA 提取后调用。如果参数值已经以 JSON 格式传入（即 `json.loads` 成功），则优先使用 JSON 解析结果。`_auto_type` 仅在 JSON 解析失败时作为 fallback。

#### `_clean_dsml_text(text)` — 清理 DSML 标记

从文本中去除所有 DSML 相关标记，返回纯净文本。执行以下清理：

| 步骤 | 正则/操作 | 清理目标 |
|------|----------|---------|
| 1 | `<tool_calls>...</tool_calls>` | 工具调用外层包装 |
| 2 | `<invoke ...>...</invoke>` | 单个工具调用 |
| 3 | `<parameter ...>...</parameter>` | 参数声明 |
| 4 | `<![CDATA[...]]>` | CDATA 标记 |
| 5 | `[citation:N]` | DeepSeek 联网搜索引用标记 |
| 6 | 3 个以上连续换行 → 2 个 | 空白行压缩 |

**`[citation:N]` 引用标记：** 当 `search_enabled: true` 时，DeepSeek 可能在回复中插入引用标记如 `[citation:1]`。这些标记对用户无意义（无法跳转），故统一去除。

#### `format_tool_calls_for_prompt()` — 工具调用历史回传

将 OpenAI 格式的 tool_calls 转回 DSML 格式，用于多轮对话。输入兼容以下格式：

```json
// 格式 A: OpenAI 标准
{"id": "call_xxx", "type": "function", "function": {"name": "get_weather", "arguments": "{\"city\": \"北京\"}"}}

// 格式 B: 简化格式
{"name": "get_weather", "arguments": {"city": "北京"}}

// 格式 C: 原生格式
{"name": "get_weather", "input": "{\"city\": \"北京\"}"}
```

输出：
```xml
<|DSML|tool_calls>
  <|DSML|invoke name="get_weather">
    <|DSML|parameter name="city"><![CDATA[北京]]></|DSML|parameter>
  </|DSML|invoke>
</|DSML|tool_calls>
```

#### 参数格式化细则

`_format_params_dsml()` 处理不同 Python 类型的 DSML 序列化：

| Python 类型 | DSML 输出 | 示例 |
|------------|----------|------|
| `None` | 空标签 | `<parameter name="x"></parameter>` |
| `str` | CDATA 包裹 | `<parameter name="x"><![CDATA[hello]]></parameter>` |
| `int/float/bool` | 纯文本 | `<parameter name="x">42</parameter>` |
| `dict/list` | CDATA 包裹的 JSON | `<parameter name="x"><![CDATA[{"key":"value"}]]></parameter>` |

**修复（2026-05-07）：** 历史上 dict/list 类型参数会被序列化为空标签（`<parameter name="x"></parameter>`），导致嵌套参数丢失。修复后使用 `json.dumps()` 序列化为 JSON 字符串，再以 CDATA 包裹传递，保留了完整的嵌套结构。

---



## 9. StreamSieve 流式筛分引擎

### 9.1 解决的问题

流式模式下，DeepSeek 逐 token 返回文本。当工具调用发生时，DSML XML 标签与普通文本 token 交错传输。StreamSieve 需要在 token 级别实时检测并分离文本和工具调用标签。

### 9.2 双缓冲区设计

```
待处理缓冲区 (_pending)
  │ 存储尚未被判定为工具调用的文本
  │ 避免在标签边界处截断 token
  ▼
检测到 DSML 起始标记
  │ (如 <|DSML|tool_calls>, <invoke, <tool_calls>)
  ▼
捕获缓冲区 (_capture_buf)
  │ 从标记开始捕获所有后续 token
  │ 持续到检测到闭合标签
  ▼
捕获完成 → parse_fn 解析 → SieveEvent 发出
  │ type='tool_calls' 或 type='text'
  ▼
缓冲区和状态重置
```

### 9.3 核心方法

**`feed(chunk)`** — 处理新 token：

```
流程图:
1. 如果当前处于 _capturing 状态:
   a. 将 chunk 追加到 _capture_buf
   b. 尝试 _try_finish_capture()
   c. 完成则发出事件并重置，未完成继续等待
   
2. 如果不处于 _capturing 状态:
   a. 将 chunk 追加到 _pending
   b. 在 _pending 中搜索 _find_tool_start()
   c. 找到标记:
      - 标记前的文本作为 text 事件发出
      - 剩余部分移入 _capture_buf
      - 尝试 _try_finish_capture()
   d. 未找到标记:
      - _split_safe() 将安全部分发出，可能包含标记起始的尾部保留
```

**`flush()`** — 流结束时处理残余缓冲区：
- `_capture_buf` 中未闭合的工具调用 → 当普通文本发出
- `_pending` 中残余文本 → 发出

**`_find_tool_start(text)`** — 在文本中搜索 DSML 起始标记：

```python
_TOOL_STARTS = [
    "<|DSML|tool_calls>",
    "|DSML|tool_calls>",
    "<tool_calls>",
    "<tool_call>",
    "<invoke ",
    "<|DSML|invoke ",
    "|DSML|invoke ",
]
```

同时检测前缀：`<|DSML|`、`|DSML|`、`<tool_calls`、`<tool_call`、`<invoke`

**`_split_safe(text)`** — 切分文本，避免在可能的标记起始处截断：

检查文本最后一个 `<` 或 `|` 位置，如果尾部匹配任何 `_TOOL_STARTS` 的前缀，则保留尾部到 `_pending`，其余部分作为安全文本发出。

**`_is_capture_complete()`** — 判断捕获是否完整：

- 如果 `_capture_buf` 包含 `<|DSML|tool_calls>` 或 `<tool_calls>` → 等待对应的闭合标签
- 如果包含 `<invoke` 或 `<|DSML|invoke` → 等待 `</invoke>` 或 `</|DSML|invoke>`

### 9.4 事件模型

```python
@dataclass
class SieveEvent:
    type: str      # 'text' | 'tool_calls'
    data: Any      # str (for text) | list[dict] (for tool_calls)
```

### 9.5 流式 Fallback 机制

server.py 的 `_handle_stream` 中有两层防护：

1. **主路径**：StreamSieve 实时筛分，检测到工具调用立即发出 tool_calls 事件并终止流
2. **Flush 路径**：流结束时 `sieve.flush()` 处理残余
3. **Fallback 路径**：如果 sieve 漏检（罕见情况），用 `full_buf`（完整缓冲区）重新调用 `parse_dsml_tool_calls()` 全量解析

```python
if not had_tool and full_buf:
    tc_result, _ = parse_dsml_tool_calls(full_buf, tool_names)
    if tc_result:
        # 发出工具调用事件
        ...
```

---

## 10. OpenAI 兼容层

### 10.1 端点

| 端点 | 方法 | 功能 | server.py 处理函数 |
|------|------|------|-------------------|
| `/health` | GET | 健康检查 | `health()` |
| `/v1/models` | GET | 模型列表 | `list_models()` |
| `/v1/chat/completions` | POST | 对话补全 | `chat_completions()` |

### 10.2 请求模型 (`ChatCompletionRequest`)

```python
class ChatCompletionRequest(BaseModel):
    model: Optional[str] = MODEL_NAME        # 模型名，可自定义（不影响转发）
    messages: list[ChatMessage]               # 消息列表
    stream: Optional[bool] = False            # 是否流式
    max_tokens: Optional[int] = None          # 当前被忽略（透传无效）
    temperature: Optional[float] = None       # 当前被忽略
    top_p: Optional[float] = None             # 当前被忽略
    tools: Optional[list[ToolDef]] = None     # 工具定义
    tool_choice: Optional[Union[str, dict]] = None  # 工具选择（不可靠）
    thinking_mode: Optional[bool] = False     # 客户端请求的思考模式（被 MODE/THINKING env 覆盖）
    search_enabled: Optional[bool] = False    # 联网搜索
```

**`thinking_mode` 与 MODE/THINKING env 的关系：**

```
thinking_mode 只在 MODE=auto 且 THINKING=auto 时生效
  ↑
客户端请求       → MODE=auto, THINKING=auto → thinking = req.thinking_mode
               → MODE=expert               → model_type = "expert"（忽略客户端）
               → THINKING=enabled          → thinking = True（忽略客户端）
```

即：环境变量的优先级高于客户端传参。

### 10.3 流式 SSE 格式

```json
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1234567890,"model":"deepseek-chat","choices":[{"index":0,"delta":{},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1234567890,"model":"deepseek-chat","choices":[{"index":0,"delta":{"role":"assistant","content":null},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1234567890,"model":"deepseek-chat","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1234567890,"model":"deepseek-chat","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

**必须包含 `finish_reason: "stop"` 结束帧。** 标准 OpenAI 兼容客户端依赖此字段判断流是否正常结束。缺少则客户端可能报告 `finish: "other"` 或 `finish: null`，导致响应处理异常。

**开启思考时 (`thinking_mode=true`) 的 SSE 序列：**

```json
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":...,"model":"deepseek-chat","choices":[{"index":0,"delta":{},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":...,"model":"deepseek-chat","choices":[{"index":0,"delta":{"reasoning_content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":...,"model":"deepseek-chat","choices":[{"index":0,"delta":{"reasoning_content":"思考过程..."},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":...,"model":"deepseek-chat","choices":[{"index":0,"delta":{"content":"最终回答"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":...,"model":"deepseek-chat","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

### 10.4 工具调用 SSE 格式（`_emit_tool_calls_chunks`）

```
帧1: delta.tool_calls[0] = {id: "call_xxx", type: "function", function: {name: "get_weather", arguments: ""}}
帧2: delta.tool_calls[0] = {function: {arguments: '{"city": "北京"}'}}
结束帧: finish_reason = "tool_calls"
data: [DONE]
```

### 10.5 非流式响应格式

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "deepseek-chat",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "回复内容"
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

工具调用时：
```json
"message": {
  "role": "assistant",
  "content": null,
  "tool_calls": [{
    "id": "call_xxx",
    "type": "function",
    "function": {"name": "get_weather", "arguments": "{\"city\": \"北京\"}"}
  }]
},
"finish_reason": "tool_calls"
```

### 10.6 模型名称处理

`MODEL_NAME` 通过 `.env` 配置，默认 `"deepseek-chat"`。可自定义为 `"gpt-4"`、`"deepseek-reasoner"` 等任意值，**不影响实际转发**，仅用于响应中的 model 字段。

---

## 11. Anthropic 兼容层

### 11.1 概述

项目新增对 Anthropic Claude API 格式的支持，通过 `POST /v1/messages` 端点提供。

**设计原则：** adapter 层完全不变。格式转换在独立模块 `anthropic_format.py` 中完成，与 OpenAI 逻辑隔离。

### 11.2 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/v1/messages` | POST | Anthropic 格式对话补全 |

### 11.3 请求映射

| Anthropic 字段 | 映射方式 |
|---------------|---------|
| `messages[].content` | 提取文本 → `build_anthropic_prompt()` 拼入 prompt |
| `system` | 拼入 prompt 开头作为 System 前缀 |
| `thinking.type` | 映射为 `thinking_mode`，受 THINKING env 覆盖 |
| `tools` | 转为 DSML 工具提示词注入（复用 `build_dsml_tool_prompt()`） |
| `max_tokens` | 忽略（DeepSeek 不支持） |
| `metadata` | 忽略 |
| `stop_sequences` | 忽略 |
| `stream` | 控制流式/非流式路径 |

### 11.4 流式 SSE 格式

Anthropic 使用独立的事件类型：

```
event: message_start
data: {"type":"message_start","message":{"id":"msg_...","type":"message","role":"assistant","content":[],...}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"推理过程..."}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: content_block_start
data: {"type":"content_block_start","index":1,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"最终回答"}}

event: content_block_stop
data: {"type":"content_block_stop","index":1}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},...}

event: message_stop
data: {"type":"message_stop"}
```

工具调用时：
```
content_block_start(index, type="tool_use", id="toolu_...", name="get_weather", input={})
content_block_delta(index, type="input_json_delta", partial_json="...")
content_block_stop(index)
message_delta → stop_reason: "tool_use"
```

### 11.5 非流式响应

Anthropic 格式使用 `content` 数组替代 OpenAI 的单一 `content` 字符串：

```json
{
  "id": "msg_...",
  "type": "message",
  "role": "assistant",
  "content": [
    {"type": "text", "text": "回答内容"}
  ],
  "model": "deepseek-chat",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {"input_tokens": -1, "output_tokens": -1}
}
```

有工具调用时：
```json
"content": [
  {"type": "tool_use", "id": "toolu_xxx", "name": "get_weather", "input": {"city": "北京"}}
],
"stop_reason": "tool_use"
```

有 thinking 时（仅流式场景，非流式 adapter.chat() 不返回 thinking）：
```json
"content": [
  {"type": "thinking", "thinking": "推理过程..."},
  {"type": "text", "text": "回答内容"}
]
```

### 11.6 工具调用映射

Anthropic 使用 `tool_use`/`tool_result` content block 类型，与 OpenAI 的 `tool_calls`/`tool` role 对应：

| OpenAI | Anthropic |
|--------|-----------|
| `tool_calls[].function.name` | `tool_use.name` |
| `tool_calls[].function.arguments` (JSON string) | `tool_use.input` (parsed object) |
| `tool_calls[].id` | `tool_use.id` (prefix: `toolu_`) |
| `role: "tool"` + `tool_call_id` | `role: "user"` + `tool_result` block |

`build_anthropic_prompt()` 将多轮对话中的 `tool_use` 块转为 DSML 格式 + `tool_result` 块转为 `Tool result:` 前缀。

### 11.7 关键实现

`anthropic_format.py` 的核心函数：

| 函数 | 职责 |
|------|------|
| `build_anthropic_prompt()` | Anthropic messages → 内部 prompt 文本 |
| `build_nonstream_response()` | token 流 → Anthropic 非流式 JSON |
| `stream_response()` | token 流 → Anthropic SSE 事件生成器 |
| `_dsml_toolcalls_to_anthropic()` | OpenAI tool_calls → Anthropic tool_use blocks |
| `_emit_tool_use_blocks()` | tool_use → SSE content_block_start/delta/stop 事件 |

### 11.8 MODE/THINKING/SEARCH 交互

与 OpenAI 端点共享 MODE/THINKING/SEARCH 环境变量：

```
THINKING=enabled  → 强制 thinking=true（无视请求中 thinking 参数）
THINKING=disabled → 强制 thinking=false
THINKING=auto     → thinking = (请求中 thinking.type == "enabled")
```

---

## 12. 多轮对话与消息组装

### 11.1 `_build_prompt()`

将 OpenAI messages 数组转为 DeepSeek 纯文本格式：

```
System: 你是一个有帮助的助手。\n\n工具指令...
User: 北京天气怎么样？
Assistant: 让我查一下。<|DSML|tool_calls>...
Tool result: {"temperature": 25}
User: 那湿度呢？
```

### 11.2 角色映射

| OpenAI role | Prompt 前缀 | 处理逻辑 |
|-------------|------------|---------|
| `system` | `System: ` | 直接拼接，如有 tools 则附加 DSML 指令 |
| `user` | `User: ` | 提取 content 文本 |
| `assistant` | `Assistant: ` | 文本 + tool_calls（转 DSML） |
| `tool` | `Tool result: ` | 截断前 1000 字符 |

### 11.3 system message 的工具注入

当请求包含 `tools` 时，`build_dsml_tool_prompt()` 生成的指令会 **注入到 system message 末尾**。如果有多个 system message，指令会被拼接到第一个 system message 中。如果没有 system message，会创建一个新的 system 前缀。

---

## 13. ContentPart 支持

### 12.1 解决的问题

OpenAI 的 `content` 字段支持两种格式：

```json
// 格式 A: 纯字符串
{"role": "user", "content": "你好"}

// 格式 B: ContentPart 数组
{"role": "user", "content": [{"type": "text", "text": "你好"}]}
```

`_extract_text()` 统一处理：

```python
def _extract_text(content) -> str:
    if content is None:    return ""
    if isinstance(content, str):  return content
    # list[ContentPart] 格式
    return " ".join(p.text for p in content if p.type == "text" and p.text)
```

当前只支持 `type: "text"` 的 ContentPart。不支持图片、文件等多模态内容（DeepSeek Chat 网页版本身不支持）。

### 12.2 Pydantic 模型

```python
class ContentPart(BaseModel):
    type: str
    text: Optional[str] = None
```

---

## 14. 配置系统

### 13.1 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_TOKEN` | — | Authorization Bearer Token |
| `DEEPSEEK_COOKIES` | — | Cookie 字符串 |
| `MODEL_NAME` | `deepseek-chat` | 响应中的模型名（不影响实际转发） |
| `PORT` | `8080` | 服务器监听端口 |
| `MODE` | `auto` | 模式控制：`auto`/`quick`/`expert` |
| `THINKING` | `auto` | 思考控制：`auto`/`enabled`/`disabled` |
| `SEARCH` | `auto` | 联网搜索控制：`auto`/`enabled`/`disabled` |
| `DEEPSEEK_JITTER_SECS` | `0.4`（v3.2.2+） | 上游调用前随机 sleep（0~N 秒），降低触发上游限流概率；`0` 禁用 |
| `DEEPSEEK_RATE_LIMIT_RETRY_DELAYS` | `5,15`（v3.2.2+） | 上游限流（`rate_limit_reached`）时的退避秒数列表，每项重试一次并换新会话；空则禁重试 |

> 其余可选变量见下表（`.env.example` 有完整注释，此处是给 Agent/自动化配置的速查）：

| 变量 | 默认值 | 用途 | 非交互关键度 |
|------|--------|------|------|
| `API_KEYS` | `""` | `/v1/*` 客户端鉴权，逗号分隔多 key | ⭐必配(公网) |
| `DEEPSEEK_API_KEY` | `""` | 单 key 别名，与 `API_KEYS` 等价 | 可选 |
| `ALLOW_UNAUTHENTICATED_API` | `false` | 是否允许 /v1/* 无鉴权 | 仅本地开发 |
| `HOST` | `127.0.0.1` | 监听地址；`0.0.0.0`+默认密码拒绝启动 | ⭐反代需关注 |
| `PORT` | `8080` | 监听端口 | |
| `MODEL_NAME` | `deepseek-chat` | /v1/models 显示名（不影响实际模型） | |
| `MODEL_ROUTES` | `""` | JSON 路由表，按 model 字段切 quick/expert | ⭐多模型路由 |
| `MODE` / `THINKING` / `SEARCH` | `auto` | 行为三独立维度 | ⭐强制模式 |
| `ACCOUNT_STORE_PATH` | `data/accounts.json` | 账号池持久化文件路径 | ⭐非交互账号池 |
| `DEEPSEEK_ENCRYPTION_KEY` | `""` | Fernet key，accounts.json 加密(v2) | ⭐公网安全 |
| `CLIENT_RPM_PER_KEY` | `60` | 每 key 每分钟请求数(0=不限) | ⭐限流 |
| `CLIENT_RPM_PER_IP` | `120` | 每 IP 每分钟请求数(0=不限) | ⭐限流 |
| `ENABLE_RATE_LIMIT` | `true` | 限流总开关 | |
| `SESSION_CACHE_TTL` | `600` | 多轮会话缓存秒数，0=禁多轮 | ⭐多轮 |
| `DEEPSEEK_TOKEN` / `_N` | `""` | DeepSeek 账号凭证(token)，`_1`为多账号 | ⭐兜底账号 |
| `DEEPSEEK_COOKIES` / `_N` | `""` | DeepSeek 账号 Cookie | ⭐兜底账号 |
| `DEEPSEEK_EMAIL_N` | `env-N` | 多账号标识 | |
| `DEEPSEEK_PROXY` / `_N` | `""` | 每账号上游代理 URL | ⭐反检测 |
| `DEEPSEEK_IMPERSONATE` | `chrome131` | curl_cffi TLS 指纹 profile | |
| `DEEPSEEK_JITTER_SECS` | `0.4` | 调用前随机 sleep 秒数 | |
| `DEEPSEEK_RATE_LIMIT_RETRY_DELAYS` | `5,15` | 上游限流退避秒数列，空=禁重试 | |
| `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR | |
| `LOG_FORMAT` | `json` | json(生产)/text(开发) | |
| `ALLOWED_ORIGINS` | `""` | CORS 允许 origin，逗号分隔 | 浏览器客户端 |
| `ALLOW_CORS_CREDENTIALS` | `false` | 带凭证跨域 | |
| `TRUSTED_PROXIES` | `""` | 信任代理 IP/CIDR，设后才采纳 XFF | ⭐反代 |
| `ALLOW_INSECURE_PUBLIC_DEFAULTS` | `false` | 公网+默认密码的显式确认(不建议) | |
| `DISABLE_AUTO_RECOVER` | `false` | 禁用账号自动恢复 | |

**给自动化/代理工具的配置 checklist（按顺序）：**
1. `API_KEYS` 必配（否则 /v1/* 报 503）→ Bearer/x-api-key 鉴权
2. 账号池：多账号→写 `data/accounts.json`；单兜底→`.env` 的 `DEEPSEEK_TOKEN_1/COOKIES_1`
3. 公网→`HOST=127.0.0.1`+反代+`TRUSTED_PROXIES`；或 `HOST=0.0.0.0`+自己上 TLS/WAF
4. 限流默认够用；多 worker(gunicorn -w N) 实际限流=N×配置值
5. 改 `.env` 必须**重启进程**才生效（load_dotenv 只在模块加载时调用一次）


#### MODE 详细说明

| 值 | 效果 | model_type |
|----|------|-----------|
| `auto` | 不强制，使用客户端默认行为 | `"default"`（快速模式） |
| `quick` | 强制快速模式 | `"default"` |
| `expert` | 强制专家模式 | `"expert"` |

#### THINKING 详细说明

| 值 | 效果 | thinking_enabled |
|----|------|-----------------|
| `auto` | 由客户端 request 中的 `thinking_mode` 决定 | `req.thinking_mode or False` |
| `enabled` | 强制开启思考 | `True` |
| `disabled` | 强制关闭思考 | `False` |

#### SEARCH 详细说明

| 值 | 效果 | search_enabled |
|----|------|---------------|
| `auto` | 由客户端 request 中的 `search_enabled` 决定 | `req.search_enabled or False` |
| `enabled` | 强制开启联网搜索 | `True` |
| `disabled` | 强制关闭联网搜索 | `False` |

**重要：** 三个参数完全独立。`MODE=auto` 不等于"旧版 auto"——旧版中 `thinking_mode=true` 会同时设置 `model_type="expert"`。新版中每个维度由对应的环境变量独立控制。

#### MODE / THINKING / SEARCH 交互矩阵

| MODE | THINKING | SEARCH | 实际行为 |
|------|----------|--------|---------|
| `auto` | `auto` | `auto` | model_type="default", thinking=客户端, search=客户端 |
| `auto` | `enabled` | `auto` | model_type="default", thinking=true, search=客户端 |
| `auto` | `disabled` | `auto` | model_type="default", thinking=false, search=客户端 |
| `quick` | `auto` | `auto` | model_type="default", thinking=客户端, search=客户端 |
| `quick` | `enabled` | `auto` | model_type="default", thinking=true, search=客户端 |
| `quick` | `disabled` | `disabled` | model_type="default", thinking=false, search=false |
| `expert` | `auto` | `auto` | model_type="expert", thinking=客户端, search=客户端 |
| `expert` | `enabled` | `enabled` | model_type="expert", thinking=true, search=true |
| `expert` | `disabled` | `auto` | model_type="expert", thinking=false, search=客户端 |

所有 9 种组合均有效，`auto` 表示由客户端请求中的对应字段决定。

修改 `.env` 后需要**重启服务器**才能生效（`load_dotenv()` 只在模块加载时调用一次）。

### 13.2 加载方式

```python
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.environ.get("DEEPSEEK_TOKEN", "")
COOKIES = os.environ.get("DEEPSEEK_COOKIES", "")
MODEL_NAME = os.environ.get("MODEL_NAME", "deepseek-chat")
```

同时 `adapter.py` 和 `server.py` 各自调用 `load_dotenv()`（dotenv 保证只加载一次）。

### 13.3 Token 和 Cookie 获取

1. 打开 https://chat.deepseek.com 并登录
2. F12 → Network → 任意请求
3. 从 Request Headers 复制：
   - `Authorization: Bearer <token>` → token
   - `Cookie: <完整cookie>` → cookies

Token 和 Cookie 会过期，需定期更新。过期特征：PoW challenge 请求返回 `{"code":40003,"msg":"Authorization Failed (invalid token)"}`。

### 13.4 WASM 二进制来源

`sha3_wasm_bg.wasm` 从 DeepSeek 前端中提取：

1. 打开 https://chat.deepseek.com 并登录
2. F12 → Sources → 搜索 `sha3_wasm_bg.wasm`
3. 在 "Network" 标签中找到该文件并下载
4. 或者直接在 JS 中定位：前端通过 `wasm_bindgen` 加载 `sha3_wasm_bg.wasm`，通常与 `sha3_wasm.js` 配套
5. 将下载的 `.wasm` 文件覆盖项目根目录的同名文件

验证方法：
```python
from wasmtime import Store, Module
with open("sha3_wasm_bg.wasm", "rb") as f:
    Module(Store().engine, f.read())
print("WASM valid")
```

**风险提示：**
- DeepSeek 可能在任何前端更新中更换 WASM 二进制
- 更新 WASM 后需检查导出函数名是否变化
- 如果 `wasm_solve` 等导出函数不可用，需要同步更新 `_WASMSolver` 类

### 13.5 httpx 客户端配置

```python
self._client = httpx.Client(timeout=120)
```

| 配置项 | 值 | 说明 |
|--------|------|------|
| `timeout` | 120s | 含连接、读取、写入总超时 |
| 连接池 | 默认 (10) | httpx 默认连接池限制 |
| Keep-Alive | 默认启用 | 复用 HTTP 连接 |

**120s 超时的选择理由：**
- 专家模式 THINK 阶段可能持续 30-60s，需要足够等待时间
- DeepSeek 服务端在长时间思考期间不会发送数据，短超时会误断连
- 网页版实际超时约 180s，120s 是保守值
- `timeout=120` 是所有子超时的总上限（connect/read/write/pool）

如果使用短超时（如默认的 5s），专家模式会在 thinking 阶段频繁断连，表现为 `Server disconnected without sending a response`。

### 13.6 端口管理与进程控制

`start.bat` 的端口管理逻辑（结合 `PORT` 环境变量）：

```batch
:: 使用 PORT 环境变量（默认 8080）
if "%PORT%"=="" set PORT=8080

:: 查找配置端口的 LISTENING 进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do (
    taskkill /F /PID %%a
)
```

**工作原理：**
1. 检查 `PORT` 环境变量，如果未设置则默认为 8080
2. `netstat -ano` 列出所有连接及对应 PID
3. `findstr ":%PORT% "` 过滤包含配置端口号的行
4. `findstr LISTENING` 只保留 LISTENING 状态
5. `tokens=5` 提取第 5 列（PID）
6. `taskkill /F /PID` 强制终止

**手动排查：**
```bash
# 查看配置端口占用
netstat -ano | findstr ":%PORT%"

# 强制终止指定 PID
taskkill /F /PID <pid>
```

**`__pycache__` 注意事项：** 如果更新代码后启动旧行为，可能是 Python 缓存了旧字节码：
```bash
# 清理所有 __pycache__
for /d /r . %d in (__pycache__) do @if exist "%d" rd /s /q "%d"
```
建议将清理命令加入 `start.bat` 或开发工作流中。

---

## 15. 账号池 (AccountPool)

### 18.1 设计目标

支持多 DeepSeek 账号轮询使用，解决单账号被限流/封禁时的 failover 问题。`AccountPool` 管理账号的完整生命周期：添加、分配、释放、错误标记和健康检查。

### 18.2 核心数据结构

```python
@dataclass
class Account:
    token: str            # DeepSeek Bearer Token
    cookies: str          # DeepSeek Cookie
    email: str            # 显示用标识
    state: str            # idle | busy | error
    error_count: int
    last_error: str
    last_used: float
```

### 18.3 状态流转

```
添加 → idle
        │
   acquire() → busy → release() → idle
        │                │
        │  mark_error()  ↓
        └────────→ error ──→ relogin() (成功 → idle, 失败 → error)
```

### 18.4 轮询分配

`acquire()` 使用 round-robin 策略遍历账号列表，返回第一个 `idle` 状态的账号并将其标记为 `busy`。如果所有账号均 busy，返回 `None`，server.py 返回 HTTP 503。

### 18.5 健康检查与重登录

```python
def check_health(acct) -> bool:
    """通过创建 DeepSeek 会话来验证凭证有效性。"""
```

`relogin(index)` 对 `error` 状态的账号执行健康检查：成功则重置为 `idle`，失败保留 `error` 状态并更新 `last_error`。

### 15.6 线程安全

`AccountPool` 使用 `threading.Lock` 保护所有状态变更操作（CRUD、状态切换）。`_WASMSolver` 已有独立锁，两把锁不会形成死锁（无嵌套加锁）。

### 15.7 初始加载与 env 兜底

- **池内账号**：启动时从 `data/accounts.json`（面板持久化）加载；面板/Admin API 增删改。
- **env 兜底**：`.env` 中的凭证（numbered `DEEPSEEK_TOKEN_1/...` 优先，legacy `DEEPSEEK_TOKEN`/`DEEPSEEK_COOKIES` 其次）**不再预加载进池**，而是作为只读兜底账号（id=`env-*`，source=`env`，`read_only=true`）：
  - 池内**有**账号时：只用池内账号（面板账号优先）
  - 池内**0**个账号时：`acquire()` 返回 env 兜底账号，服务不因池空而 503
  - webui 账号池页显示该条目（灰色只读），删除接口对 `env-*` 无效（不在池内，返回 404）
  - 实现：`AccountPool._env_fallback`（`_load_env_fallback()`），`acquire()` 池空分支、`get_all()`/`stats()` 含兜底账号

### 15.8 非交互式账号池配置（代理 / 自动化工具专用）

> **场景**：给 SDK、脚本、curl、CI、代理等**不经过 WebUI 面板**的自动化工具配置多账号轮询。
> **要点**：v3.0.0+ 账号池的**主配置源是 `data/accounts.json` 文件**，不是 `.env`。`.env` 只提供「单账号只读兜底」。要跑**多账号轮询**，非交互场景必须直接写 `data/accounts.json`。

**`data/accounts.json` 完整 schema（v1 明文版）：**

```json
{
  "version": 1,
  "accounts": [
    {
      "id": "acc-001",
      "email": "acc-001",
      "token": "<DeepSeek Bearer token>",
      "cookies": "cf_clearance=xxx; session=yyy; ...",
      "created_at": 1781234567,
      "updated_at": 1781234567
    },
    {
      "id": "acc-002",
      "email": "acc-002",
      "token": "<token2>",
      "cookies": "<cookies2>",
      "created_at": 1781234567,
      "updated_at": 1781234567
    }
  ]
}
```

- 字段：`id`(可选,默认自动生成)、`email`(显示标识)、`token`、`cookies`(必填两个)、`created_at`/`updated_at`(可选,整数 epoch 秒)。
- `version`：`1`(明文) 或 `2`(Fernet 加密)。缺省按明文解析。
- 该文件**必须** `chmod 600`、所在目录 `700`。含明文 DeepSeek token+cookie，泄露=账号被滥用。

**非交互配置步骤：**

```bash
# 1. 写入账号池文件（可脚本生成）
cat > /path/to/project/data/accounts.json <<'JSON'
{"version":1,"accounts":[
  {"email":"acc-001","token":"<token>","cookies":"<cookies>"}
]}
JSON
chmod 600 /path/to/project/data/accounts.json
chmod 700 /path/to/project/data

# 2. 可选：改存储路径（不改则默认 data/accounts.json）
#    .env 或环境变量设：ACCOUNT_STORE_PATH=/path/to/accounts.json

# 3. 配置 API 鉴权（非交互必须，否则 /v1/* 报 503）
#    API_KEYS=***   （多个逗号分隔)

# 4. 启动
python -m uvicorn server:app --host 127.0.0.1 --port 8080
```

- **加密存储（推荐公网）**：设 `DEEPSEEK_ENCRYPTION_KEY`(Fernet 32B base64)，首次启动会把 `version:1` 明文自动迁移为 `version:2` 加密，并留 `accounts.json.v1.bak`。此时**不要再手写明文文件**（会被 detect_store_version 判成 v2 encrypted 又无 key 而拒绝加载）。
- **写入时机**：在服务**启动前**写文件，或运行中调 `POST /admin/api/accounts`(需 admin token)。服务启动时 `_load_persisted_accounts()` 一次性全量加载。
- **只保留一个兜底账号**：直接用 `.env` 的 `DEEPSEEK_TOKEN_1/COOKIES_1`（或 legacy `DEEPSEEK_TOKEN/COOKIES`），池空自动兜底，不必写 accounts.json。

---

## 16. 管理后台 (Admin API)

### 19.1 设计概述

管理后台包含三个部分：
1. **Admin API** (`admin.py`) — FastAPI APIRouter，挂载在 `/admin/api` 前缀
2. **AccountPool** (`account_pool.py`) — 账号池核心逻辑
3. **前端 SPA** (`webui-new/`) — React SPA（v3.0.0+），构建产物 `webui-new/dist/` 由 `server.py` 伺服于 `/webui/*`

所有管理 API 端点（除 `/admin/api/login`）均需要 Bearer Token 认证。

### 19.2 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/admin/api/login` | 密码登录，返回 token |
| `GET` | `/admin/api/stats` | 请求统计（总量/成功/失败/平均延迟/tokens/运行时长） |
| `GET` | `/admin/api/accounts` | 账号列表 + 池状态汇总（total/idle/busy/error） |
| `POST` | `/admin/api/accounts` | 添加账号（body: token, cookies, email） |
| `DELETE` | `/admin/api/accounts/{index}` | 删除账号 |
| `POST` | `/admin/api/accounts/{index}/relogin` | 重登录 error 账号 |

### 19.3 认证机制

- 管理密码设置：`DEEPSEEK_ADMIN_PASSWORD` 环境变量（默认 `admin`）
- Token 存储：服务端内存 `set`，每次登录生成 64 位 hex token
- Token 验证：每次请求从 `Authorization: Bearer <token>` 头提取
- 无过期机制（服务重启后需重新登录）

### 16.4 请求统计

`StatsSnapshot` 在内存中维护以下计数器：
- `total_requests` / `success_requests` / `failed_requests`
- `total_latency_ms`（累加后计算平均值）
- `total_prompt_tokens` / `total_completion_tokens`
- 按模型聚合：`models[model_name] = {requests, prompt_tokens, completion_tokens}`

统计在 `chat()`/`chat_stream()` 调用前后通过 `get_stats().record()` 记录。流式响应在 `finally` 块中确保统计被记录。

### 16.5 前端 SPA（v3.0.0+）

- **技术栈**：Vite 5 + React 18 + TypeScript + shadcn/ui（Radix + Tailwind）+ Recharts + Zustand + react-router-dom v6
- **路由**：`createBrowserRouter(..., { basename: '/webui' })`——SPA 位于 `/webui/*`，深链接刷新由 `server.py` 的 `/webui/{rest}` SPA fallback 回 index.html
- **构建**：`webui-new/` 下 `npm install && npm run build`（或 `scripts/build.bat`），产物 `webui-new/dist/`。vite `base: '/webui/'` 使资源引用带前缀（改回 `/` 会导致 JS/CSS 404 白屏）
- **鉴权**：admin token 存 `localStorage`（zustand persist，key `ds2api-auth`）；`api()` 包装器统一带 `Authorization: Bearer <admin-token>`，401 自动 logout 跳 `/login`。`/v1/*` 现也接受该 admin token（见 13.1/18.1）
- **页面**：登录 / 概览（统计卡 + 请求量/延迟 Recharts 图 + 账号池状态）/ 账号池（表格 + 抽屉详情 + 添加/编辑/删除 + 重登）/ Playground（流式对话，参数仅暴露后端真实转发的字段，reasoning 折叠显示）/ 设置（`/admin/api/env` 只读）/ 404
- **主题**：浅色/深色/跟随系统，`localStorage` 持久化（key `ds2api-theme`），`main.tsx` 挂载前提前 `applyTheme` 防闪烁
- **轮询**：概览页 stats 5s / accounts 10s / history 30s，账号页 10s（`useApi` hook 带 AbortController + reqId 防竞态）

### 16.6 与 server.py 集成

```python
# server.py
from admin import router as admin_router, get_pool, get_stats

pool = get_pool()           # 共享的 AccountPool 实例

# 在 handler 中使用 pool 获取账号
acq = pool.acquire()        # 获取一个空闲账号（标记为 busy）
# ... 使用 acq.adapter.chat_stream(...) ...
pool.release(acq.acct)      # 释放（标记回 idle）

# 请求完成后记录统计
get_stats().record(model, latency_ms, prompt_tokens, completion_tokens)
```

---

## 17. 关键算法细节

### 20.1 PoW Token 构造

### 20.1 PoW Token 构造

```python
raw = json.dumps({
    "algorithm": "DeepSeekHashV1",
    "challenge": challenge_data["challenge"],
    "salt": challenge_data["salt"],
    "answer": nonce,
    "signature": challenge_data["signature"],
    "target_path": challenge_data["target_path"],
}, separators=(",", ":"))  # 无空格压缩
pow_token = base64.b64encode(raw.encode()).decode()
```

注意 `separators=(",", ":")` 确保 JSON 无空白，这是 DeepSeek 服务端的期望格式。

### 17.2 SSE 行解析

```python
for line in resp.iter_lines():
    line = line.strip()
    if not line: continue
    if line.startswith("event: "):
        current_event = line[7:]
        continue
    if line.startswith("data: "):
        data_str = line[6:]
        if not data_str: continue
        data = json.loads(data_str)
```

关键点：
- `line.strip()` 去除首尾空白（包括 `\r`）
- `event:` 行是可选的事件类型标签
- `data:` 行后可能跟空字符串（跳过）
- JSON 解析失败的行跳过（非关键路径）

### 17.3 `_try_finish_capture` 完成判断

```python
def _is_capture_complete(self) -> bool:
    if "<|DSML|tool_calls>" in buf or "<tool_calls>" in buf:
        return "</|DSML|tool_calls>" in buf or "</tool_calls>" in buf
    if "<invoke " in buf or "<|DSML|invoke " in buf:
        return "</invoke>" in buf or "</|DSML|invoke>" in buf
    return False
```

同时检测带 `|DSML|` 前缀和不带前缀的两种标签格式。

### 14.4 WASM 内存操作

`_WASMSolver._encode(s)` 将字符串写入 WASM 线性内存：

```python
def _encode(self, s: str):
    data = s.encode("utf-8")
    ptr = self.malloc(self.store, len(data), 1)  # wasm 分配 len(data) 字节
    mem = self.memory.data_ptr(self.store)
    for i, b in enumerate(data):
        mem[ptr + i] = b                         # 逐字节复制到 WASM 内存
    return ptr, len(data)
```

关键细节：

| 操作 | 说明 |
|------|------|
| `self.malloc(len, 1)` | wasm 分配的 `__wbindgen_export_0`，对应 `aligned_alloc`，align=1 无对齐要求 |
| `mem[ptr + i] = b` | Python 通过 `memory.data_ptr` 获取 WASM 线性内存的 NumPy-like 视图，直接写入 |
| 返回 `(ptr, length)` | 指针 + 长度两个值传给 wasm 函数 |

`wasm_solve` 的调用参数含义：

```python
self.wasm_solve(
    self.store,
    stack_ptr,     # 栈指针（放结果的位置）
    chal_ptr,      # challenge 字符串指针
    chal_len,      # challenge 字符串长度
    prefix_ptr,    # prefix 字符串指针 = salt + "_" + expire_at + "_"
    prefix_len,    # prefix 字符串长度
    float(difficulty),  # difficulty 转为 f64
)
```

结果读取：

```python
ret = int.from_bytes(bytes(mem[stack_ptr:stack_ptr + 4]), byteorder='little', signed=True)
# ret == 0 → 求解失败，抛出 PoWError
# ret != 0 → 继续读取 nonce

result = struct.unpack('<d', bytes(mem[stack_ptr + 8:stack_ptr + 16]))[0]
# 8 字节 f64，小端序，即求解得到的 nonce
```

栈布局（16 字节）：

```
stack_ptr + 0:  i32 (4 字节) — 成功标志 (0=失败, !=0=成功)
stack_ptr + 4:  4 字节填充
stack_ptr + 8:  f64 (8 字节) — nonce 值
```

### 14.5 流式响应中的 `role_sent` 追踪

在 `server.py` 的流式处理中，需要控制 SSE 的初始事件：

```python
role_sent = False

# 处理 thinking token
elif tt == "thinking":
    content = token.get("content", "")
    if content:
        if not role_sent:
            yield _openai_chunk(proxy_id, reasoning_content="")  # 空帧标记思考开始
            role_sent = True
        yield _openai_chunk(proxy_id, reasoning_content=content)
    continue

# 处理 content token（经 sieve）
if not role_sent:
    if thinking_mode:
        yield _openai_chunk(proxy_id, reasoning_content="")  # 仅 thinking 模式发空帧
    role_sent = True
yield _openai_chunk(proxy_id, content=evt.data)
```

**`reasoning_content` 空帧的条件：**

| 路径 | 是否发空帧 | 条件 |
|------|-----------|------|
| Thinking token 循环 | ✅ 总是 | 已在 thinking 分支，空帧作为"thinking 开始"标记 |
| Text token 循环 | ✅ 仅当 `thinking_mode=True` | 没有 thinking 的纯 text 流不应发 reasoning |
| Flush 路径 | ✅ 仅当 `thinking_mode=True` | 同上 |
| Fallback 路径 | ✅ 仅当 `thinking_mode=True` | 同上 |

**`role_sent` 标志第 1 次内容发送后变为 True，后续不再重复发初始帧。**

#### `finish_reason: "stop"` 结束帧

流式响应末尾必须发送 `finish_reason: "stop"` 结束帧（`_openai_chunk(proxy_id, finish=True)`），否则客户端无法区分正常完成与异常断连。

```python
# 流末尾
yield _openai_chunk(proxy_id, finish=True)  # delta: {}, finish_reason: "stop"
yield "data: [DONE]\n\n"
```

`_openai_chunk(proxy_id, finish=True)` 产出：
```json
{"index": 0, "delta": {}, "finish_reason": "stop"}
```

历史版本缺少此帧，导致客户端将 `[DONE]` 前的最后 content chunk 的 `finish_reason: null` 作为结束信号，误判为 `finish: "other"`。

---

## 18. 已知限制与边界情况

### 18.1 认证相关

- **Token/Cookie 过期**：不定期失效，需重新获取。没有自动续期机制（webui 账号池提供一键重登录）。
- **账号来源**：`.env` 静态账号（`DEEPSEEK_TOKEN_n`/`DEEPSEEK_COOKIES_n` 或 legacy `DEEPSEEK_TOKEN`）与 webui 面板账号（`data/accounts.json`）双通道，账号池轮询分配。
- **两套鉴权**：`/v1/*` 客户端用 `API_KEYS`（Bearer 或 `x-api-key`）；webui 管理端用 `DEEPSEEK_ADMIN_PASSWORD` 换 admin 会话 token。
- **admin token 放行 `/v1/*`**（v2.2.0+ 行为）：`_check_api_auth` 先验证 `verify_admin_token()`，有效则放行——webui 用同一 token 调模型列表/Playground。持有 admin token 者本已能完全控制账号池，不扩大风险面。
- **登录节流**：每 IP 5 次失败 / 300s 窗口，超限返回 429；计数为进程内存态，重启清零。

### 18.2 功能限制

| 限制 | 原因 | 影响 |
|------|------|------|
| 不支持并行工具调用 | DSML 协议限制 | 每次只能调用一个工具 |
| `tool_choice` 不可靠 | 提示词注入方案限制 | 模型可能选择不调用工具 |
| `max_tokens` 无效 | DeepSeek API 不支持 | 超长回复需自行截断 |
| `temperature`/`top_p` 无效 | DeepSeek API 不支持 | 无法控制随机性 |
| 无多模态 | 网页 API 不支持图片 | 仅文本交互 |
| 非流式 OpenAI 端点不输出 reasoning_content | OpenAI 非流式响应模型未包含该字段 | 需要推理过程请用流式模式（Anthropic 非流式已支持 thinking 块） |

### 18.3 CORS 跨域支持

项目使用 FastAPI 的 `CORSMiddleware` 处理跨域请求。配置位于 `server.py`：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**默认允许所有来源、方法和请求头。** 这解决了浏览器插件（如 YouTube 字幕翻译等 Chrome 扩展）在使用 OpenAI 兼容接口时因 CORS 预检请求（`OPTIONS`）失败的问题。如果部署在需要限制跨域访问的环境，可相应收紧 `allow_origins` 等参数。

### 18.4 稳定性

- **WASM 求解失败**：罕见情况下求解超时或返回 0，需重试
- **Session 创建失败**：PoW 过期或凭证失效
- **SSE 断流**：长时间响应可能被 DeepSeek 中断
- **DSML 解析失败**：模型输出格式不符合预期时，工具调用不生效

### 18.5 边界情况处理

**空消息列表：** `_build_prompt([])` 返回 `""`，DeepSeek 可能回复空或报错。

### 18.6 陈旧字节码缓存 (`__pycache__`)

Python 的 `__pycache__` 目录缓存编译后的字节码（`.pyc`）。当源文件被修改但缓存未刷新时，python server.py 可能运行旧版本代码。

**触发条件：**
- 编辑代码文件后直接启动
- 之前运行过且 `__pycache__` 已存在
- uvicorn 的 `--reload` 模式虽然检测文件变更，但不会清理 `__pycache__`

**症状：**
- 修改代码后行为不变
- print 调试语句不出现
- 旧版 bug 依然存在
- 新增的函数抛出 `ImportError` 或 `NameError`

**排查方法：**
```bash
# 比较 .py 和 .pyc 的时间戳
dir /s __pycache__\*.pyc

# 查看 Python 实际加载的模块路径
python -c "import adapter; print(adapter.__file__)"
```

**根治方法：**
```bash
# 删除所有 __pycache__ 目录
for /d /r . %d in (__pycache__) do @if exist "%d" rd /s /q "%d"
```

**预防措施：**
- 开发时使用 `--reload` 模式
- 在 `start.bat` 末尾添加 `__pycache__` 清理命令
- 修改代码后手动删除 `__pycache__`

### 15.6 README.md

`README.md` 已存在并持续同步（v3.2.1 摘要 + 快速开始 + API 文档）。维护注意事项：
- 改 README 时同步更新 "v3.2.1 修复" 摘要与快速开始（启动/配置/凭证语义）
- start.bat 行为（自动 venv/依赖/WebUI 构建/自动开浏览器）在 README 有对应描述，改动脚本时同步

### 15.7 Windows bash curl 中文编码问题

在 Windows bash（Git Bash）中，curl 发送包含中文的 JSON body 可能导致请求被拒：

```bash
# 在 Windows bash 中可能失败（返回 422 Pydantic 校验错误）
curl -s -X POST ... -d '{"messages":[{"role":"user","content":"你好"}],"stream":true}'

# 使用英文则正常
curl -s -X POST ... -d '{"messages":[{"role":"user","content":"hello"}],"stream":true}'
```

**根本原因：** Windows bash 在处理命令行参数中的非 ASCII 字符时，编码传递与 Python/FastAPI 的 JSON 解析器不一致，导致 Pydantic 模型校验失败（`There was an error parsing the body`）。

**解决方法：**
1. 使用 ASCII-only 内容测试（`"hello"` 替换 `"你好"`）
2. 将 JSON 写入文件后用 `-d @file.json` 传递
3. 使用 PowerShell 的 `Invoke-RestMethod`
4. 使用 Postman、Bruno 等 GUI 工具

这**不影响实际使用**——用户的工具/客户端（如 OpenAI SDK、Claude Code、自定义工具）使用标准的 HTTP POST 发送 UTF-8 JSON body，不受此限制影响。

### 15.8 `.env` 变更需重启服务

`server.py` 和 `adapter.py` 都在模块加载时调用 `load_dotenv()` 读取 `.env`：

```python
# 模块级
load_dotenv()
MODE = os.environ.get("MODE", "auto").strip().lower()
THINKING = os.environ.get("THINKING", "auto").strip().lower()
```

这意味着**修改 `.env` 后必须重启服务器**才能生效。仅保存文件不会触发重新加载。使用 `--reload` 模式时 uvicorn 会检测文件变更然后重启，但 `.env` 变更不在 uvicorn 的文件监控范围内——需要手动重启。


## 19. 常见调试方法

### 19.1 测试 PoW 和基本连接

```python
from adapter import DeepSeekAdapter, TOKEN, COOKIES
adapter = DeepSeekAdapter(token=TOKEN, cookies=COOKIES)
sid = adapter.create_session()
print(f"Session: {sid}")
```

预期输出：`Session: <uuid>`。如失败检查凭证是否过期。

### 19.2 测试快速模式

```python
content = adapter.chat(sid, "User: 你好")
print(f"Reply: {content}")
```

### 19.3 测试专家模式

```python
content = adapter.chat(sid, "User: 思考一个哲学问题",
                        thinking_enabled=True, search_enabled=False)
print(f"Reply: {content}")
```

### 16.4 测试专家模式流式

```python
for token in adapter.chat_stream(sid, "User: 你好",
                                  thinking_enabled=True):
    if isinstance(token, dict):
        if token.get("__type") == "thinking":
            print(f"[THINK] {token['content']}")
        elif token.get("__type") == "status":
            print(f"[STATUS] {token['status']}")
    else:
        print(token, end="")
```

### 16.5 原始 SSE 抓包

修改 `chat_stream()` 或使用以下片段打印原始 SSE：

```python
resp = adapter._client.post(
    f"{BASE_URL}/api/v0/chat/completion", json=body, headers=headers)
for line in resp.iter_lines():
    print(line)
```

### 16.6 使用 curl 快速测试

**健康检查：**
```bash
curl http://localhost:8080/health
```

**模型列表：**
```bash
curl http://localhost:8080/v1/models
```

**非流式普通对话：**
```bash
curl -X POST http://localhost:8080/v1/chat/completions ^
  -H "Content-Type: application/json" ^
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}],\"stream\":false}"
```

**流式普通对话：**
```bash
curl -X POST http://localhost:8080/v1/chat/completions ^
  -H "Content-Type: application/json" ^
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}],\"stream\":true}"
```

**专家模式（流式）：**
```bash
curl -X POST http://localhost:8080/v1/chat/completions ^
  -H "Content-Type: application/json" ^
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"思考一个哲学问题\"}],\"stream\":true,\"thinking_mode\":true}"
```

**工具调用：**
```bash
curl -X POST http://localhost:8080/v1/chat/completions ^
  -H "Content-Type: application/json" ^
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"北京天气怎么样？\"}],\"tools\":[{\"type\":\"function\",\"function\":{\"name\":\"get_weather\",\"description\":\"获取天气\",\"parameters\":{\"type\":\"object\",\"properties\":{\"city\":{\"type\":\"string\"}}}}]}"
```

### 16.7 排查步骤（按优先级排序）

当服务异常时的系统化排查流程：

1. **健康检查** → `/health` 返回 `{"status":"ok"}`？
2. **凭证有效性** → `adapter.create_session()` 是否成功？
3. **PoW 求解** → WASM 是否正常加载？
4. **快速模式** → 最基本的 `adapter.chat(sid, "User: 你好")` 是否返回？
5. **专家模式** → `thinking_enabled=True` 是否触发 fragment 状态机？
6. **流式输出** → `chat_stream()` 能否逐 token 产出？
7. **工具调用** → DSML 标签是否被 StreamSieve 正确捕获？

### 16.8 常见错误

| 错误信息 | 可能原因 | 解决 |
|---------|---------|------|
| `Authorization Failed (invalid token)` | Token 过期 | 更新 .env |
| `Update to the latest version to use Expert` | X-App-Version 版本过低 | 改为 `20241129.1` |
| `WASM solver found no solution` | PoW 难度过高/求解异常 | 重试 |
| `Session creation failed` | PoW 过期/凭证无效 | 重试/更新凭证 |
| `Server disconnected without sending a response` | DeepSeek 服务端超时或 httpx 超时太短 | 检查 timeout=120；重试 |
| `data: {"type":"error","content":"..."}` | DeepSeek 业务错误 | 根据 content 排查 |
| 修改代码后行为不变 | `__pycache__` 陈旧缓存 | 删除 `__pycache__` 目录 |
| `ImportError: cannot import name 'X' from 'adapter'` | 模块缓存旧版本 | 删除 `__pycache__` 后重启 |
| `PoWError: WASM solver found no solution` | WASM 二进制不兼容 | 检查 wasmtime 版本或重新提取 WASM |
| 进程已退出但端口仍占用 | 前一个 uvicorn 未完全终止 | 用 `netstat -ano | findstr :<PORT>` 找到 PID 后 taskkill |

### 16.9 使用 HAR 分析

1. 浏览器 F12 → Network → 导出 HAR
2. 用 `jq` 或 Python 解析：
```python
import json
with open("file.har") as f:
    har = json.load(f)
for entry in har["log"]["entries"]:
    url = entry["request"]["url"]
    if "chat/completion" in url:
        print(url, entry["request"]["postData"]["text"])
```

---

## 20. 协议变更预警

以下因素可能导致项目失效，需要及时更新：

### 20.1 前端更新

DeepSeek 前端更新可能改变：
- API 端点路径（`/api/v0/chat/completion` → 其他）
- 请求体字段名/格式
- SSE 事件结构
- PoW 算法或 challenge 格式
- 请求头要求

**检测方法**：定期用浏览器 DevTools 抓取最新 HAR 对比。

### 17.2 WASM 更新

`sha3_wasm_bg.wasm` 可能被 DeepSeek 更新：
- 导出函数名变更
- 求解算法变更
- 难度算法调整

**检测方法**：检查 `create_pow_challenge` 响应中的 `algorithm` 字段。

### 17.3 反爬升级

DeepSeek 可能引入新的反爬机制：
- 额外的签名/加密头
- JS Challenge（类似 Cloudflare）
- 请求频率限制
- IP 封锁

### 17.4 维护策略

1. **定期抓包**（至少每月一次）
2. **HAR 对比**：保存基线 HAR 文件，对比差异
3. **降级方案**：当专家模式失效时，至少保证快速模式可用
4. **抓包要点**：
   - 关注 `chat_session/create` 和 `chat/completion` 两个核心端点
   - 记录所有请求头，特别关注 `X-` 开头的自定义头
   - 记录 SSE 事件序列，注意新增的 `p` 路径或 `o` 操作
   - 关注 `model_type` 字段的枚举值变化

### 17.5 WASM 二进制更新流程

DeepSeek 前端更新可能导致 WASM 二进制变化。完整更新流程：

```bash
# 步骤 1: 从 DeepSeek 前端提取新 WASM
# 方法 A: 浏览器 DevTools → Network → 搜索 "sha3_wasm_bg.wasm" → 下载
# 方法 B: 在 JS 中定位 wasm 加载点
#   打开 chat.deepseek.com → F12 → Sources
#   搜索 "sha3_wasm_bg.wasm" 找到加载代码

# 步骤 2: 覆盖旧文件
copy /y new_sha3_wasm_bg.wasm sha3_wasm_bg.wasm

# 步骤 3: 验证导出函数
python -c "
from wasmtime import Store, Module, Instance
with open('sha3_wasm_bg.wasm', 'rb') as f:
    module = Module(Store().engine, f.read())
instance = Instance(Store(), module, [])
exports = instance.exports(Store())
print('Exports:', list(exports.keys()))
print('has wasm_solve:', 'wasm_solve' in exports)
print('has memory:', 'memory' in exports)
"

# 步骤 4: 测试 PoW 求解
python -c "
from adapter import DeepSeekAdapter, TOKEN, COOKIES
a = DeepSeekAdapter(token=TOKEN, cookies=COOKIES)
c = a._get_challenge()
print('Challenge solved')
"

# 步骤 5: 测试完整对话
python -c "
from adapter import DeepSeekAdapter, TOKEN, COOKIES
a = DeepSeekAdapter(token=TOKEN, cookies=COOKIES)
sid = a.create_session()
r = a.chat(sid, 'User: 你好')
print('Reply:', r[:100])
"
```

**变更检测脚本**（推荐定期运行）：
```python
import hashlib
old_hash = "已知的旧文件 SHA256"  # 首次运行时记录
with open("sha3_wasm_bg.wasm", "rb") as f:
    new_hash = hashlib.sha256(f.read()).hexdigest()
if new_hash != old_hash:
    print("WARNING: WASM binary has changed!")
    print(f"Old: {old_hash}")
    print(f"New: {new_hash}")
```

---

> 本文档最后更新：2026-08-08
> 基于 `chat.deepseek.com` HAR 抓包分析（2026-05-06）
> WASM 引擎版本：`sha3_wasm_bg.wasm`（DeepSeek 前端提取，含 `__wbindgen_export_0` malloc / `__wbindgen_export_1` realloc / `__wbindgen_export_2` free）
> 协议版本：DeepSeek Chat v2.0.0 (X-Client-Version)
