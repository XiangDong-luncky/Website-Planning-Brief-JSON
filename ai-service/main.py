"""Website Planning Brief AI - V3 AI 层。

V3 升级：
1. BYOK（Bring Your Own Key）：生成接口必须由前端传入 userConfig（apiKey/baseUrl/modelName），
   服务端按请求动态实例化 OpenAI 兼容客户端，不保存密钥、不提供默认 Key。
2. Agentic 深度需求澄清：/chat 的 System Prompt 按产品经理的需求评审清单深挖需求。
3. 可视化架构图：/generate-outline 额外输出 systemDiagram（Mermaid graph TD 代码）。

POST /chat                 多轮需求澄清对话
POST /generate-outline     生成策划书大纲（含 Mermaid 架构图，不含 HTML）
POST /generate-page-html   根据单个页面大纲生成现代风格的静态 HTML
GET  /health               健康检查

本地开发时设置 MOCK_LLM=1，三个接口会返回 mock_data.py 中的固定数据，
此时不要求 userConfig，也不调用任何模型服务。
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Callable, Literal, TypeVar

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

APP_DIR = Path(__file__).resolve().parent

# 显式加载脚本同目录的 .env，避免从别的目录启动时读不到配置。
# V3 起 .env 只用于本地开发的 MOCK 兜底，不再提供任何 API Key。
load_dotenv(APP_DIR / ".env")

THINKING_MODE = os.getenv("ZHIPU_THINKING", "disabled").strip().lower()
MOCK = os.getenv("MOCK_LLM", "0").strip() == "1"
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "180"))

CHAT_MAX_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", "1024"))
OUTLINE_MAX_TOKENS = int(os.getenv("OUTLINE_MAX_TOKENS", "6144"))
HTML_MAX_TOKENS = int(os.getenv("HTML_MAX_TOKENS", "16000"))

# 历史对话字符预算：超出时丢弃最早的消息，避免上下文无限膨胀
HISTORY_CHAR_BUDGET = int(os.getenv("HISTORY_CHAR_BUDGET", "24000"))

DEBUG_DIR = APP_DIR / "debug"

logger = logging.getLogger("brief")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

T = TypeVar("T")

# Mermaid 允许的图类型（小写比较）
MERMAID_TYPES = (
    "graph",
    "flowchart",
    "sequencediagram",
    "classdiagram",
    "statediagram",
    "erdiagram",
    "journey",
    "gantt",
    "pie",
    "mindmap",
    "timeline",
    "quadrantchart",
)


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------

class UserConfig(BaseModel):
    """BYOK 模型配置。字段保持宽松，由 require_user_config 做统一校验并返回 400。"""

    model_config = ConfigDict(extra="ignore")

    apiKey: str = ""
    baseUrl: str = ""
    modelName: str = ""


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content 不能为空")
        return value


class MessagesRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=80)
    userConfig: UserConfig | None = None


class ChatResponse(BaseModel):
    reply: str


class Section(BaseModel):
    name: str
    description: str = ""


class PageOutline(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str
    path: str = "/"
    purpose: str = ""
    sections: list[Section] = Field(default_factory=list)

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
    fontFamily: str = "system-ui, -apple-system, 'Microsoft YaHei', sans-serif"
    tone: str = "现代、简洁、有设计感"


class SiteInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    siteName: str = ""
    tagline: str = ""


class PlanningOutline(BaseModel):
    model_config = ConfigDict(extra="ignore")

    siteName: str
    tagline: str = ""
    summary: str = ""
    targetAudience: str = ""
    coreFeatures: list[str] = Field(default_factory=list)
    styleGuide: StyleGuide = Field(default_factory=StyleGuide)
    # Mermaid 代码：服务端已去掉 ```mermaid 围栏，前端拿到即可直接交给 mermaid.render()
    systemDiagram: str = Field(..., min_length=10)
    pages: list[PageOutline] = Field(..., min_length=1)

    @field_validator("systemDiagram")
    @classmethod
    def _normalize_diagram(cls, value: str) -> str:
        return normalize_mermaid(value)

    @field_validator("pages")
    @classmethod
    def _normalize_page_ids(cls, pages: list[PageOutline]) -> list[PageOutline]:
        seen: set[str] = set()
        for index, page in enumerate(pages, start=1):
            page_id = (page.id or "").strip()
            if not page_id:
                page_id = f"page-{index}"
            if page_id in seen:
                page_id = f"{page_id}-{index}"
            page.id = page_id
            seen.add(page_id)
        return pages


class PageHtmlRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    page: PageOutline
    styleGuide: StyleGuide = Field(default_factory=StyleGuide)
    site: SiteInfo = Field(default_factory=SiteInfo)
    userConfig: UserConfig | None = None


class PageHtmlResponse(BaseModel):
    pageId: str
    html: str


# ---------------------------------------------------------------------------
# System Prompts
# ---------------------------------------------------------------------------

CHAT_SYSTEM_PROMPT = """你是「Website Planning Brief AI」的资深产品经理，拥有 10 年 To B / To C 产品需求分析经验。用户会给你一个网站想法，你要通过多轮对话，把它打磨成可以直接进入设计开发的《网站策划书》。

