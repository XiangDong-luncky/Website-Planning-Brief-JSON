# Website Planning Brief AI

输入一句网站想法，AI 生成结构化的《网站策划书》JSON，并为每个页面生成可直接预览的静态 HTML 概念稿。

## 功能

- 输入网站想法，输出策划书：站点名称、标语、项目概述、目标用户、核心功能、视觉规范、页面清单
- 每个页面附带一份独立的静态 HTML 概念稿，前端通过 iframe 实时预览
- 前后端分离三层架构，AI 层可独立替换模型或 Prompt

## 架构

```
浏览器
  │  POST /api/generate  { "idea": "..." }
  ▼
Vue 3 + Vite (5173)          ← 开发时由 Vite 代理 /api，浏览器视角同源
  │  代理到 http://127.0.0.1:8080
  ▼
Spring Boot 3 (8080)         ← 参数校验、错误透传、CORS
  │  POST http://127.0.0.1:8000/generate
  ▼
FastAPI ai-service (8000)    ← 构造 Prompt、调模型、JSON 解析与结构校验
  │  HTTPS
  ▼
智谱 GLM-4.7-Flash
```

## 目录结构

```
Website Planning Brief JSON/
├── ai-service/          # AI 层：FastAPI + 智谱 GLM
│   ├── main.py          # POST /generate、GET /health
│   ├── mock_data.py     # 离线联调数据
│   └── requirements.txt
├── backend/             # 转发层：Spring Boot 3
│   └── src/main/java/com/websitebrief/backend/
│       ├── controller/GenerateController.java   # POST /api/generate
│       ├── service/AiServiceClient.java         # RestTemplate 调用 AI 层
│       ├── dto/GenerateRequest.java             # 请求体校验
│       └── exception/GlobalExceptionHandler.java
├── frontend/            # 展示层：Vue 3 + Vite
│   └── src/App.vue      # 左侧输入 + 右侧策划书 / iframe 预览
├── .gitignore
└── README.md
```

## 技术栈

| 层 | 技术 | 端口 |
| --- | --- | --- |
| 前端 | Vue 3、Vite | 5173 |
| 转发层 | Spring Boot 3.5、Java 17 | 8080 |
| AI 层 | Python 3.11+、FastAPI、Uvicorn | 8000 |
| 模型 | 智谱 GLM-4.7-Flash（OpenAI 兼容接口） | - |

## 本地运行

按 **AI 层 → 后端 → 前端** 的顺序启动，需要三个终端。

### 1. 启动 AI 服务（终端一）

```powershell
cd "D:\AI Practice\Website Planning Brief JSON\ai-service"

# 首次运行：创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 配置 Key：复制 .env.example 为 .env，填入 ZHIPU_API_KEY

# 启动
.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

验证：访问 http://127.0.0.1:8000/health ，`api_key_configured` 应为 `true`。

> 没配 Key 时可设置 `MOCK_LLM=1`，接口会返回示例数据，用于前端联调。

### 2. 启动后端（终端二）

```powershell
cd "D:\AI Practice\Website Planning Brief JSON\backend"
mvn spring-boot:run
```

验证：访问 http://127.0.0.1:8080/api/generate （GET 会返回 405，说明服务已启动）。

打包运行的方式：

```powershell
mvn package
java -jar target/backend-0.1.0.jar
```

### 3. 启动前端（终端三）

```powershell
cd "D:\AI Practice\Website Planning Brief JSON\frontend"
npm install
npm run dev
```

打开 http://localhost:5173 ，输入想法即可生成。

> Windows 上 Vite 默认只绑定 IPv6 的 `localhost`，如果 `127.0.0.1:5173` 打不开属正常现象，用 `localhost` 访问即可。

## 接口

### POST /api/generate（经 Spring Boot）

请求：

```json
{ "idea": "一个记录咖啡豆风味的社区网站" }
```

响应：策划书 JSON（结构由 AI 层保证）

```json
{
  "siteName": "...",
  "tagline": "...",
  "summary": "...",
  "targetAudience": "...",
  "coreFeatures": ["..."],
  "styleGuide": {
    "primaryColor": "#2563eb",
    "secondaryColor": "#0f172a",
    "fontFamily": "...",
    "tone": "..."
  },
  "pages": [
    {
      "id": "home",
      "name": "首页",
      "path": "/",
      "purpose": "...",
      "sections": [{ "name": "...", "description": "..." }],
      "html": "<!DOCTYPE html>..."
    }
  ]
}
```

错误响应统一为 `{ "detail": "..." }`，HTTP 状态码与 AI 层保持一致（400 参数错误 / 502 模型或结构错误 / 503 AI 服务未启动 / 504 连接超时）。

## 环境变量

`ai-service/.env`（不提交到 Git）：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `ZHIPU_API_KEY` | 智谱 API Key | 必填 |
| `ZHIPU_MODEL` | 模型编码 | `glm-4.7-flash` |
| `ZHIPU_THINKING` | `disabled` 关闭思考 | `disabled` |
| `LLM_TIMEOUT` | 请求超时（秒） | `180` |
| `MAX_TOKENS` | 最大输出 token | `12000` |
| `MOCK_LLM` | `1` 时返回示例数据 | `0` |

后端配置见 `backend/src/main/resources/application.yml`，AI 服务地址由 `ai.service.base-url` 指定。

## 常见问题

- **端口被占用**：`netstat -ano | findstr :8000`（或 8080 / 5173）找到 PID 后 `taskkill /F /PID <pid>`，或换端口启动。
- **前端报“连不上后端”**：确认 Spring Boot 在 8080、AI 服务在 8000，且三个服务都已启动。
- **浏览器打不开 127.0.0.1:5173**：Vite 在 Windows 上默认绑定 `localhost`（IPv6），改用 http://localhost:5173 。
- **502 且 detail 提到 JSON 结构**：查看 `ai-service/debug/last_raw.txt` 中模型原始输出，按提示调整 `main.py` 的 Prompt 或 `MAX_TOKENS`。
- **401 令牌已过期或验证不正确**：检查 `.env` 中的 Key，重启 AI 服务。
- **Maven 报 `Non-readable settings ... input contained no data`**：`conf/settings.xml` 被清空了，恢复一份标准模板即可。

## Roadmap

- [ ] 生成任务异步化，前端轮询或 SSE 展示进度
- [ ] 策划书历史记录与导出（Markdown / PDF）
- [ ] 单页 HTML 重新生成与局部修改
- [ ] 多模型提供商切换

## License

MIT
