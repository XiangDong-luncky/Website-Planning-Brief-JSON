# Website Planning Brief AI

**自带产品经理和架构师思维的 AI 建站助手。**

说一句「我想做一个咖啡社区」，它会像真正的产品经理一样追问需求盲区，然后交付一份网站策划书、三张 Mermaid 架构图，以及可以直接预览的页面概念稿。

![Demo](./assets/demo.gif)

## ✨ 核心特性

- **🔑 BYOK，模型自由**：自带任意 OpenAI 兼容模型的 Key（智谱 GLM、DeepSeek、Moonshot、自建网关均可）。Web 端密钥只存浏览器 sessionStorage，MCP 端只读进程环境变量，服务端零存储。
- **🧠 独创「查漏补缺」式需求澄清**：不是问卷式收集，而是顺着你提到的功能联想配套能力——提到个人中心就追问好友私信，提到详情页就追问导航推荐，每轮只问一个最关键的盲区。
- **🗺 一键生成三大 Mermaid 架构图**：功能脑图（mindmap）、系统架构（graph TD）、核心业务时序（sequenceDiagram）。服务端做语法级校验，不合法自动纠错重试，前端可直接渲染并全屏查看。
- **🖥 Web UI 与 MCP Server 双形态**：同一套 Prompt 和校验逻辑，既能在浏览器里可视化操作，也能作为 MCP 插件无缝接入 Cursor / Codex / Claude Desktop。
- **📦 结构化交付**：策划书 JSON + 每页独立的现代风格静态 HTML，iframe 即开即看，可直接作为开发前的原型基线。

## 🚀 快速开始

### 方式一：作为 MCP 插件使用（最快，1 分钟）

不需要启动任何 Web 服务，只要 Python 3.11+。

```powershell
cd mcp-server
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> macOS / Linux 把 `.venv\Scripts\python.exe` 换成 `.venv/bin/python`。

<details open>
<summary><b>Cursor</b> · 项目内 <code>.cursor/mcp.json</code> 或全局 <code>%USERPROFILE%\.cursor\mcp.json</code></summary>

```json
{
  "mcpServers": {
    "website-planning-brief": {
      "command": "<REPO>/mcp-server/.venv/Scripts/python.exe",
      "args": ["<REPO>/mcp-server/mcp_server.py"],
      "env": {
        "OPENAI_API_KEY": "你的 API Key",
        "OPENAI_BASE_URL": "https://open.bigmodel.cn/api/paas/v4",
        "MODEL_NAME": "glm-4.7-flash"
      }
    }
  }
}
```

</details>

<details open>
<summary><b>Codex CLI</b> · <code>~/.codex/config.toml</code></summary>

```toml
[mcp_servers.website-planning-brief]
command = '<REPO>/mcp-server/.venv/Scripts/python.exe'
args = ['<REPO>/mcp-server/mcp_server.py']
env = { OPENAI_API_KEY = "你的 API Key", OPENAI_BASE_URL = "https://open.bigmodel.cn/api/paas/v4", MODEL_NAME = "glm-4.7-flash" }
```

</details>

把 `<REPO>` 替换成你克隆仓库的绝对路径，填上 API Key，重启编辑器，然后在对话里直接说：

> 我想做一个记录咖啡豆风味的社区网站，先帮我澄清需求。

AI 会自动调用 `chat_requirement → generate_outline → generate_page_html`。Claude Desktop 同样支持，配置见 [mcp-server/README.md](mcp-server/README.md)。

### 方式二：本地运行 Web UI

前置：Python 3.11+、JDK 17+、Node 20+。

```powershell
# 首次安装依赖
cd ai-service
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

cd ../frontend
npm install
```

开三个终端，在仓库根目录分别执行：

```powershell
# 终端 1：AI 层
cd ai-service
.venv\Scripts\python.exe -m uvicorn main:app --port 8000

# 终端 2：Spring Boot
cd backend
mvn spring-boot:run

# 终端 3：前端
cd frontend
npm run dev
```

打开 **http://localhost:5173**，点右上角「配置模型」填入 Key，即可开始聊天。

> macOS / Linux 使用 `.venv/bin/python`；Windows 上请用 `localhost` 而不是 `127.0.0.1` 访问前端。

## 🏗 技术架构

```
Web   浏览器（Vue 3）──► Spring Boot ──► FastAPI ──► OpenAI 兼容模型
                         字节流透传      BYOK / Prompt / 校验

MCP   Cursor / Codex / Claude ──stdio──► mcp_server.py ──► 同一个模型
```

- Web 端每个请求携带 `userConfig`（apiKey / baseUrl / modelName），AI 层按请求动态创建客户端。
- MCP 端从配置的环境变量读取同一组信息。
- 两端共用 System Prompt、JSON 解析与 Mermaid 语法校验，行为保持一致。

## 📖 详细文档

- [API 接口、错误约定、环境变量、项目结构](docs/API.md)
- [MCP Server 安装、配置与排错](mcp-server/README.md)

## 🗺 Roadmap

- [x] 多轮「查漏补缺」式需求澄清
- [x] JSON 模式 + 自动纠错重试
- [x] BYOK 模型配置（服务端不保存密钥）
- [x] 三张 Mermaid 图：功能脑图 / 系统架构 / 核心时序
- [x] 双形态：Web UI + MCP Server（Cursor / Codex / Claude Desktop）
- [ ] VS Code 插件：在编辑器内一键生成策划书与页面概念稿
- [ ] JetBrains 插件
- [ ] 浏览器扩展：边浏览网页边生成策划书
- [ ] Docker Compose 一键启动
- [ ] 策划书导出 Markdown / PDF
- [ ] 生成任务异步化与 SSE 进度

## 🤝 Contributing

欢迎 Issue 和 PR。提交前请确保 `mvn package`、`npm run build`、`py_compile` 均通过；涉及 Prompt 的改动请附生成结果对比。

## License

MIT
