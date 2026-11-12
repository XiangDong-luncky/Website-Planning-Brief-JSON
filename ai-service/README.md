# ai-service（V3）

项目 AI 层：FastAPI + OpenAI 兼容接口。支持「多轮需求澄清 → 策划书大纲（含 Mermaid 架构图）→ 单页 HTML」三段式生成。

V3 的两个关键变化：

- **BYOK（Bring Your Own Key）**：生成接口必须由前端传入 `userConfig`，服务端按请求动态创建客户端，**不保存密钥、不提供默认 Key**。
- **Agentic 需求澄清**：`/chat` 按产品经理的需求评审清单（受众、业务流、数据校验、异常、权限）逐轮深挖，每轮只问一个最关键的盲区。

## 接口

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| POST | `/chat` | 多轮需求澄清对话 |
| POST | `/generate-outline` | 策划书大纲 JSON（含 `systemDiagram`，不含 HTML） |
| POST | `/generate-page-html` | 单页现代风格静态 HTML |
| GET | `/health` | 健康检查（不返回任何密钥信息） |

所有生成接口（mock 模式除外）都要求请求体携带：

```json
{
  "userConfig": {
    "apiKey": "你的 Key",
    "baseUrl": "https://open.bigmodel.cn/api/paas/v4",
    "modelName": "glm-4.7-flash"
  }
}
```

`baseUrl` 只要是 OpenAI 兼容地址即可（智谱、DeepSeek、Moonshot、自建网关等）。若缺少配置或配置不完整，接口返回 **400** 并说明缺了哪个字段；不做服务端默认 Key 降级。

### POST /chat

```json
{
  "messages": [
    { "role": "user", "content": "我想做一个咖啡社区网站" },
    { "role": "assistant", "content": "明白。..." },
    { "role": "user", "content": "咖啡爱好者" }
  ],
  "userConfig": { "apiKey": "...", "baseUrl": "...", "modelName": "..." }
}
```

返回：

```json
{ "reply": "明白。记录页如果图片上传失败，你希望：提示重试、静默保存文字、还是禁止提交？" }
```

### POST /generate-outline

请求体同上（完整对话 + userConfig）。返回：

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
  "systemDiagram": "graph TD\n  A[用户浏览器] --> B[前端页面]\n  B --> C[后端接口]",
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

`systemDiagram` 说明：模型被要求输出 ```mermaid 包裹的 `graph TD` 代码，服务端返回前会**去掉围栏**，因此该字段是纯 Mermaid 代码，前端可直接交给 `mermaid.render()`。服务端还会校验图类型，不是合法 Mermaid 会触发自动重试。

### POST /generate-page-html

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
  "site": { "siteName": "豆香志", "tagline": "..." },
  "userConfig": { "apiKey": "...", "baseUrl": "...", "modelName": "..." }
}
```

返回：

```json
{ "pageId": "home", "html": "<!DOCTYPE html>..." }
```

## 错误约定

| 状态码 | 场景 | 前端处理 |
| --- | --- | --- |
| 400 | 缺少/不完整 `userConfig`、`baseUrl` 非法、`modelName` 不被支持、请求格式错误 | 引导用户检查模型设置 |
| 401 | 上游返回 401/403，Key 无效或无模型权限 | 提示重新填写 Key |
| 429 | 上游限流 | 提示稍后重试或更换 Key |
| 502 | 上游其他错误、两次生成都无法得到合法 JSON | 展示 `detail`，可重试 |
| 504 | 连接失败或模型请求超时 | 提示检查 baseUrl/网络 |

## 关键设计

- **动态客户端**：每个请求用 `userConfig` 创建 `OpenAI(api_key, base_url, timeout, max_retries=0)`；不缓存、不落盘、不写日志。
- **智谱专属参数**：`thinking` 只对 `bigmodel.cn` / `z.ai` 域名发送，其他兼容服务不会收到不认识的参数。
- **JSON 自动纠错**：大纲/HTML 解析失败时把错误和上一次输出回传模型重试一次。
- **单引号约束**：HTML 字符串内禁用双引号，避免长 HTML 嵌 JSON 的转义崩坏。
- **调试留存**：`debug/` 下保存最近一次调用（不含任何密钥）。

## 环境变量

V3 起服务端环境变量只用于本地开发与基础设施参数，**没有 API Key 配置项**。见 `.env.example`：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `MOCK_LLM` | `1` 时三个接口返回 `mock_data.py` 示例数据，不需要 userConfig | `0` |
| `ZHIPU_THINKING` | 智谱思考模式，仅对智谱域名生效 | `disabled` |
| `LLM_TIMEOUT` | 单次模型请求超时（秒） | `180` |
| `CHAT_MAX_TOKENS` | 对话回复上限 | `1024` |
| `OUTLINE_MAX_TOKENS` | 大纲输出上限（含 Mermaid） | `6144` |
| `HTML_MAX_TOKENS` | 单页 HTML 输出上限 | `16000` |
| `HISTORY_CHAR_BUDGET` | 历史对话字符预算 | `24000` |

## 启动

```powershell
cd ai-service
.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

验证：http://127.0.0.1:8000/health ，应返回 `version: 3.0.0`、`byok: true`。

前端联调（不消耗额度）：设置 `MOCK_LLM=1`，此时请求体可以不传 `userConfig`。

## 调试文件

| 文件 | 内容 |
| --- | --- |
| `debug/last_chat.txt` | 最近一次对话回复 |
| `debug/outline_raw.txt` / `outline_result.json` | 大纲原始输出 / 解析结果 |
| `debug/page_html_raw.txt` / `page_html_result.json` | HTML 原始输出 / 解析结果 |
| `debug/last_page.html` | 最近一次生成的页面，可直接双击预览 |
