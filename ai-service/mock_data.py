"""离线联调用的固定返回数据。

设置 MOCK_LLM=1 时三个接口直接返回这里的数据，不调用智谱：
- /chat                 -> MOCK_CHAT_REPLY
- /generate-outline     -> SAMPLE_OUTLINE
- /generate-page-html   -> SAMPLE_PAGE_HTML
用途：API Key 未配置、前端联调、或不想消耗额度时验证整条链路。
"""

MOCK_CHAT_REPLY = (
    "明白，你想做一个记录咖啡豆风味的社区网站。先锁定一个关键点："
    "用户提交一条品鉴记录时，如果评分和笔记都为空，"
    "你希望系统直接拒绝提交、允许保存为草稿，还是自动补全默认值？"
    "这决定了表单校验规则和数据模型的边界。"
)

SAMPLE_OUTLINE = {
    "siteName": "豆香志",
    "tagline": "记录每一杯咖啡的风味",
    "summary": "面向咖啡爱好者的风味记录与分享社区，支持评分、笔记与推荐。",
    "targetAudience": "喜欢手冲咖啡、愿意记录和分享品鉴体验的年轻咖啡爱好者",
    "coreFeatures": ["风味评分", "品鉴笔记", "社区推荐"],
    "styleGuide": {
        "primaryColor": "#8b5e34",
        "secondaryColor": "#1f2937",
        "fontFamily": "system-ui, -apple-system, 'Microsoft YaHei', sans-serif",
        "tone": "温暖、有质感、偏杂志风格",
    },
    "systemDiagram": (
        "graph TD\n"
        "  A[用户浏览器] --> B[首页与探索页]\n"
        "  B --> C[记录页表单]\n"
        "  C --> D[后端记录接口]\n"
        "  D --> E[校验与权限服务]\n"
        "  E -->|通过| F[(记录数据库)]\n"
        "  E -->|校验失败| G[表单错误提示]\n"
        "  F --> H[社区推荐服务]\n"
        "  H --> B\n"
        "  D --> I[第三方图片存储]\n"
        "  I -->|上传失败| G"
    ),
    "pages": [
        {
            "id": "home",
            "name": "首页",
            "path": "/",
            "purpose": "介绍产品价值并引导用户开始记录",
            "sections": [
                {"name": "顶部导航", "description": "品牌名与主要页面入口"},
                {"name": "首屏 Hero", "description": "标语、产品介绍与开始记录按钮"},
                {"name": "精选风味", "description": "三张精选咖啡风味卡片"},
            ],
        },
        {
            "id": "explore",
            "name": "探索",
            "path": "/explore",
            "purpose": "浏览社区里的风味记录",
            "sections": [
                {"name": "筛选栏", "description": "按产地和烘焙度筛选"},
                {"name": "记录列表", "description": "社区用户的品鉴记录卡片"},
            ],
        },
        {
            "id": "record",
            "name": "记录",
            "path": "/record",
            "purpose": "引导用户完成一条风味记录",
            "sections": [
                {"name": "记录表单", "description": "填写咖啡豆信息、评分与笔记"},
                {"name": "风味标签", "description": "选择酸度、甜感、余韵等标签"},
            ],
        },
    ],
}

SAMPLE_PAGE_HTML = (
    "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width, initial-scale=1'>"
    "<title>豆香志 - 首页</title><style>"
    ":root{--primary:#8b5e34;--dark:#1f2937;--light:#f8f4ef}"
    "*{box-sizing:border-box}"
    "body{margin:0;font-family:system-ui,-apple-system,'Microsoft YaHei',sans-serif;color:var(--dark);line-height:1.6}"
    ".wrap{max-width:1200px;margin:0 auto;padding:0 24px}"
    "nav{display:flex;justify-content:space-between;align-items:center;padding:20px 0}"
    "nav a{color:var(--dark);text-decoration:none;margin-left:24px;font-size:14px}"
    ".hero{padding:96px 0 72px;background:linear-gradient(135deg,#f3e8dc,#f8f4ef 60%,#e8dccd)}"
    ".hero h1{font-size:52px;line-height:1.2;margin:0 0 16px;max-width:640px}"
    ".hero p{font-size:18px;color:#4b5563;max-width:520px}"
    ".btn{display:inline-block;margin-top:24px;padding:14px 28px;border-radius:999px;background:var(--primary);color:#fff;text-decoration:none;transition:transform .2s}"
    ".btn:hover{transform:translateY(-2px)}"
    ".cards{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;padding:56px 0}"
    ".card{background:#fff;border-radius:16px;padding:24px;box-shadow:0 12px 30px rgba(31,41,55,.08);transition:box-shadow .2s,transform .2s}"
    ".card:hover{transform:translateY(-4px);box-shadow:0 18px 40px rgba(31,41,55,.14)}"
    ".card .icon{font-size:28px}"
    "footer{padding:32px 0;color:#6b7280;font-size:13px;border-top:1px solid #e5e7eb}"
    "@media(max-width:768px){.hero h1{font-size:34px}.cards{grid-template-columns:1fr}}"
    "</style></head><body>"
    "<div class='wrap'><nav><strong>豆香志</strong><div><a href='/'>首页</a><a href='/explore'>探索</a><a href='/record'>记录</a></div></nav></div>"
    "<section class='hero'><div class='wrap'><h1>记录每一杯咖啡的风味</h1>"
    "<p>给你喝过的每一支豆子留下评分与笔记，发现同好们正在推荐什么。</p>"
    "<a class='btn' href='/record'>开始记录</a></div></section>"
    "<section class='wrap cards'>"
    "<div class='card'><div class='icon'>☕</div><h3>风味评分</h3><p>从酸度、甜感到余韵，六维记录你的真实感受。</p></div>"
    "<div class='card'><div class='icon'>📝</div><h3>品鉴笔记</h3><p>写下冲煮参数与风味描述，沉淀属于你的咖啡档案。</p></div>"
    "<div class='card'><div class='icon'>🌍</div><h3>社区推荐</h3><p>看看大家最近在喝什么，按产地与烘焙度探索。</p></div>"
    "</section>"
    "<footer><div class='wrap'>豆香志 · 记录每一杯咖啡的风味</div></footer>"
    "</body></html>"
)
