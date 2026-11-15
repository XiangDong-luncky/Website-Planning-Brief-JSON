"""Website Planning Brief AI - MCP Server（独立自包含版本）。

不依赖 FastAPI、Spring Boot 或任何本地 Web 服务，直接通过 openai SDK 调用
任意 OpenAI 兼容模型（智谱 GLM、DeepSeek、Moonshot、自建网关等）。

提供的 MCP Tools：
- chat_requirement    多轮需求澄清，返回产品经理风格的下一条追问
- generate_outline    生成策划书大纲 JSON（含三张 Mermaid 图表）
- generate_page_html  为单个页面生成现代风格的静态 HTML

模型配置全部来自 MCP 客户端 env：
- OPENAI_API_KEY   必填
- OPENAI_BASE_URL  可选，默认 https://open.bigmodel.cn/api/paas/v4
- MODEL_NAME       可选，默认 glm-4.7-flash（兼容 OPENAI_MODEL）

注意：stdio 模式下严禁向 stdout 打印任何内容，否则会破坏 MCP 协议。
本文件的所有日志都走 stderr。
"""

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Literal

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from pydantic import BaseModel, ConfigDict, Field

try:
    from dotenv import load_dotenv

    # 仅用于本地调试；MCP 客户端注入的 env 优先级更高（load_dotenv 默认不覆盖）
    load_dotenv(Path(__file__).with_name(".env"))
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("brief-mcp")

DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_MODEL = "glm-4.7-flash"


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _int_env(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


CHAT_MAX_TOKENS = _int_env("CHAT_MAX_TOKENS", 1024)
OUTLINE_MAX_TOKENS = _int_env("OUTLINE_MAX_TOKENS", 8192)
HTML_MAX_TOKENS = _int_env("HTML_MAX_TOKENS", 16000)
HISTORY_CHAR_BUDGET = _int_env("HISTORY_CHAR_BUDGET", 24000)
THINKING_MODE = (_env("MODEL_THINKING") or _env("ZHIPU_THINKING") or "disabled").lower()


def get_openai_client() -> OpenAI:
    """从环境变量读取配置，返回 OpenAI 兼容客户端实例。"""
    api_key = _env("OPENAI_API_KEY")
    if not api_key:
        raise ToolError(
            "未配置 OPENAI_API_KEY。请在 MCP 客户端配置的 env 字段中填写你自己的 API Key。"
        )

    base_url = _env("OPENAI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise ToolError("OPENAI_BASE_URL 必须以 http:// 或 https:// 开头")

    timeout = float(_env("MODEL_TIMEOUT", "180"))
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)


def get_model_name() -> str:
    return _env("MODEL_NAME") or _env("OPENAI_MODEL") or DEFAULT_MODEL


def _base_url() -> str:
    return _env("OPENAI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _is_zhipu() -> bool:
    base_url = _base_url()
    return "bigmodel.cn" in base_url or "z.ai" in base_url


# ---------------------------------------------------------------------------
# 输入模型（MCP 客户端据此生成工具 schema）
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)


class SectionInput(BaseModel):
    name: str
    description: str = ""


class PageInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str
    path: str = "/"
    purpose: str = ""
    sections: list[SectionInput] = Field(default_factory=list)


class StyleGuideInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    primaryColor: str = "#2563eb"
    secondaryColor: str = "#0f172a"
    fontFamily: str = "system-ui, -apple-system, 'Microsoft YaHei', sans-serif"
    tone: str = "现代、简洁、有设计感"


class SiteInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    siteName: str = ""
    tagline: str = ""


# ---------------------------------------------------------------------------
# System Prompts（与 ai-service/main.py 保持一致）
# ---------------------------------------------------------------------------

CHAT_SYSTEM_PROMPT = """你是「Website Planning Brief AI」的资深产品经理，擅长把一句模糊的想法聊成可以开发的完整需求。

你的思考方式：
1. 先理解用户已经说清楚的内容，用一句话复述确认。
2. 再主动联想：用户提到的这个功能，在真实产品里通常还会牵连哪些配套功能、数据、异常和权限？例如提到个人中心就该想到好友与私信，提到详情页就该想到导航与周边推荐。
3. 每轮只挑一个当前最关键的缺失去追问，给出 2 到 3 个具体选项，降低用户的回答成本。
4. 不要机械地按清单逐项审问，也不要重复追问已经明确的信息；顺着用户当前的业务上下文自然展开。
5. 当核心业务闭环、关键异常和权限边界都清楚后，直接回复：需求已经足够清晰，点击生成策划书即可。

输出格式（必须严格遵守）：
只输出纯文本。绝对不要使用 Markdown：不要用星号加粗、不要井号标题、不要短横线列表、不要代码块、不要表格。
用换行分段，像产品经理在聊天软件里说话。每次回复不超过 200 字，全程使用简体中文。

下面是对话示例，请模仿这种顺着功能联想配套能力的追问风格：

示例一
用户：我想要一个个人中心。
你：明白，个人中心用来沉淀用户自己的内容。
除了资料编辑和我的订单，用户之间需不需要加好友或私信？如果暂时不做社交，也可以只保留收藏和浏览记录，你更倾向哪种？

示例二
用户：我们会有景点详情页。
你：收到，详情页重点展示景点介绍、门票和开放时间。
用户看完详情后通常会关心怎么过去、附近还有什么，需要加地图导航和周边推荐吗？还是先只保留收藏功能？

示例三
用户：用户可以下单购买会员。
你：好的，会员购买流程我记下了。
支付失败在真实业务里很常见，你希望怎么处理：提示用户重试、自动取消订单，还是保留订单等他稍后支付？这决定了订单状态机怎么设计。"""

OUTLINE_SYSTEM_PROMPT = """你是资深网站策划师兼系统架构师。请把用户与你的完整对话，整理成一份结构化的《网站策划书》大纲 JSON。

你的职责是根据对话中的真实业务，自由设计功能拓扑、架构深度和核心链路，像真正的产品经理和架构师一样思考。不要套用通用模板，不要输出空洞的占位内容；所有图表都要落到用户聊过的角色、模块、接口和第三方服务上。你只需要遵守下面的 JSON 结构和 Mermaid 语法格式。

1. 只输出一个 JSON 对象，不要用 Markdown 代码块包裹，不要输出解释、前言或后记。
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
  "featureMindmap": "mindmap\\n  网站名称\\n    用户模块\\n      注册登录",
  "systemDiagram": "graph TD\\n  U[用户浏览器] --> W[前端页面]",
  "coreFlowDiagram": "sequenceDiagram\\n  participant U as 用户\\n  participant W as 前端\\n  U->>W: 提交表单",
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
9. 三个图表字段都必须是纯 Mermaid 代码字符串（不要带 ``` 围栏），内容必须基于对话里的真实业务：
   - featureMindmap：用 mindmap 语法，根节点是网站名称，一级分支 3 到 5 个（如用户、核心业务、后台），每个分支下 2 到 4 个具体功能节点，用缩进表达层级，不要使用括号形状。
   - systemDiagram：用 graph TD 语法，至少 8 个节点，覆盖前端页面、接口层、业务服务、数据存储和至少一个第三方服务（如支付、短信、对象存储），并用带文字的箭头标出关键异常分支。
   - coreFlowDiagram：用 sequenceDiagram 语法，从对话中挑出最核心的一条业务链路（如下单支付、内容发布、预约），至少 4 个参与者、8 条消息，包含一次失败、回调或补偿。
   图表要体现业务深度，但不要编造对话中完全不存在的大型系统。
10. 下面的示例只用于模仿语法格式，内容必须替换成当前对话里的真实业务：

featureMindmap 示例：
mindmap
  校园二手书
    用户
      注册认证
      个人主页
    书籍
      发布闲置
      搜索筛选
    交易
      下单
      面交确认

systemDiagram 示例：
graph TD
  U[用户浏览器] --> W[前端页面]
  W --> G[接口网关]
  G --> S[业务服务]
  S --> DB[主数据库]
  S --> C[缓存]
  S --> P[支付服务]
  P -->|支付回调| S
  S -->|失败重试| Q[消息队列]

coreFlowDiagram 示例：
sequenceDiagram
  participant U as 用户
  participant W as 前端
  participant A as 接口层
  participant S as 业务服务
  participant P as 支付服务
  U->>W: 点击购买
  W->>A: 提交订单
  A->>S: 校验库存与权限
  S->>P: 发起支付
  P-->>S: 返回支付结果
  S-->>A: 更新订单状态
  A-->>W: 返回结果
  W-->>U: 展示结果页

11. Mermaid 语法安全约束（防止前端渲染崩溃）：
   - 三个图表字段内禁止出现双引号字符，否则会破坏 JSON。
   - 节点和消息文案尽量只使用纯中文、字母和数字，避免括号、花括号、竖线、分号等特殊字符。
   - sequenceDiagram 语法里的冒号只用于分隔消息，消息文案中不要再出现冒号。
   - 图表代码中不要出现 ``` 围栏或任何 Markdown。"""

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
    "必须同时包含非空的 featureMindmap（mindmap 语法）、systemDiagram（graph TD 语法）、"
    "coreFlowDiagram（sequenceDiagram 语法）三个字段，代码不要带 Markdown 围栏；"
    "节点和消息文案避免双引号与括号，不要包含任何 html 字段，确保 JSON 正确闭合。"
)

