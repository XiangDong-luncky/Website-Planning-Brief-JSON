"""网站策划书生成服务（AI 层）。

POST /generate  接收 {"idea": "网站想法"}，调用智谱 GLM 生成结构化策划书 JSON 并返回。
GET  /health    健康检查，确认服务和配置是否就绪。
"""

import json
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import APIConnectionError, APIStatusError, OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

APP_DIR = Path(__file__).resolve().parent

# 显式加载脚本同目录的 .env，避免从别的目录启动时读不到配置
load_dotenv(APP_DIR / ".env")

API_KEY = os.getenv("ZHIPU_API_KEY", "").strip()
BASE_URL = os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").strip()
MODEL = os.getenv("ZHIPU_MODEL", "glm-4.7-flash").strip()
THINKING_MODE = os.getenv("ZHIPU_THINKING", "disabled").strip().lower()
MOCK = os.getenv("MOCK_LLM", "0").strip() == "1"
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "180"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "12000"))

DEBUG_DIR = Path(__file__).resolve().parent / "debug"

logger = logging.getLogger("brief")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

client = OpenAI(
    api_key=API_KEY or "not-configured",
    base_url=BASE_URL,
    timeout=LLM_TIMEOUT,
)


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    idea: str = Field(..., min_length=2, max_length=2000, description="用户的网站想法")


class Section(BaseModel):
    name: str
    description: str = ""


class Page(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    path: str = "/"
    purpose: str = ""
    sections: list[Section] = Field(default_factory=list)
    html: str

    @field_validator("sections", mode="before")
    @classmethod
    def _accept_plain_strings(cls, value):
        # 模型有时把 sections 写成 ["首屏 Hero", "功能介绍"]，这里兜底转换
        if isinstance(value, list):
            return [{"name": item} if isinstance(item, str) else item for item in value]
        return value


class StyleGuide(BaseModel):
    model_config = ConfigDict(extra="ignore")

    primaryColor: str = "#2563eb"
    secondaryColor: str = "#0f172a"
    fontFamily: str = "system-ui, sans-serif"
    tone: str = ""


class PlanningBrief(BaseModel):
    model_config = ConfigDict(extra="ignore")

    siteName: str
    tagline: str = ""
    summary: str = ""
    targetAudience: str = ""
    coreFeatures: list[str] = Field(default_factory=list)
    styleGuide: StyleGuide = Field(default_factory=StyleGuide)
    pages: list[Page]

    @field_validator("pages")
    @classmethod
    def _pages_not_empty(cls, value):
        if not value:
            raise ValueError("pages 不能为空，至少需要 1 个页面")
        return value


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是一名资深网站策划师，同时精通静态网页原型设计。用户会给你一个网站想法，你要产出一份结构化的《网站策划书》JSON。

输出必须严格遵守以下规则：
1. 只输出一个 JSON 对象。不要用 Markdown 代码块包裹，不要输出任何解释、前言或后记。
2. 字段名、字段类型、嵌套层级必须与下面的结构完全一致，不要改名、不要增删顶层字段：

{
  "siteName": "网站名称",
  "tagline": "一句话标语",
  "summary": "项目概述，100 字以内",
  "targetAudience": "目标用户描述",
  "coreFeatures": ["核心功能1", "核心功能2", "核心功能3"],
  "styleGuide": {
    "primaryColor": "#十六进制主色",
    "secondaryColor": "#十六进制辅助色",
    "fontFamily": "字体栈",
    "tone": "视觉与文案基调"
  },
  "pages": [
    {
      "id": "英文小写短标识，如 home",
      "name": "页面中文名",
      "path": "路由，如 /",
      "purpose": "该页面的目标，50 字以内",
      "sections": [
        {"name": "区块名，如 首屏 Hero", "description": "该区块展示什么内容"}
      ],
      "html": "完整的静态 HTML 概念稿字符串"
    }
  ]
}

3. pages 数量为 3 到 4 个，必须覆盖用户想法的核心使用流程，第一页必须是首页（path 为 "/"）。
4. 每个 page.html 的要求：
   - 是一个完整且可独立运行的 HTML 文档，以 <!DOCTYPE html> 开头，包含 <html>、<head>、<body>。
   - 所有样式写在 <style> 标签内，不使用任何外部资源：不要 CDN、外链字体、外链图片、不要 <script>。
   - 用内联 SVG、CSS 渐变、色块和 emoji 充当图片占位；宽度自适应（body 设置 margin: 0，主容器 max-width: 1200px; margin: 0 auto）。
   - 使用中文撰写真实、具体、贴合该网站的文案，禁止出现 Lorem ipsum、"这里是标题" 这类占位文字。
   - 视觉风格与 styleGuide 保持一致。
   - 代码保持精简，单个页面控制在 150 行以内。
   - html 字符串内禁止出现任何双引号字符（"）：所有标签属性一律使用单引号（例如 <div class='hero'>、<a href='/'>），CSS 中的字体名也用单引号。这是硬性要求，违反会导致 JSON 无法解析。
5. sections 列表要与 html 中实际呈现的区块一一对应。
"""


def build_user_prompt(idea: str) -> str:
    return f"网站想法：{idea}\n\n请生成 3 到 4 个页面的策划书 JSON。"


# ---------------------------------------------------------------------------
# 调用与解析
# ---------------------------------------------------------------------------

def call_llm(messages: list[dict]) -> tuple[str, str | None]:
    extra = {}
    if THINKING_MODE in ("enabled", "disabled"):
        extra["extra_body"] = {"thinking": {"type": THINKING_MODE}}

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.4,
        max_tokens=MAX_TOKENS,
        response_format={"type": "json_object"},
        **extra,
    )

    usage = response.usage
    if usage is not None:
        logger.info(
            "llm done: prompt_tokens=%s completion_tokens=%s",
            usage.prompt_tokens,
            usage.completion_tokens,
        )
    choice = response.choices[0]
    return choice.message.content or "", choice.finish_reason


def extract_json(text: str) -> dict:
    """解析模型输出。正常应直接是 JSON；这里兜底处理代码块包裹和前后杂字。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def save_debug(name: str, content: str) -> Path:
    DEBUG_DIR.mkdir(exist_ok=True)
    path = DEBUG_DIR / name
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------

app = FastAPI(title="Website Planning Brief AI", version="0.1.0")

# 开发阶段允许所有来源，方便 Vue 前端跨域调用；上线前应改成具体域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"service": "website-planning-brief-ai", "docs": "/docs", "generate": "POST /generate"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": MODEL,
        "base_url": BASE_URL,
        "thinking": THINKING_MODE,
        "mock": MOCK,
        "api_key_configured": bool(API_KEY),
    }


