# mcp-server

把 Website Planning Brief AI 的核心能力封装成一个独立、自包含的 MCP Server：

- 不依赖 FastAPI / Spring Boot / 8000 端口，直接通过 `openai` SDK 调模型
- 通过 MCP 客户端配置的 **环境变量** 获取 Key 和模型信息
- 通过 stdio 传输接入 Cursor / Claude Desktop

## 工具

| 工具 | 作用 | 返回 |
| --- | --- | --- |
| `chat_requirement` | 多轮需求澄清，产品经理式查漏补缺 | 纯文本追问 |
| `generate_outline` | 生成策划书大纲 JSON，含三张 Mermaid 图 | JSON 字符串 |
| `generate_page_html` | 为单个页面生成现代风格静态 HTML | HTML 字符串 |

## 安装

```powershell
cd mcp-server
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> 在仓库根目录执行；macOS / Linux 把 `.venv\Scripts\python.exe` 换成 `.venv/bin/python`。

> 代码基于 MCP Python SDK 2.x 的 `MCPServer`（`from mcp.server.mcpserver import MCPServer`）。如果你看到 `No module named 'mcp.server.fastmcp'`，说明装的是 1.x，执行 `pip install -U "mcp>=2.0.0"` 即可。

## 环境变量

| 变量 | 必填 | 说明 | 默认值 |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | 是 | 你的模型 API Key | - |
| `OPENAI_BASE_URL` | 否 | OpenAI 兼容地址 | `https://open.bigmodel.cn/api/paas/v4` |
| `MODEL_NAME` | 否 | 模型编码（也兼容 `OPENAI_MODEL`） | `glm-4.7-flash` |
| `MODEL_TIMEOUT` | 否 | 单次请求超时秒数 | `180` |
| `MODEL_THINKING` | 否 | 智谱思考模式，仅对智谱域名生效 | `disabled` |
| `CHAT_MAX_TOKENS` | 否 | 对话回复上限 | `1024` |
| `OUTLINE_MAX_TOKENS` | 否 | 大纲输出上限 | `8192` |
| `HTML_MAX_TOKENS` | 否 | 单页 HTML 输出上限 | `16000` |
| `HISTORY_CHAR_BUDGET` | 否 | 历史对话字符预算 | `24000` |

## Cursor 配置

在项目根目录创建 `.cursor/mcp.json`（只对本项目生效），或编辑全局 `%USERPROFILE%\.cursor\mcp.json`：

```json
{
  "mcpServers": {
    "website-planning-brief": {
      "command": "<REPO>/mcp-server/.venv/Scripts/python.exe",
      "args": [
        "<REPO>/mcp-server/mcp_server.py"
      ],
      "env": {
        "OPENAI_API_KEY": "你的 API Key",
        "OPENAI_BASE_URL": "https://open.bigmodel.cn/api/paas/v4",
        "MODEL_NAME": "glm-4.7-flash"
      }
    }
  }
}
```

保存后重启 Cursor（或在 Settings → MCP 里刷新）。把 `<REPO>` 替换成你克隆仓库的绝对路径；Windows 支持正斜杠，macOS / Linux 使用 `.venv/bin/python`。工具状态变绿后，在聊天里输入：

> 我想做一个记录咖啡豆风味的社区网站，先帮我澄清需求。

Cursor 会自动调用 `chat_requirement`；聊几轮后让它生成策划书，再让它为首页生成 HTML。

## Claude Desktop 配置

编辑 `%APPDATA%\Claude\claude_desktop_config.json`，把上面 `mcpServers` 里的条目原样加进去，然后完全退出并重启 Claude Desktop。

## 手动调试

```powershell
cd mcp-server
$env:OPENAI_API_KEY="你的 Key"
$env:OPENAI_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
$env:MODEL_NAME="glm-4.7-flash"
.venv\Scripts\python.exe mcp_server.py
```

启动后会等待 stdin 上的 MCP 消息（不会有输出，这是正常的）；按 Ctrl+C 退出。日志全部走 stderr。

也可以临时建一个 `mcp-server/.env` 放配置，本地运行时会自动读取（该文件已被根目录 `.gitignore` 忽略，不会提交）。

## 常见问题

- **401**：Key 错误或没有模型权限，检查 `OPENAI_API_KEY` 与 `MODEL_NAME`。
- **429**：模型限流，稍后重试或换模型。
- **400 且提示 model 不支持**：检查 `MODEL_NAME` 是否是 `OPENAI_BASE_URL` 对应的模型编码。
- **Cursor 里工具不出现**：确认 JSON 路径转义正确、Python 路径指向 `.venv` 里的解释器、重启 Cursor。
- **生成的 HTML 太长**：MCP 客户端会完整接收；如需保存成文件，让 Cursor 把结果写入 `.html` 文件即可。