HTML_CORRECTION = (
    "你上一次的输出不是合法的 {\"html\": \"...\"} JSON，或 HTML 不完整：__ERROR__。"
    "请重新输出，只包含一个 html 字段；html 字符串内禁止出现双引号字符，"
    "所有 HTML 属性一律使用单引号，并确保字符串正确闭合。"
)


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

def strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


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


def normalize_diagram(
    value: str,
    *,
    label: str,
    prefixes: tuple[str, ...],
    min_lines: int,
    required_snippet: str = "",
    snippet_hint: str = "",
    require_indent: bool = False,
) -> str:
    """清洗 Mermaid 代码并做语法级校验。

    只约束图表语法，不限制业务内容。不合法时抛 ValueError，
    由调用方决定是否触发模型自动纠错。
    """
    text = strip_code_fence(value.strip())
    text = re.sub(r"^mermaid\s*", "", text, flags=re.IGNORECASE).strip()

    if '"' in text:
        raise ValueError(f"{label} 中出现了双引号，会破坏 JSON 并导致渲染失败")

    lowered = text.lower()
    if not any(lowered.startswith(prefix) for prefix in prefixes):
        raise ValueError(f"{label} 必须使用 Mermaid 的 {' / '.join(prefixes)} 语法开头")

    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < min_lines:
        raise ValueError(f"{label} 内容过于简单，至少需要 {min_lines} 行节点或消息")

    if require_indent and not any(line[:1].isspace() for line in lines[1:]):
        raise ValueError(f"{label} 必须用缩进表达层级，例如 mindmap 根节点下方缩进两格")

    if required_snippet and required_snippet not in text:
        raise ValueError(f"{label} 语法不完整，{snippet_hint}")

    return text


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


