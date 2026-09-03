# saiClawBot

手写的个人 AI 助理 Agent：多渠道接入 → 自研 ReAct 执行循环 → 工具系统 → 分层记忆 → 全链路 trace。
不依赖 LangChain / LangGraph 等编排框架，编排逻辑全部自己实现。

## 架构

```
Telegram / CLI ──► gateway(适配器归一化为 InboundMessage)
                          │
                          ▼
                    AgentRunner (agent/runner.py)
                    ┌─ ReAct 循环：LLM → tool_use → 并发执行 → tool_result → 循环
                    ├─ ToolRegistry：@tool 装饰器注册 + pydantic 自动生成 schema + 风险分级
                    ├─ Memory：滑窗 + LLM 摘要压缩，切点保证 tool_use/result 成对
                    └─ Store(SQLite)：会话消息 / 摘要 / trace(token、耗时)
```

## 快速开始

```bash
cd D:\saiClawBot
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
copy .env.example .env      # 填 ANTHROPIC_API_KEY
python -m saiclawbot cli
```

### OpenCode Go

项目通过 Anthropic Messages API 调用模型，OpenCode Go 可以直接配置，无需修改代码。将 `.env` 中的 LLM 部分改为：

```dotenv
ANTHROPIC_API_KEY=你的_OpenCode_Go_API_Key
ANTHROPIC_BASE_URL=https://opencode.ai/zen/go/v1
MODEL=deepseek-v4-flash
```

当前依赖的 Anthropic Python SDK 会自动请求 `/v1/messages`；项目会把带 `/v1` 的 API 根地址自动规范化，避免产生重复的 `/v1/v1/messages` 路径。模型可替换为 OpenCode Go 当前可用的其他裸模型 ID，例如 `qwen3.7-plus`。

Telegram：`pip install -e .[telegram]`，在 `.env` 填 `TELEGRAM_BOT_TOKEN` 与 `ALLOWED_USER_IDS`，然后 `python -m saiclawbot telegram`。

测试（不需要 API key）：`pytest`

## 目录

```
src/saiclawbot/
  __main__.py        入口与装配
  config.py          环境变量配置
  llm.py             Anthropic SDK 薄封装（无编排逻辑）
  storage.py         SQLite：messages / summaries / traces
  memory.py          上下文组装与摘要压缩
  agent/runner.py    Agent 循环、工具执行、危险确认、步数上限
  tools/registry.py  工具注册中心
  tools/builtin.py   内置工具：get_time / read_file / write_file / shell
  gateway/           渠道适配：cli / telegram
tests/               FakeLLM 驱动的循环与记忆测试
```

## 路线图

- [x] 单渠道 + 会话持久化 + ReAct 循环 + 工具系统 + 摘要压缩 + trace
- [ ] 长期记忆：向量召回（sqlite-vec / chromadb）
- [ ] MCP client：挂载外部工具服务
- [ ] Docker 沙箱执行 shell
- [ ] Telegram 危险操作 inline keyboard 确认
- [ ] APScheduler 定时主动任务
- [ ] 流式输出
- [ ] 飞书渠道
- [ ] trace 看板
