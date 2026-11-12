# Website Planning Brief AI

一个 BYOK（Bring Your Own Key）的 AI 建站策划工具：先和 AI 产品经理多轮澄清需求，再生成结构化策划书与 Mermaid 系统架构图，最后按页生成现代风格的静态 HTML 概念稿，直接在 iframe 中预览。

## 工作流

1. **配置模型**：点击右上角「配置模型」，填入你自己的 `apiKey`、`baseUrl`、`modelName`（OpenAI 兼容接口）。服务端不保存密钥，也不提供内置额度。
2. **需求澄清**：左侧聊天窗口里描述想法，AI 按产品评审清单（受众、业务流、数据校验、异常处理、权限）逐轮指出最大的逻辑盲区，每轮只追问一个问题。
3. **生成策划书**：点击「信息已完善，生成策划书」，得到站点信息、视觉规范、页面规划，以及三张 Mermaid 图：功能脑图（featureMindmap）、系统架构图（systemDiagram）、核心业务时序图（coreFlowDiagram）。这一步不生成 HTML。
4. **图表与页面预览**：右侧顶部有三个图表 Tab（功能脑图 / 系统架构 / 核心流程），生成大纲后自动渲染；点击「全屏查看」或双击图表可放大，按 Esc 或点遮罩关闭。点击页面 Tab 才触发该页的 HTML 生成；生成完成后，页面预览同样支持「全屏查看」。

## 架构

```
浏览器（Vue 3 + Vite，localhost:5173）
  │  每个请求携带 userConfig {apiKey, baseUrl, modelName}
  │  Vite 代理 /api，浏览器视角同源
  ▼
Spring Boot 3（127.0.0.1:8080）
  │  透明转发 JSON、错误与状态码；不解析、不记录密钥
  │  /api/chat               → POST /chat
  │  /api/generate-outline   → POST /generate-outline
  │  /api/generate-page-html → POST /generate-page-html
  ▼
FastAPI ai-service（127.0.0.1:8000）
  │  校验 userConfig，按请求动态实例化 OpenAI 客户端
  │  拼 Prompt、JSON 校验、自动纠错重试、Mermaid 清洗
  ▼
智谱 GLM 或其他 OpenAI 兼容模型服务
```

## 目录结构

```
Website Planning Brief JSON/
├── ai-service/          # AI 层：FastAPI（BYOK + 三段式生成）
│   ├── main.py          # /chat、/generate-outline、/generate-page-html
│   ├── mock_data.py     # 离线联调数据
│   └── requirements.txt
├── backend/             # 转发层：Spring Boot 3
│   └── src/main/java/com/websitebrief/backend/
│       ├── controller/GenerateController.java   # 三个 /api 接口
│       ├── service/AiServiceClient.java         # RestTemplate 字节流透传
│       └── exception/{AiServiceUnavailableException,InvalidRequestException,GlobalExceptionHandler}.java
├── frontend/            # 展示层：Vue 3 + Vite + Mermaid
│   └── src/App.vue      # 聊天 + BYOK 设置 + 架构图 + 逐页 iframe 预览
├── .gitignore
└── README.md
```

## 技术栈

| 层 | 技术 | 端口 |
| --- | --- | --- |
| 前端 | Vue 3、Vite、Mermaid | 5173 |
| 转发层 | Spring Boot 3.5、Java 17 | 8080 |
| AI 层 | Python 3.11+、FastAPI、Uvicorn | 8000 |
| 模型 | 任意 OpenAI 兼容服务（默认示例：智谱 GLM-4.7-Flash） | - |

## 本地运行

三个终端，按 **AI 层 → 后端 → 前端** 启动。

### 1. 启动 AI 服务（终端一）

```powershell
cd "D:\AI Practice\Website Planning Brief JSON\ai-service"

# 首次运行
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

验证：http://127.0.0.1:8000/health ，应看到 `version: 3.0.0`、`byok: true`。

### 2. 启动后端（终端二）

```powershell
cd "D:\AI Practice\Website Planning Brief JSON\backend"
mvn spring-boot:run
```

### 3. 启动前端（终端三）

```powershell
cd "D:\AI Practice\Website Planning Brief JSON\frontend"
npm install
npm run dev
```

打开 http://localhost:5173 ，先点右上角「配置模型」填入 Key，再开始聊天。

> Windows 上 Vite 默认只绑定 IPv6 的 `localhost`，`127.0.0.1:5173` 打不开属正常现象。

### 离线联调（不调用模型）

1. 在 `ai-service/.env` 中设置 `MOCK_LLM=1` 并重启 AI 服务。
2. 前端「配置模型」里随便填一组非空值（例如 `demo` / `https://open.bigmodel.cn/api/paas/v4` / `glm-4.7-flash`），三个接口会返回 `mock_data.py` 中的数据。

## 接口

所有生成接口的请求体都必须带上：

```json
{
  "userConfig": {
    "apiKey": "你的 Key",
    "baseUrl": "https://open.bigmodel.cn/api/paas/v4",
    "modelName": "glm-4.7-flash"
  }
}
```

### POST /api/chat

```json
{
  "messages": [{ "role": "user", "content": "我想做一个咖啡社区网站" }],
  "userConfig": { "apiKey": "...", "baseUrl": "...", "modelName": "..." }
}
```

响应：`{ "reply": "明白。用户提交记录时如果评分和笔记都为空，你希望……" }`

### POST /api/generate-outline