你的工作方式：
1. 像做需求评审一样，系统性检查以下维度，找出用户当前描述中最大的逻辑盲区：
   - 目标受众与核心场景：谁在用、在什么场景下用、解决什么痛点；
   - 核心业务流转：用户从进入网站到完成目标的完整链路，每一步的输入与产出；
   - 数据校验规则：必填项、格式、唯一性、长度与数量上限、重复提交；
   - 异常情况处理：支付失败、接口超时、网络中断、空数据、并发冲突、审核不通过；
   - 权限设计：有哪些角色，各角色能看什么、能改什么、不能做什么；
   - 非功能约束：数据隐私、合规、性能、多端适配。
2. 每轮只指出一个当前最关键的盲区：先用一句话说明"为什么这一点重要"，再提出一个问题。
3. 提问必须给出 2~3 个具体选项或示例，降低用户的回答成本。例如："库存扣减在什么时机做：下单时立即扣减、支付成功后扣减，还是先预占库存？"
4. 用户回答后，先复述确认你的理解，再进入下一个盲区；不要重复追问已经明确的信息。
5. 如果用户的回答仍然含糊，就针对同一个点追问具体规则，可以给出边界值帮助用户判断。
6. 当上述维度都有明确答案、足以支撑开发时，回复："需求已经足够清晰，点击「生成策划书」即可。"
7. 不要输出 JSON、HTML 或 Mermaid；每次回复不超过 200 字；全程使用简体中文，语气专业但不居高临下。"""

OUTLINE_SYSTEM_PROMPT = """你是资深网站策划师兼系统架构师。请把用户与你的完整对话，整理成一份结构化的《网站策划书》大纲 JSON。

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
    "fontFamily": "字体栈，如 system-ui, -apple-system, 'Microsoft YaHei', sans-serif",
    "tone": "视觉与文案基调"
  },
  "systemDiagram": "```mermaid\ngraph TD\n  A[用户浏览器] --> B[前端页面]\n  B --> C[后端接口]\n  C --> D[业务服务]\n  D --> E[(数据存储)]\n```",
  "pages": [
    {
      "id": "英文小写短标识，如 home",
      "name": "页面中文名",
      "path": "路由，如 /",
      "purpose": "该页面的目标，50 字以内",
      "sections": [
        {"name": "区块名，如 首屏 Hero", "description": "该区块展示什么内容"}
      ]
    }
  ]
}

