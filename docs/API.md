# API 与开发文档

Web 端的接口定义、错误约定、环境变量与本地联调说明。MCP 工具的参数与用法见 [mcp-server/README.md](../mcp-server/README.md)。

## 请求约定（BYOK）

所有生成接口都必须携带 `userConfig`：

```json
{
  "userConfig": {
    "apiKey": "你的 Key",
    "baseUrl": "https://open.bigmodel.cn/api/paas/v4",
    "modelName": "glm-4.7-flash"
  }
}
```

- `baseUrl` 可以是任意 OpenAI 兼容地址。
- 服务端不保存密钥，只在单次请求内使用。
- 缺少或配置不完整时返回 `400`，并说明缺了哪个字段。

## POST /api/chat

多轮需求澄清。`messages` 为完整对话历史，最后一条必须是 `user`。

请求：

```json
{
  "messages": [
    { "role": "user", "content": "我想做一个咖啡社区网站" },
    { "role": "assistant", "content": "明白。这个网站主要给谁用？" },
    { "role": "user", "content": "咖啡爱好者" }
  ],
  "userConfig": { "apiKey": "...", "baseUrl": "...", "modelName": "..." }
}
```

响应：

```json
{ "reply": "收到。核心功能除了打分和笔记，还需要社区浏览和按产地筛选吗？" }
```

超过字符预算的历史消息会从最早开始截断，避免上下文无限膨胀。

## POST /api/generate-outline

请求体同上（完整对话）。响应为策划书大纲：

```json
{
  "siteName": "豆香志",
  "tagline": "记录每一杯咖啡的风味",
  "summary": "面向咖啡爱好者的风味记录与分享社区。",
  "targetAudience": "喜欢手冲咖啡、愿意分享品鉴体验的年轻用户",
  "coreFeatures": ["风味评分", "品鉴笔记", "社区推荐"],
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
      "purpose": "介绍产品价值并引导用户开始记录",
      "sections": [{ "name": "首屏 Hero", "description": "标语、介绍与开始按钮" }]
    }
  ]
}
```

约定：

- `pages` 为 3～5 个，第一页是首页（`path` 为 `/`）。
- 三个图表字段是纯 Mermaid 代码（服务端已去掉 ```mermaid 围栏），前端可直接交给 `mermaid.render()`。
- 服务端按图类型校验语法（mindmap / graph TD / sequenceDiagram）、最小行数、缩进与箭头，不合法时自动纠错重试一次。
- 大纲里不会出现 `html` 字段。

## POST /api/generate-page-html

根据单个页面的信息生成静态 HTML。

请求：

```json
{
  "page": {
    "id": "home",
    "name": "首页",
    "path": "/",
    "purpose": "介绍产品价值并引导用户开始记录",
    "sections": [{ "name": "首屏 Hero", "description": "标语、介绍与开始按钮" }]
  },
  "styleGuide": {
    "primaryColor": "#8b5e34",
    "secondaryColor": "#1f2937",
    "fontFamily": "...",
    "tone": "温暖、有质感、偏杂志风格"
  },
  "site": { "siteName": "豆香志", "tagline": "记录每一杯咖啡的风味" },
  "userConfig": { "apiKey": "...", "baseUrl": "...", "modelName": "..." }
}
```

响应：

```json
{ "pageId": "home", "html": "<!DOCTYPE html>..." }
```

生成的 HTML 是完整文档，内联样式、无外部资源、无脚本，可直接放入 iframe 的 `srcdoc`。

## 错误约定

所有错误统一为 `{ "detail": "..." }`：

| 状态码 | 场景 |
| --- | --- |
| 400 | 缺少/不完整 `userConfig`、`baseUrl` 非法、模型名不受支持、请求体格式错误 |
| 401 | 模型服务鉴权失败（Key 无效或无权限） |
| 429 | 模型服务限流 |
| 502 | 上游异常、两次生成都未得到合法 JSON |
| 503 | Spring 连不上 AI 服务（8000 未启动） |
| 504 | 模型请求超时或网络不可达 |

## 环境变量

### ai-service/.env

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `MOCK_LLM` | `1` 时返回示例数据，不调用模型 | `0` |
| `ZHIPU_THINKING` | 智谱思考模式，仅对智谱域名生效 | `disabled` |
| `LLM_TIMEOUT` | 单次模型请求超时（秒） | `180` |
| `CHAT_MAX_TOKENS` | 对话回复上限 | `1024` |
| `OUTLINE_MAX_TOKENS` | 大纲输出上限（含三张 Mermaid 图） | `8192` |
| `HTML_MAX_TOKENS` | 单页 HTML 输出上限 | `16000` |
| `HISTORY_CHAR_BUDGET` | 历史对话字符预算 | `24000` |

### MCP Server

| 变量 | 必填 | 说明 | 默认值 |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | 是 | 模型 API Key | - |
| `OPENAI_BASE_URL` | 否 | OpenAI 兼容地址 | `https://open.bigmodel.cn/api/paas/v4` |
| `MODEL_NAME` | 否 | 模型编码（兼容 `OPENAI_MODEL`） | `glm-4.7-flash` |
| `MODEL_TIMEOUT` | 否 | 单次请求超时（秒） | `180` |
| `MODEL_THINKING` | 否 | 智谱思考模式，仅对智谱域名生效 | `disabled` |
| `CHAT_MAX_TOKENS` | 否 | 对话回复上限 | `1024` |
| `OUTLINE_MAX_TOKENS` | 否 | 大纲输出上限 | `8192` |
| `HTML_MAX_TOKENS` | 否 | 单页 HTML 输出上限 | `16000` |
| `HISTORY_CHAR_BUDGET` | 否 | 历史对话字符预算 | `24000` |

