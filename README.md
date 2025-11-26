# Weather Push Agent

一个基于 LangChain 的自动化天气推送服务，直接注入高德地图 MCP 工具，由大模型调用获取天气，并通过飞书机器人推送每日报告（含出行与穿衣建议）。

## 项目目的

- 每日定时查询指定城市的实时与预报天气
- 自动生成“出行与穿衣建议”（气温 ≤10℃ 提醒保暖；出现“雨”提醒携带雨具）
- 通过飞书机器人以交互卡片推送给用户/群

## 架构与特性

- MCP 集成：直接注入高德 MCP 工具（`amap.weather.current` 等），由 LLM 触发调用
- LLM 选择：支持阿里云通义千问（DashScope）或谷歌 Gemini，自动按环境变量检测
- 推送方式：飞书自定义机器人 Webhook，交互卡片展示完整报告
- 定时任务：基于 APScheduler 的每日定时执行；也支持 HTTP 手动触发

## 安装要求

- Python ≥ 3.11
- 建议使用虚拟环境（venv/conda）

## 快速开始

### 1. 克隆与环境

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. 安装依赖

项目的依赖在 `pyproject.toml` 中，如可用直接安装：

```bash
pip install -U apscheduler dashscope fastapi langchain langchain-community \
  langchain-core langchain-mcp-adapters langchain-openai python-dotenv ruff uvicorn
```

如使用 `uv`（更快的包管理器）：

```bash
uv pip install -U apscheduler dashscope fastapi langchain langchain-community \
  langchain-core langchain-mcp-adapters langchain-openai python-dotenv ruff uvicorn
```

### 3. 配置环境变量

将 `.env-example` 复制为 `.env` 并填写真实值：

```bash
cp .env-example .env
```

`.env` 需要包含以下键：

- `TARGET_CITY_CODE`：目标城市编码（如杭州 `330100`）
- `TARGET_CITY`：目标城市中文名（可选）
- `AMAP_API_KEY`：高德 MCP 服务访问密钥（从 https://mcp.amap.com 申请）
- `FEISHU_WEBHOOK_URL`：飞书自定义机器人 Webhook 地址
- `DASHSCOPE_API_KEY`：阿里云通义千问 API Key（可选）
- `GEMINI_API_KEY`：谷歌 Gemini API Key（可选）
- 可选模型键（如在 `.env-example` 中所示）：`DASHSCOPE_API_MODEL`、`GEMINI_API_MODEL`

说明：

- 若设置了 `DASHSCOPE_API_KEY`，默认使用通义千问；否则若设置了 `GEMINI_API_KEY`，使用 Gemini。
- 至少需要一个 LLM 的 API Key 才能生成报告与建议。

### 4. 运行服务

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

启动后：

- `GET /`：查看服务状态与配置
- `GET /trigger-weather`：手动触发一次天气查询与飞书推送

### 5. 定时任务

服务启动后会注册每日执行的定时任务（时区：`Asia/Shanghai`）。时间在 `main.py` 中通过 APScheduler 配置，可按需调整。

## 获取 API Key

### 高德 MCP（AMAP）

- 访问 https://mcp.amap.com 注册并创建 MCP Key
- 将 Key 填入 `.env` 的 `AMAP_API_KEY`

### 阿里云通义千问（DashScope）

- 申请地址：https://dashscope.aliyun.com
- 获取 `DASHSCOPE_API_KEY` 并写入 `.env`

### 谷歌 Gemini

- 申请地址：https://ai.google.dev
- 获取 `GEMINI_API_KEY` 并写入 `.env`

## 使用说明

- 系统提示会引导 LLM：
  - 使用 MCP 天气工具获取天气
  - 生成含“实时天气、今日/未来预报、出行与穿衣建议”的报告
  - 调用 `SendFeishuMessage` 推送到飞书
- 出行与穿衣建议规则（基础版）：
  - 气温 ≤ 10℃：提醒“天气较冷，注意保暖，穿厚衣服”
  - 出现“雨”（实时或预报）：提醒“可能有降雨，出门携带雨具，注意交通安全”

## 故障排查

- LLM 请求超时：检查网络可达性与 API Key 配额；可临时增大超时设置
- MCP 工具名变动：日志中查看 `tool_calls` 的 `name` 并在代码调整提示说明
- 推送失败：检查 `FEISHU_WEBHOOK_URL` 是否可用、网络是否可达
