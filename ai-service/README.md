# ai-service

项目 AI 层：一个 Python FastAPI 服务，接收用户的网站想法，调用智谱 GLM-4.7-Flash 生成结构化《网站策划书》JSON（含每个页面的静态 HTML 概念稿），供前端 iframe 预览。

## 目录结构

```
ai-service/
├── main.py           # FastAPI 应用：/generate、/health
├── mock_data.py      # 离线测试用的固定返回数据
├── requirements.txt  # 依赖
├── .env.example      # 配置模板（复制成 .env 后填写）
├── .env              # 你的本地配置（不要提交到 git）
├── debug/            # 运行后自动生成：最近一次模型原始输出、解析结果
└── .venv/            # 虚拟环境
```

## 快速开始

```bash
cd ai-service

# 1. 创建并激活虚拟环境（已存在则跳过）
python -m venv .venv
.venv\Scripts\activate          # PowerShell / cmd
# source .venv/Scripts/activate # Git Bash

# 2. 安装依赖
python -m pip install -r requirements.txt

# 3. 配置 Key：复制 .env.example 为 .env，填入 ZHIPU_API_KEY

# 4. 启动
python -m uvicorn main:app --reload --port 8000
```

打开 http://127.0.0.1:8000/docs 可直接在 Swagger UI 里测试接口。

不激活虚拟环境时，可以直接用 `.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000`。

## 接口

### POST /generate

请求：

```json
{ "idea": "一个记录咖啡豆风味的社区网站" }
```

响应：策划书 JSON（HTTP 200）。核心字段：

```json
{
  "siteName": "...",
  "tagline": "...",
  "summary": "...",
  "targetAudience": "...",
  "coreFeatures": ["..."],
  "styleGuide": { "primaryColor": "#...", "secondaryColor": "#...", "fontFamily": "...", "tone": "..." },
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

`pages[].html` 是完整、可独立渲染的 HTML 文档（内联样式、无外部资源），前端直接塞进 `iframe` 的 `srcdoc` 即可预览。

### GET /health

返回当前模型、base_url、是否启用 mock、是否已配置 Key。

## 离线模式

`.env` 里设置 `MOCK_LLM=1` 后，`/generate` 不调用智谱，直接返回 `mock_data.py` 中的示例数据，适合前端联调。

## 出错排查

| HTTP 状态 | 含义 | 处理 |
| --- | --- | --- |
| 500 | 未配置 `ZHIPU_API_KEY` | 填 `.env` 后重启 |
| 502 | 上游接口报错 / 返回非 JSON / 结构校验失败 / 输出被截断 | 看返回 detail；原始输出在 `debug/last_raw.txt` |
| 504 | 连不上智谱接口 | 检查网络/代理、`base_url` |

模型返回结构不对时，先看 `debug/last_raw.txt` 里实际返回了什么，再调整 `main.py` 里的 `SYSTEM_PROMPT`。

## 技术说明

- 智谱 OpenAI 兼容接口：`https://open.bigmodel.cn/api/paas/v4`
- 模型：`glm-4.7-flash`
- 用 `response_format={"type": "json_object"}` 强制 JSON 输出
- `glm-4.7-flash` 是混合思考模型，默认开启思考；JSON 模式下会把思考内容混入输出，因此默认传 `thinking: {"type": "disabled"}` 关闭（见 `.env` 的 `ZHIPU_THINKING`）