def _call_model(
    client: OpenAI,
    model: str,
    messages: list[dict],
    *,
    temperature: float,
    max_tokens: int,
    json_mode: bool = False,
) -> tuple[str, str | None]:
    extra = {}
    # thinking 是智谱扩展参数，只对智谱域名发送，避免其他兼容服务报错
    if _is_zhipu() and THINKING_MODE in ("enabled", "disabled"):
        extra["extra_body"] = {"thinking": {"type": THINKING_MODE}}

    kwargs = {
        "model": model,
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
        raise ToolError(f"模型请求超时（{_env('MODEL_TIMEOUT', '180')} 秒），请稍后重试。") from exc
    except APIStatusError as exc:
        provider_message = exc.response.text[:600] if exc.response is not None else ""
        if exc.status_code in (401, 403):
            raise ToolError(
                f"模型服务鉴权失败（HTTP {exc.status_code}），请检查 OPENAI_API_KEY 是否正确。"
            ) from exc
        if exc.status_code == 429:
            raise ToolError(f"模型服务限流（HTTP 429），请稍后重试：{provider_message}") from exc
        if exc.status_code == 400:
            raise ToolError(
                f"模型服务拒绝了请求（HTTP 400），请检查 MODEL_NAME={model} 是否受支持：{provider_message}"
            ) from exc
        raise ToolError(f"模型服务返回 HTTP {exc.status_code}：{provider_message}") from exc
    except APIConnectionError as exc:
        raise ToolError(f"连接不上模型服务（{_base_url()}），请检查 OPENAI_BASE_URL 和网络。") from exc

    choice = response.choices[0]
    return choice.message.content or "", choice.finish_reason


def _complete_json(
    messages: list[dict],
    *,
    max_tokens: int,
    parse,
    correction_hint: str,
) -> dict:
    """调用模型并解析 JSON；失败时把错误和上一次输出回传，自动重试一次。"""
    client = get_openai_client()
    model = get_model_name()
    last_error = "未知错误"

    for attempt in (1, 2):
        content, finish_reason = _call_model(
            client,
            model,
            messages,
            temperature=0.4,
            max_tokens=max_tokens,
            json_mode=True,
        )

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
            return parse(data)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt == 1:
                messages = messages + [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": correction_hint.replace("__ERROR__", str(exc))},
                ]
                continue
            break

    raise ToolError(f"两次生成都未得到合法结果：{last_error}")


def _prepare_history(messages: list[ChatMessage]) -> list[dict]:
    history = trim_history([message.model_dump() for message in messages])
    if not history:
        raise ToolError("messages 不能为空")
    if history[-1]["role"] != "user":
        raise ToolError("最后一条消息必须来自用户（role=user）")
    return history


def _validate_outline(data: dict) -> dict:
    """把模型输出整理成最终大纲；三张图在这里做语法校验，不合法会触发重试。"""
    if not isinstance(data, dict):
        raise ValueError("模型返回的顶层不是 JSON 对象")

    site_name = str(data.get("siteName") or "").strip()
    if not site_name:
        raise ValueError("缺少 siteName")

    raw_pages = data.get("pages")
    if not isinstance(raw_pages, list) or not raw_pages:
        raise ValueError("pages 不能为空，至少需要 1 个页面")

    pages = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_pages, start=1):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue

        page_id = str(raw.get("id") or "").strip() or f"page-{index}"
        if page_id in seen_ids:
            page_id = f"{page_id}-{index}"
        seen_ids.add(page_id)

        sections = []
        for item in raw.get("sections") or []:
            if isinstance(item, str):
                sections.append({"name": item, "description": ""})
            elif isinstance(item, dict) and str(item.get("name") or "").strip():
                sections.append(
                    {
                        "name": str(item["name"]).strip(),
                        "description": str(item.get("description") or "").strip(),
                    }
                )

        pages.append(
            {
                "id": page_id,
                "name": name,
                "path": str(raw.get("path") or "/").strip() or "/",
                "purpose": str(raw.get("purpose") or "").strip(),
                "sections": sections,
            }
        )

    if not pages:
        raise ValueError("pages 中没有有效页面（每页必须有 name）")

    style = data.get("styleGuide")
    style = style if isinstance(style, dict) else {}

    return {
        "siteName": site_name,
        "tagline": str(data.get("tagline") or "").strip(),
        "summary": str(data.get("summary") or "").strip(),
        "targetAudience": str(data.get("targetAudience") or "").strip(),
        "coreFeatures": [
            str(item).strip() for item in (data.get("coreFeatures") or []) if str(item).strip()
        ],
        "styleGuide": {
            "primaryColor": str(style.get("primaryColor") or "#2563eb"),
            "secondaryColor": str(style.get("secondaryColor") or "#0f172a"),
            "fontFamily": str(
                style.get("fontFamily")
                or "system-ui, -apple-system, 'Microsoft YaHei', sans-serif"
            ),
            "tone": str(style.get("tone") or "现代、简洁、有设计感"),
        },
        "featureMindmap": normalize_diagram(
            str(data.get("featureMindmap") or ""),
            label="featureMindmap",
            prefixes=("mindmap",),
            min_lines=6,
            require_indent=True,
        ),
        "systemDiagram": normalize_diagram(
            str(data.get("systemDiagram") or ""),
            label="systemDiagram",
            prefixes=("graph", "flowchart"),
            min_lines=6,
            required_snippet="-->",
            snippet_hint="请使用 A --> B 这样的箭头连接节点",
        ),
        "coreFlowDiagram": normalize_diagram(
            str(data.get("coreFlowDiagram") or ""),
            label="coreFlowDiagram",
            prefixes=("sequencediagram",),
            min_lines=8,
            required_snippet="->>",
            snippet_hint="请使用 U->>W: 提交订单 这样的消息箭头表示交互",
        ),
        "pages": pages,
    }


def parse_page_html(data: dict) -> dict:
    """从 JSON 中取出 html 字段，兼容模型偶尔使用的其他键名。"""
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
    return {"html": html}


def build_page_prompt(
    page: PageInput,
    style: StyleGuideInput,
    site: SiteInput,
) -> str:
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