@app.post("/generate", response_model=PlanningBrief)
def generate(req: GenerateRequest):
    if MOCK:
        from mock_data import SAMPLE_BRIEF

        return PlanningBrief.model_validate(SAMPLE_BRIEF)

    if not API_KEY:
        raise HTTPException(
            status_code=500,
            detail="未配置 ZHIPU_API_KEY。请在 ai-service/.env 中填写智谱 API Key，然后重启服务。",
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(req.idea)},
    ]

    last_error = "未知错误"
    raw_path = None

    # 最多尝试两次：第一次失败时，把错误原因和上一次输出回传给模型让它自行修正
    for attempt in (1, 2):
        try:
            content, finish_reason = call_llm(messages)
        except APIStatusError as exc:
            # 401 key 错误 / 429 限流 / 400 参数不支持 都会走这里
            raise HTTPException(
                status_code=502,
                detail=f"智谱接口返回 HTTP {exc.status_code}：{exc.response.text[:600]}",
            ) from exc
        except APIConnectionError as exc:
            raise HTTPException(
                status_code=504,
                detail=f"连接不上智谱接口（{BASE_URL}）。请检查网络或代理设置。",
            ) from exc

        if attempt == 1:
            save_debug("last_raw_attempt1.txt", content)
        raw_path = save_debug("last_raw.txt", content)

        if not content.strip():
            last_error = "模型返回内容为空"
            if attempt == 1:
                continue
            break

        if finish_reason == "length":
            last_error = "输出达到 max_tokens 上限被截断，JSON 不完整"
            if attempt == 1:
                messages += [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": "上一次输出因长度被截断。请重新输出完整 JSON，并把每个页面的 html 精简到 80 行以内。",
                    },
                ]
                continue
            break

        try:
            data = extract_json(content)
            brief = PlanningBrief.model_validate(data)
        except json.JSONDecodeError as exc:
            last_error = f"不是合法 JSON：{exc}"
            correction = (
                "你上一次的输出无法解析为合法 JSON（{err}）。请重新输出完整的 JSON 对象："
                "只输出 JSON 本身；html 字符串内禁止出现双引号字符，所有 HTML 属性一律使用单引号；"
                "确保每个字符串的引号、逗号和括号都正确闭合。"
            ).format(err=exc)
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first["loc"])
            last_error = f"结构不符合约定：{loc} -> {first['msg']}（共 {exc.error_count()} 处）"
            correction = (
                f"你上一次的输出结构不符合约定。首个错误：{loc} -> {first['msg']}。"
                "请严格按系统提示中的字段名和嵌套结构重新输出完整 JSON，"
                "html 字符串内禁止出现双引号字符。"
            )
        else:
            save_debug("last_result.json", json.dumps(data, ensure_ascii=False, indent=2))
            logger.info(
                "generated: pages=%d chars=%d attempt=%d",
                len(brief.pages),
                len(content),
                attempt,
            )
            return brief

        if attempt == 1:
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user", "content": correction},
            ]

    raise HTTPException(
        status_code=502,
        detail=f"两次生成都未能得到合法的策划书 JSON。最后一次错误：{last_error}。原始输出已保存到 {raw_path}",
    )
