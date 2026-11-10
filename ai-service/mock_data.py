"""离线联调用的固定返回数据。

设置 MOCK_LLM=1 时 /generate 直接返回这份数据，不调用智谱接口。
用途：在 API Key 还没配好、或者前端联调不想消耗额度时，验证整条链路。
"""

SAMPLE_BRIEF = {
    "siteName": "灵感清单",
    "tagline": "一个想法，一份完整的网站策划书",
    "summary": "用户输入网站想法，自动生成包含页面规划与静态概念稿的策划书。",
    "targetAudience": "有建站想法但缺乏设计与策划经验的小团队和个人开发者",
    "coreFeatures": ["想法结构化", "页面规划", "静态概念稿预览"],
    "styleGuide": {
        "primaryColor": "#2563eb",
        "secondaryColor": "#0f172a",
        "fontFamily": "system-ui, -apple-system, sans-serif",
        "tone": "简洁、清爽、技术感",
    },
    "pages": [
        {
            "id": "home",
            "name": "首页",
            "path": "/",
            "purpose": "一句话讲清产品价值，引导用户输入想法",
            "sections": [
                {"name": "顶部导航", "description": "品牌名与主要入口"},
                {"name": "首屏 Hero", "description": "标语、说明文字与主按钮"},
            ],
            "html": (
                "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
                "<title>灵感清单</title><style>"
                "body{margin:0;font-family:system-ui,sans-serif;color:#0f172a}"
                "header{display:flex;justify-content:space-between;align-items:center;padding:18px 40px;border-bottom:1px solid #e5e7eb}"
                ".hero{padding:90px 40px;background:linear-gradient(135deg,#dbeafe,#ede9fe)}"
                "h1{font-size:40px;margin:0 0 12px}.cta{display:inline-block;margin-top:28px;padding:12px 26px;background:#2563eb;color:#fff;border-radius:8px;text-decoration:none}"
                "</style></head><body><header><strong>灵感清单</strong><nav>首页 · 功能 · 关于</nav></header>"
                "<section class='hero'><h1>一个想法，一份完整的网站策划书</h1>"
                "<p>输入一句话，自动获得页面规划、视觉风格与静态概念稿。</p>"
                "<a class='cta' href='#'>开始生成</a></section></body></html>"
            ),
        },
        {
            "id": "about",
            "name": "关于",
            "path": "/about",
            "purpose": "介绍产品定位与适用人群",
            "sections": [{"name": "产品介绍", "description": "产品定位与解决什么问题"}],
            "html": (
                "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
                "<title>关于灵感清单</title><style>"
                "body{margin:0;font-family:system-ui,sans-serif;color:#0f172a}"
                "main{max-width:760px;margin:0 auto;padding:80px 24px}h1{font-size:32px}"
                "</style></head><body><main><h1>关于灵感清单</h1>"
                "<p>我们帮助有建站想法的人，在动手写第一行代码之前，先看到完整的页面规划与视觉概念。</p>"
                "</main></body></html>"
            ),
        },
    ],
}