def _chat_requirement_sync(history: list[dict]) -> str:
    client = get_openai_client()
    messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}] + history
    content, _ = _call_model(
        client,
        get_model_name(),
        messages,
        temperature=0.7,
        max_tokens=CHAT_MAX_TOKENS,
    )
    reply = content.strip()
    if not reply:
        raise ToolError("模型返回内容为空，请重试")
    return reply


def _generate_outline_sync(history: list[dict]) -> dict:
    messages = (
        [{"role": "system", "content": OUTLINE_SYSTEM_PROMPT}]
        + history
        + [
            {
                "role": "user",
                "content": (
                    "请根据以上全部对话，输出策划书大纲 JSON。记住：不要包含任何 HTML，"
                    "必须包含 Mermaid 格式的 featureMindmap、systemDiagram、coreFlowDiagram。"
                ),
            }
        ]
    )
    return _complete_json(
        messages,
        max_tokens=OUTLINE_MAX_TOKENS,
        parse=_validate_outline,
        correction_hint=OUTLINE_CORRECTION,
    )


def _generate_page_html_sync(
    page: PageInput,
    style: StyleGuideInput,
    site: SiteInput,
) -> str:
    messages = [
        {"role": "system", "content": HTML_SYSTEM_PROMPT},
        {"role": "user", "content": build_page_prompt(page, style, site)},
    ]
    result = _complete_json(
        messages,
        max_tokens=HTML_MAX_TOKENS,
        parse=parse_page_html,
        correction_hint=HTML_CORRECTION,
    )
    return result["html"]


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = MCPServer(
    "website-planning-brief",
    instructions=(
        "网站策划书生成工具。先用 chat_requirement 多轮澄清需求，"
        "再用 generate_outline 生成含三张 Mermaid 图的策划书大纲，"
        "最后用 generate_page_html 逐页生成静态 HTML 概念稿。"
    ),
)


@mcp.tool()
async def chat_requirement(messages: list[ChatMessage]) -> str:
    """多轮需求澄清。

    接收完整对话历史，扮演资深产品经理，顺着用户当前功能主动联想配套能力
    （查漏补缺），每轮只追问一个最关键的信息，并给出 2 到 3 个选项。

    Args:
        messages: 对话历史，role 为 user 或 assistant，最后一条必须是 user。

    Returns:
        下一条追问的纯文本（无 Markdown，200 字以内）。
    """
    history = _prepare_history(messages)
    return await anyio.to_thread.run_sync(_chat_requirement_sync, history)


@mcp.tool()
async def generate_outline(messages: list[ChatMessage]) -> str:
    """生成策划书大纲 JSON。

    根据完整对话输出站点信息、视觉规范、页面规划，以及三张 Mermaid 图：
    featureMindmap（mindmap）、systemDiagram（graph TD）、coreFlowDiagram（sequenceDiagram）。
    服务端会校验图表语法并在失败时自动纠错一次；返回的图表字段不带 Markdown 围栏。

    Args:
        messages: 完整对话历史，最后一条必须是 user。

    Returns:
        策划书大纲 JSON 字符串（UTF-8，含中文，未转义）。
    """
    history = _prepare_history(messages)
    outline = await anyio.to_thread.run_sync(_generate_outline_sync, history)
    return json.dumps(outline, ensure_ascii=False, indent=2)


@mcp.tool()
async def generate_page_html(
    page: PageInput,
    style_guide: StyleGuideInput | None = None,
    site: SiteInput | None = None,
) -> str:
    """为单个页面生成现代风格的静态 HTML 概念稿。

    Args:
        page: 页面信息，来自 generate_outline 返回的 pages 数组中的一项。
        style_guide: 视觉规范（主色、辅助色、字体、基调），建议传入大纲里的 styleGuide。
        site: 站点信息（siteName、tagline），可选，用于导航与页脚文案。

    Returns:
        完整的 HTML 文档字符串（以 <!DOCTYPE html> 开头，内联样式，无外部资源）。
    """
    html = await anyio.to_thread.run_sync(
        _generate_page_html_sync,
        page,
        style_guide or StyleGuideInput(),
        site or SiteInput(),
    )
    return html


if __name__ == "__main__":
    # stdio 传输：由 Cursor / Claude Desktop 作为子进程启动
    mcp.run(transport="stdio")