3. pages 数量为 3 到 5 个，必须覆盖对话中确认的核心使用流程，第一页必须是首页（path 为 "/"）。
4. 每个页面包含 3 到 6 个 sections，name 简短明确，description 说明该区块的具体内容，不要写空话。
5. 绝对不要在 pages 或任何层级中出现 html 字段——HTML 会在用户点击具体页面时单独生成。
6. styleGuide 必须体现对话中确认的风格偏好；对话没有明确时，选择与网站主题匹配的现代风格。
7. 对话中缺失的信息，基于上下文做出合理推断，不要留空，也不要在 JSON 里写"待确认"。
8. 所有面向用户的文本使用简体中文（id、path、字段名除外）。
9. systemDiagram 字段要求：
   - 内容是合法的 Mermaid 代码，必须用 ```mermaid 开头、``` 结尾包裹；
   - 必须使用 graph TD（自上而下），描述「用户/浏览器 → 前端页面 → 后端接口 → 业务服务 → 数据存储/第三方服务」的真实流向；
   - 结合对话内容补充核心业务节点，必要时加入关键异常分支（如 支付失败重试、审核不通过回流）；
   - 节点数量 8~15 个；节点 id 使用简短英文（如 A、B、login、pay），中文文案写在方括号内，例如 A[用户浏览器]；
   - 节点文案中禁止使用括号、引号、花括号、竖线、分号等特殊字符，避免 Mermaid 语法错误；
   - systemDiagram 字符串内禁止出现任何双引号字符，否则会破坏 JSON；
   - 除 systemDiagram 外，其他字段中不要输出 Mermaid。"""

HTML_SYSTEM_PROMPT = """你是资深 UI 设计师兼前端工程师，擅长制作现代、精致、可直接展示的静态网站概念稿。请为给定的单个页面生成完整的静态 HTML。

输出必须严格遵守以下规则：
1. 只输出一个 JSON 对象：{"html": "<完整的 HTML 文档字符串>"}。不要输出其他字段、解释或 Markdown 代码块。
2. html 必须是完整文档：以 <!DOCTYPE html> 开头，包含 <html lang='zh-CN'>、<head>（含 <meta charset='utf-8'> 和 viewport）、<style>、<body>。
3. 所有 HTML 属性一律使用单引号；html 字符串内禁止出现任何双引号字符；CSS 中的字体名、content 值也使用单引号或直接省略引号。这是硬性要求，违反会导致 JSON 解析失败。
4. 不使用任何外部资源：不要 CDN、外链字体、外链图片、外部图标库，也不要写 <script>。图片用 CSS 渐变、内联 SVG、emoji 或色块代替。
5. 设计质量要求：
   - 用 styleGuide 的主色和辅助色定义 CSS 变量（:root），整页配色统一；
   - 现代排版：留白充足，字号层级清晰（辅助 13~14px、正文 16px、小标题 20~24px、大标题 40~56px），行高约 1.6；
   - 使用 Flex / Grid 布局、12~20px 圆角、柔和的 box-shadow、渐变背景；
   - 至少设计一个视觉亮点：渐变 Hero、Bento 卡片网格、玻璃拟态卡片、超大号数字或大字排版等；
   - 交互细节：按钮和卡片有 hover 状态与 transition；
   - 响应式：桌面多栏布局，宽度小于 768px 时切换为单栏（使用 @media）。