## 离线联调（不调用模型）

1. 在 `ai-service/.env` 中设置 `MOCK_LLM=1` 并重启 AI 服务。
2. 在 Web 端「配置模型」里随便填一组非空值（例如 `demo` / `https://open.bigmodel.cn/api/paas/v4` / `glm-4.7-flash`）。
3. 三个接口会返回 `ai-service/mock_data.py` 中的示例数据，可直接调试前端。

## 本地构建与验证

```powershell
# 后端
cd backend
mvn package

# 前端
cd frontend
npm run build

# AI 层语法检查
cd ai-service
.venv\Scripts\python.exe -m py_compile main.py
```

## 项目结构

```
Website Planning Brief JSON/
├── ai-service/          # AI 层：FastAPI + BYOK + Prompt + 校验
│   ├── main.py          # /chat、/generate-outline、/generate-page-html
│   ├── mock_data.py     # 离线联调数据
│   └── requirements.txt
├── backend/             # 转发层：Spring Boot 3
│   └── src/main/java/com/websitebrief/backend/
│       ├── controller/GenerateController.java
│       ├── service/AiServiceClient.java
│       └── exception/*.java
├── frontend/            # Web 端：Vue 3 + Vite + Mermaid
├── mcp-server/          # 独立 MCP Server（stdio）
├── assets/              # README 演示资源
├── docs/                # 文档
└── README.md
```

## 安全说明

- Web 端 API Key 只存在浏览器 **sessionStorage**（关闭标签页即清除），`baseUrl` 与模型名存 localStorage。
- 每次请求把 `userConfig` 发给 Spring 与 FastAPI；FastAPI 按请求动态创建客户端，**不写日志、不落盘**。
- Spring 关闭了请求详情日志（`spring.mvc.log-request-details: false`），避免请求体中的 Key 出现在异常日志里。
- MCP Server 只从进程环境变量读取 Key，stdio 模式下所有日志走 stderr，不会污染协议通道。
- 这是纯 BYOK 方案，请只在可信环境使用；公网部署时建议增加登录与 HTTPS。
