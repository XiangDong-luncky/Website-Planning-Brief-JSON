<script setup>
import { computed, ref } from 'vue'

const idea = ref('')
const loading = ref(false)
const error = ref('')
const brief = ref(null)
const activePageId = ref('')

const examples = [
  '一个记录咖啡豆风味的社区网站，用户可以打分、写品鉴笔记',
  '一个面向大学生的二手教材交易平台',
  '一个宠物领养信息聚合网站，支持按城市筛选'
]

const activePage = computed(() => {
  const pages = brief.value?.pages
  if (!pages?.length) return null
  return pages.find((page) => page.id === activePageId.value) ?? pages[0]
})

function extractError(data) {
  if (!data) return ''
  const detail = data.detail ?? data.error ?? data.message
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg ?? JSON.stringify(item)).join('；')
  }
  return JSON.stringify(detail)
}

async function generate() {
  const text = idea.value.trim()
  if (!text || loading.value) return

  loading.value = true
  error.value = ''
  brief.value = null
  activePageId.value = ''

  try {
    const response = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ idea: text })
    })

    const data = await response.json().catch(() => null)

    if (!response.ok) {
      throw new Error(extractError(data) || `请求失败（HTTP ${response.status}）`)
    }
    if (!data?.pages?.length) {
      throw new Error('返回数据缺少 pages 字段，请检查后端与 AI 服务')
    }

    brief.value = data
    activePageId.value = data.pages[0].id ?? ''
  } catch (err) {
    const message = err instanceof TypeError ? '连不上后端服务，请确认 Spring Boot 已在 8080 端口启动。' : err.message
    error.value = message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <span class="logo">✦</span>
        <div>
          <h1>Website Planning Brief AI</h1>
          <p>输入一个网站想法，生成策划书与页面概念稿</p>
        </div>
      </div>
      <span class="stack">Vue 3 · Spring Boot · FastAPI · GLM</span>
    </header>

    <main class="layout">
      <aside class="panel input-panel">
        <label class="label" for="idea">你的网站想法</label>
        <textarea
          id="idea"
          v-model="idea"
          maxlength="2000"
          placeholder="例如：一个帮助独立开发者交换项目进展的社区，支持按技术栈筛选..."
          @keydown.ctrl.enter="generate"
        ></textarea>
        <div class="counter">{{ idea.length }} / 2000</div>

        <div class="examples">
          <span class="examples-label">试试这些：</span>
          <button
            v-for="example in examples"
            :key="example"
            class="chip"
            type="button"
            :disabled="loading"
            @click="idea = example"
          >
            {{ example }}
          </button>
        </div>

        <button class="generate" type="button" :disabled="loading || !idea.trim()" @click="generate">
          {{ loading ? '生成中…' : '生成策划书' }}
        </button>
        <p class="hint">生成通常需要 30～90 秒，可以用 Ctrl + Enter 提交。</p>
      </aside>

      <section class="panel preview-panel">
        <div v-if="!brief && !loading && !error" class="state">
          <div class="state-icon">🗂️</div>
          <h2>还没有策划书</h2>
          <p>在左侧描述你的想法，点击「生成策划书」。</p>
        </div>

        <div v-else-if="loading" class="state">
          <div class="spinner"></div>
          <h2>AI 正在策划中…</h2>
          <p>正在规划页面结构并撰写 HTML 概念稿，请保持页面打开。</p>
        </div>

        <div v-else-if="error" class="state error">
          <div class="state-icon">⚠️</div>
          <h2>生成失败</h2>
          <p>{{ error }}</p>
          <button class="retry" type="button" @click="generate">重试</button>
        </div>

        <template v-else-if="brief && activePage">
          <div class="brief-head">
            <div class="brief-title">
              <h2>{{ brief.siteName }}</h2>
              <p>{{ brief.tagline }}</p>
            </div>
            <div v-if="brief.styleGuide" class="colors" title="主色 / 辅助色">
              <span class="swatch" :style="{ background: brief.styleGuide.primaryColor }"></span>
              <span class="swatch" :style="{ background: brief.styleGuide.secondaryColor }"></span>
            </div>
          </div>

          <div class="tabs">
            <button
              v-for="page in brief.pages"
              :key="page.id"
              type="button"
              class="tab"
              :class="{ active: page.id === activePage.id }"
              @click="activePageId = page.id"
            >
              {{ page.name }}
            </button>
          </div>

          <div class="preview-body">
            <div class="preview-meta">
              <code>{{ activePage.path }}</code>
              <span>{{ activePage.purpose }}</span>
            </div>
            <iframe class="frame" :srcdoc="activePage.html" sandbox="" :title="activePage.name"></iframe>
          </div>

          <details class="brief-extra">
            <summary>查看完整策划信息</summary>
            <div class="brief-extra-body">
              <p><strong>项目概述：</strong>{{ brief.summary }}</p>
              <p><strong>目标用户：</strong>{{ brief.targetAudience }}</p>
              <p><strong>核心功能：</strong>{{ brief.coreFeatures?.join('、') }}</p>
              <p>
                <strong>页面：</strong>
                <span v-for="page in brief.pages" :key="page.id" class="page-tag">{{ page.name }}</span>
              </p>
            </div>
          </details>
        </template>
      </section>
    </main>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  background: #fff;
  border-bottom: 1px solid var(--border);
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  color: #fff;
  font-size: 20px;
}