6. 内容要求：使用简体中文撰写真实、具体、贴合该网站的文案，禁止 Lorem ipsum、"这里是标题"等占位文字。
7. 结构要求：包含顶部导航和页脚；主容器 max-width: 1200px; margin: 0 auto; body 设置 margin: 0；用户给出的每个 section 都要按顺序实现为独立的 <section>，并配上合适的标题和内容。
8. 代码保持 150~250 行，确保 JSON 字符串正确闭合。"""

OUTLINE_CORRECTION = (
    "你上一次的输出无法解析为合格的策划书大纲 JSON：__ERROR__。"
    "请严格按系统提示中的字段名和嵌套结构重新输出完整 JSON，"
    "必须包含非空的 systemDiagram 字段（```mermaid 包裹的 graph TD 代码），"
    "不要包含任何 html 字段，确保引号、逗号、括号都正确闭合。"
)

HTML_CORRECTION = (
    "你上一次的输出不是合法的 {\"html\": \"...\"} JSON，或 HTML 不完整：__ERROR__。"
    "请重新输出，只包含一个 html 字段；html 字符串内禁止出现双引号字符，"
    "所有 HTML 属性一律使用单引号，并确保字符串正确闭合。"
)


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

def require_user_config(config: UserConfig | None) -> UserConfig:
    """BYOK 校验：没有配置或配置不完整时直接 400，不使用服务端默认 Key。"""
    if config is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "缺少模型配置 userConfig。V3 采用 BYOK（Bring Your Own Key）："
                "请在前端设置中填写你自己的 apiKey、baseUrl、modelName，服务端不保存密钥。"
            ),
        )

    api_key = config.apiKey.strip()
    base_url = config.baseUrl.strip().rstrip("/")
    model_name = config.modelName.strip()

    missing = [
        name
        for name, value in (
            ("apiKey", api_key),
            ("baseUrl", base_url),
            ("modelName", model_name),
        )
        if not value
    ]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"模型配置不完整，缺少：{', '.join(missing)}。请在前端设置中补全后重试。",
        )

    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400,
            detail="baseUrl 必须以 http:// 或 https:// 开头，例如 https://open.bigmodel.cn/api/paas/v4",
        )

    return UserConfig(apiKey=api_key, baseUrl=base_url, modelName=model_name)


def is_zhipu(base_url: str) -> bool:
    return "bigmodel.cn" in base_url or "z.ai" in base_url


def build_client(config: UserConfig) -> OpenAI:
    """按请求里的 userConfig 动态创建 OpenAI 兼容客户端。

    max_retries=0：重试由我们自己控制，避免 SDK 在超时后静默重复调用消耗额度。
    """
    try:
        return OpenAI(
            api_key=config.apiKey,
            base_url=config.baseUrl,
            timeout=LLM_TIMEOUT,
            max_retries=0,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"模型配置无法初始化：{exc}",
        ) from exc


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


def strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def normalize_mermaid(value: str) -> str:
    """去掉 ```mermaid 围栏，校验图类型；不合法时抛 ValueError 触发大纲自动重试。"""
    text = strip_code_fence(value.strip())
    text = re.sub(r"^mermaid\s*", "", text, flags=re.IGNORECASE).strip()

    lowered = text.lower()
    if not any(lowered.startswith(prefix) for prefix in MERMAID_TYPES):
        raise ValueError("systemDiagram 不是合法的 Mermaid 代码，必须以 graph TD 等图类型开头")
    if len(text) < 10:
        raise ValueError("systemDiagram 内容过短，无法构成有效的架构图")
    return text


def save_debug(name: str, content: str) -> Path:
    DEBUG_DIR.mkdir(exist_ok=True)
    path = DEBUG_DIR / name
    path.write_text(content, encoding="utf-8")
    return path


def trim_history(messages: list[dict], max_chars: int = HISTORY_CHAR_BUDGET) -> list[dict]:
    """从最新消息向前保留，超出字符预算时丢弃最早的消息。"""
    total = 0
    kept: list[dict] = []
    for message in reversed(messages):
        size = len(message["content"])
        if kept and total + size > max_chars:
            break
        kept.append(message)
        total += size
    kept.reverse()
    return kept


def call_model(
    client: OpenAI,
    config: UserConfig,
    messages: list[dict],
    *,
    temperature: float,
    max_tokens: int,
    json_mode: bool = False,
) -> tuple[str, str | None]:
    extra = {}
    # thinking 参数是智谱扩展，其他 OpenAI 兼容服务不一定认识，只对智谱域名发送
    if is_zhipu(config.baseUrl) and THINKING_MODE in ("enabled", "disabled"):
        extra["extra_body"] = {"thinking": {"type": THINKING_MODE}}

    kwargs = {
        "model": config.modelName,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        **extra,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(**kwargs)
    except APITimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"模型请求超时（{LLM_TIMEOUT:.0f} 秒）。请检查 baseUrl（{config.baseUrl}）或稍后重试。",
        ) from exc
    except APIStatusError as exc:
        # 401/403 key 错误，429 限流，400 模型名/参数不支持，其余视为上游故障
        provider_message = exc.response.text[:600] if exc.response is not None else ""
        if exc.status_code in (401, 403):
            raise HTTPException(
                status_code=401,
                detail=(
                    f"模型服务鉴权失败（HTTP {exc.status_code}）。"
                    "请检查 userConfig.apiKey 是否正确、是否已开通该模型权限。"
                ),
            ) from exc
        if exc.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail=f"模型服务触发限流（HTTP 429）。请稍后重试或更换 Key：{provider_message}",
            ) from exc
        if exc.status_code == 400:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"模型服务拒绝了请求（HTTP 400），请检查 modelName={config.modelName} "
                    f"是否受支持：{provider_message}"
                ),
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"模型服务返回 HTTP {exc.status_code}：{provider_message}",
        ) from exc
    except APIConnectionError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"连接不上模型服务（{config.baseUrl}）。请检查 baseUrl 和网络/代理设置。",
        ) from exc

    usage = response.usage
    if usage is not None:
        logger.info(
            "llm done: model=%s prompt_tokens=%s completion_tokens=%s",
            config.modelName,
            usage.prompt_tokens,
            usage.completion_tokens,
        )

    choice = response.choices[0]
    return choice.message.content or "", choice.finish_reason


def complete_json(
    client: OpenAI,
    config: UserConfig,
    messages: list[dict],
    *,
    max_tokens: int,
    debug_prefix: str,
    parse: Callable[[dict], T],
    correction_hint: str,
) -> tuple[T, str]:
    """调用模型并解析 JSON；失败时把错误和上一次输出回传，自动重试一次。"""
    last_error = "未知错误"
    raw_path = DEBUG_DIR / f"{debug_prefix}_raw.txt"

    for attempt in (1, 2):
        content, finish_reason = call_model(
            client,
            config,
            messages,
            temperature=0.4,
            max_tokens=max_tokens,
            json_mode=True,
        )

        if attempt == 1:
            save_debug(f"{debug_prefix}_raw_attempt1.txt", content)
        raw_path = save_debug(f"{debug_prefix}_raw.txt", content)

        if not content.strip():
            last_error = "模型返回内容为空"
            if attempt == 1:
                continue
            break

        if finish_reason == "length":
            last_error = "输出达到 max_tokens 上限被截断"
            if attempt == 1:
                messages = messages + [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": "上一次输出因长度被截断，请精简内容后重新输出完整 JSON。"},
                ]
                continue
            break

        try:
            data = extract_json(content)
            result = parse(data)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt == 1:
                messages = messages + [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": correction_hint.replace("__ERROR__", str(exc))},
                ]
                continue
            break

        save_debug(
            f"{debug_prefix}_result.json",
            json.dumps(data, ensure_ascii=False, indent=2),
        )
        return result, content

    raise HTTPException(
        status_code=502,
        detail=f"两次生成都未得到合法结果：{last_error}。原始输出已保存到 {raw_path}",
    )


def build_page_prompt(req: PageHtmlRequest) -> str:
    page = req.page
    style = req.styleGuide
    site = req.site

    if page.sections:
        section_lines = "\n".join(
            f"{index}. {section.name}：{section.description or '根据页面目标自行设计具体内容'}"
            for index, section in enumerate(page.sections, start=1)
        )
    else:
        section_lines = "（未提供，请根据页面目标自行规划 3~5 个区块）"

    return (
        f"网站名称：{site.siteName or '未提供'}\n"
        f"网站标语：{site.tagline or '未提供'}\n"
        f"视觉规范：主色 {style.primaryColor}；辅助色 {style.secondaryColor}；"
        f"字体 {style.fontFamily}；整体基调 {style.tone}\n\n"
        f"当前页面：{page.name}（路径 {page.path}）\n"
        f"页面目标：{page.purpose or '清晰传达页面主题并引导用户行动'}\n"
        f"页面区块（必须按顺序全部实现，每个区块一个 <section>）：\n{section_lines}\n\n"
        "请只输出 {\"html\": \"...\"} 形式的 JSON。"
    )


def parse_page_html(data: dict) -> str:
    """从 JSON 中取出 html 字段，兼容模型偶尔使用的其他键名。返回校验通过的 HTML。"""
    if not isinstance(data, dict):
        raise ValueError("模型返回的顶层不是 JSON 对象")

    html = ""
    for key in ("html", "pageHtml", "page_html", "content", "code"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            html = value
            break

    if not html:
        for value in data.values():
            if isinstance(value, str) and "<html" in value.lower():
                html = value
                break

    html = strip_code_fence(html)
    if "<html" not in html.lower():
        raise ValueError("返回内容中找不到完整的 html 字段")
    if len(html) < 300:
        raise ValueError("html 内容过短，可能生成不完整")
    return html


# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------

app = FastAPI(title="Website Planning Brief AI", version="3.0.0")

# 开发阶段允许所有来源，方便 Vue 前端跨域调用；上线前应改成具体域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "service": "website-planning-brief-ai",
        "version": "3.0.0",
        "mode": "BYOK",
        "docs": "/docs",
        "endpoints": ["POST /chat", "POST /generate-outline", "POST /generate-page-html"],
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "3.0.0",
        "byok": True,
        "mock": MOCK,
        "thinking": THINKING_MODE,
        "hint": "生成接口必须由前端传入 userConfig（apiKey/baseUrl/modelName），服务端不保存密钥。",
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: MessagesRequest):
    history = trim_history([message.model_dump() for message in req.messages])

    if history[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="最后一条消息必须来自用户")

    if MOCK:
        from mock_data import MOCK_CHAT_REPLY

        return ChatResponse(reply=MOCK_CHAT_REPLY)

    config = require_user_config(req.userConfig)
    client = build_client(config)

    messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}] + history
    content, _ = call_model(
        client,
        config,
        messages,
        temperature=0.7,
        max_tokens=CHAT_MAX_TOKENS,
    )
    reply = content.strip()

    if not reply:
        raise HTTPException(status_code=502, detail="模型返回内容为空，请重试。")

    save_debug("last_chat.txt", reply)
    logger.info("chat reply: chars=%d", len(reply))
    return ChatResponse(reply=reply)


@app.post("/generate-outline", response_model=PlanningOutline)
def generate_outline(req: MessagesRequest):
    history = trim_history([message.model_dump() for message in req.messages])

    if history[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="最后一条消息必须来自用户")

    if MOCK:
        from mock_data import SAMPLE_OUTLINE

        return PlanningOutline.model_validate(SAMPLE_OUTLINE)

    config = require_user_config(req.userConfig)
    client = build_client(config)

    messages = (
        [{"role": "system", "content": OUTLINE_SYSTEM_PROMPT}]
        + history
        + [
            {
                "role": "user",
                "content": "请根据以上全部对话，输出策划书大纲 JSON。记住：不要包含任何 HTML，必须包含 Mermaid 格式的 systemDiagram。",
            }
        ]
    )

    outline, _ = complete_json(
        client,
        config,
        messages,
        max_tokens=OUTLINE_MAX_TOKENS,
        debug_prefix="outline",
        parse=PlanningOutline.model_validate,
        correction_hint=OUTLINE_CORRECTION,
    )

    logger.info("outline: pages=%d diagram_chars=%d", len(outline.pages), len(outline.systemDiagram))
    return outline


@app.post("/generate-page-html", response_model=PageHtmlResponse)
def generate_page_html(req: PageHtmlRequest):
    if MOCK:
        from mock_data import SAMPLE_PAGE_HTML

        return PageHtmlResponse(pageId=req.page.id or req.page.name, html=SAMPLE_PAGE_HTML)

    config = require_user_config(req.userConfig)
    client = build_client(config)

    messages = [
        {"role": "system", "content": HTML_SYSTEM_PROMPT},
        {"role": "user", "content": build_page_prompt(req)},
    ]

    html, _ = complete_json(
        client,
        config,
        messages,
        max_tokens=HTML_MAX_TOKENS,
        debug_prefix="page_html",
        parse=parse_page_html,
        correction_hint=HTML_CORRECTION,
    )

    save_debug("last_page.html", html)
    logger.info("page html: page=%s chars=%d", req.page.name, len(html))
    return PageHtmlResponse(pageId=req.page.id or req.page.name, html=html)