请求体同上（完整对话）。响应：

```json
{
  "siteName": "豆香志",
  "tagline": "...",
  "summary": "...",
  "targetAudience": "...",
  "coreFeatures": ["..."],
  "styleGuide": {
    "primaryColor": "#8b5e34",
    "secondaryColor": "#1f2937",
    "fontFamily": "system-ui, -apple-system, 'Microsoft YaHei', sans-serif",
    "tone": "温暖、有质感、偏杂志风格"
  },
  "featureMindmap": "mindmap\n  豆香志\n    用户模块\n      注册登录",
  "systemDiagram": "graph TD\n  U[用户浏览器] --> W[前端页面]\n  W --> G[接口网关]",
  "coreFlowDiagram": "sequenceDiagram\n  participant U as 用户\n  participant W as 前端\n  U->>W: 提交记录",
  "pages": [
    {
      "id": "home",
      "name": "首页",
      "path": "/",
      "purpose": "...",
      "sections": [{ "name": "首屏 Hero", "description": "..." }]
    }
  ]
}
```

三个图表字段都是纯 Mermaid 代码（服务端已去掉 ```mermaid 围栏），前端用 mermaid.render() 直接渲染。服务端只校验语法类型与最小复杂度，图表内容由模型根据业务自由设计。

### POST /api/generate-page-html

```json
{
  "page": {
    "id": "home",
    "name": "首页",
    "path": "/",
    "purpose": "...",
    "sections": [{ "name": "首屏 Hero", "description": "..." }]
  },
  "styleGuide": { "primaryColor": "#8b5e34", "secondaryColor": "#1f2937", "fontFamily": "...", "tone": "..." },
  "site": { "siteName": "豆香志", "tagline": "记录每一杯咖啡的风味" },
  "userConfig": { "apiKey": "...", "baseUrl": "...", "modelName": "..." }
}
```

响应：`{ "pageId": "home", "html": "<!DOCTYPE html>..." }`

### 错误约定

所有错误统一为 `{ "detail": "..." }`：

| 状态码 | 场景 |
| --- | --- |
| 400 | 缺少/不完整 `userConfig`、`baseUrl` 非法、模型名不受支持、请求体格式错误 |
| 401 | 模型服务鉴权失败（Key 无效或无权限） |
| 429 | 模型服务限流 |
| 502 | 上游异常、两次生成都未得到合法 JSON |
| 503 | Spring 连不上 AI 服务（8000 未启动） |
| 504 | 模型请求超时或网络不可达 |

## 密钥与安全

- 前端只把 API Key 存在 **sessionStorage**（关闭标签页即清除），`baseUrl` 和模型名存 localStorage。
- 每次请求把 `userConfig` 发给 Spring 与 FastAPI；FastAPI 用它动态创建客户端，**不写日志、不落盘**。
- Spring 关闭了请求详情日志（`spring.mvc.log-request-details: false`），避免请求体中的 Key 出现在异常日志里。
- 这是纯前端 BYOK 方案，请只在可信的本地部署中使用；公网部署时仍建议加登录与 HTTPS。

## 环境变量

`ai-service/.env`（服务端不再保存 API Key）：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `MOCK_LLM` | `1` 时返回示例数据，不调用模型 | `0` |
| `ZHIPU_THINKING` | 智谱思考模式，仅对智谱域名生效 | `disabled` |
| `LLM_TIMEOUT` | 单次模型请求超时（秒） | `180` |
| `CHAT_MAX_TOKENS` | 对话回复上限 | `1024` |
| `OUTLINE_MAX_TOKENS` | 大纲输出上限（含 Mermaid） | `6144` |
| `HTML_MAX_TOKENS` | 单页 HTML 输出上限 | `16000` |
| `HISTORY_CHAR_BUDGET` | 历史对话字符预算 | `24000` |

## 常见问题

- **界面提示缺少模型配置**：点击右上角「配置模型」，三项都要填写；保存后按钮旁的圆点会变绿。
- **401**：Key 无效或没有该模型权限，检查 `modelName` 与 `baseUrl` 是否匹配。
- **429**：免费模型限流，稍后重试或换一个模型 / Key。
- **图表 Tab 渲染失败**：查看 `ai-service/debug/outline_result.json` 中对应的 `featureMindmap` / `systemDiagram` / `coreFlowDiagram` 字段。服务端已按图类型校验语法并自动重试，但节点文案里的特殊字符仍可能让某一张图单独失败，不影响其他 Tab 和页面生成。
- **点 Tab 后 502**：看 `ai-service/debug/page_html_raw.txt`；HTML 里的双引号是主要风险，Prompt 已强制单引号并自动重试。
- **端口被占用**：`netstat -ano | findstr :8000`（或 8080 / 5173）找到 PID 后处理。
- **Maven 报 `Non-readable settings ... input contained no data`**：`conf/settings.xml` 被清空了，恢复标准模板即可。

## Roadmap

- [x] 多轮对话引导需求
- [x] 大纲与 HTML 分离生成
- [x] BYOK 模型配置（前端传入，服务端不保存）
- [x] Mermaid 系统架构图
- [x] 功能脑图与核心业务时序图
- [x] Few-shot 查漏补缺式需求访谈
- [ ] 生成任务异步化，前端轮询或 SSE 展示进度
- [ ] 策划书历史记录与导出（Markdown / PDF）
- [ ] 单页 HTML 重新生成与局部修改

## License

MIT