.brand h1 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.brand p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--muted);
}

.stack {
  font-size: 12px;
  color: var(--muted);
}

.layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 400px minmax(0, 1fr);
  gap: 16px;
  padding: 16px;
}

.panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 14px;
  min-height: 0;
}

.input-panel {
  display: flex;
  flex-direction: column;
  padding: 20px;
}

.label {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}

textarea {
  height: 180px;
  resize: vertical;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  outline: none;
  line-height: 1.6;
  font-size: 14px;
  transition: border-color 0.15s;
}

textarea:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.counter {
  margin-top: 6px;
  text-align: right;
  font-size: 12px;
  color: var(--muted);
}

.examples {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.examples-label {
  width: 100%;
  font-size: 12px;
  color: var(--muted);
}

.chip {
  max-width: 100%;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #f9fafb;
  color: #374151;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip:hover:not(:disabled) {
  border-color: var(--primary);
  color: var(--primary);
}

.generate {
  margin-top: auto;
  padding: 12px 16px;
  border: none;
  border-radius: 10px;
  background: var(--primary);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s;
}

.generate:hover:not(:disabled) {
  opacity: 0.9;
}

.generate:disabled {
  background: #93a3b8;
  cursor: not-allowed;
}

.hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--muted);
  text-align: center;
}

.preview-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 32px;
  text-align: center;
  color: var(--muted);
}

.state h2 {
  margin: 8px 0 0;
  font-size: 18px;
  color: #111827;
}

.state p {
  margin: 0;
  max-width: 460px;
  font-size: 14px;
  line-height: 1.7;
}

.state-icon {
  font-size: 40px;
}

.state.error p {
  color: #b91c1c;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #dbeafe;
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.retry {
  margin-top: 14px;
  padding: 8px 22px;
  border: 1px solid var(--primary);
  border-radius: 8px;
  background: #fff;
  color: var(--primary);
  cursor: pointer;
}

.brief-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px 12px;
  border-bottom: 1px solid var(--border);
}

.brief-title h2 {
  margin: 0;
  font-size: 18px;
}

.brief-title p {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--muted);
}

.colors {
  display: flex;
  gap: 6px;
  padding-top: 4px;
}

.swatch {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 1px solid var(--border);
}

.tabs {
  display: flex;
  gap: 6px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
}

.tab {
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #fff;
  color: #374151;
  font-size: 13px;
  white-space: nowrap;
  cursor: pointer;
}

.tab.active {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
}

.preview-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 12px 16px 16px;
}

.preview-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 2px 10px;
  font-size: 12px;
  color: var(--muted);
}

.preview-meta code {
  padding: 1px 8px;
  border-radius: 6px;
  background: #f3f4f6;
  color: #374151;
}

.frame {
  flex: 1;
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fff;
}

.brief-extra {
  border-top: 1px solid var(--border);
  padding: 10px 20px 14px;
  font-size: 13px;
  color: #374151;
}

.brief-extra summary {
  cursor: pointer;
  color: var(--muted);
}

.brief-extra-body p {
  margin: 8px 0;
  line-height: 1.6;
}

.page-tag {
  display: inline-block;
  margin-right: 6px;
  padding: 1px 8px;
  border-radius: 6px;
  background: #eff6ff;
  color: var(--primary);
  font-size: 12px;
}

@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(0, 1fr);
  }

  .stack {
    display: none;
  }

  textarea {
    height: 120px;
  }
}
</style>
