<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'

let mermaidPromise = null

function getMermaid() {
  // 按需加载：只有真正要渲染架构图时才下载 mermaid（体积较大）
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then((mod) => {
      const mermaid = mod.default
      mermaid.initialize({
        startOnLoad: false,
        theme: 'base',
        securityLevel: 'strict',
        themeVariables: {
          primaryColor: '#eff6ff',
          primaryTextColor: '#1f2937',
          primaryBorderColor: '#93c5fd',
          lineColor: '#94a3b8',
          secondaryColor: '#f3f4f6',
          tertiaryColor: '#ffffff',
          fontSize: '14px'
        }
      })
      return mermaid
    })
  }
  return mermaidPromise
}

const CONVERSATION_KEY = 'wpbrief.conversation.v2'
const CONFIG_KEY = 'wpbrief.model.v3'
const API_KEY = 'wpbrief.apiKey.v3'
const DEFAULT_BASE_URL = 'https://open.bigmodel.cn/api/paas/v4'
const DEFAULT_MODEL = 'glm-4.7-flash'
const DIAGRAM_TAB = '__diagram__'

const messages = ref(loadMessages())
const input = ref('')
const sending = ref(false)
const chatError = ref('')

const generatingOutline = ref(false)
const outlineError = ref('')
const outline = ref(null)

const activeTabId = ref('')
const pageStates = reactive({})

const diagramSvg = ref('')
const diagramError = ref('')

const chatBody = ref(null)
const inputEl = ref(null)

const modelConfig = reactive(loadModelConfig())
const settingsOpen = ref(false)
const settingsError = ref('')
const settingsDraft = reactive({
  apiKey: '',
  baseUrl: DEFAULT_BASE_URL,
  modelName: DEFAULT_MODEL,
  showKey: false
})

const isConfigured = computed(
  () => Boolean(modelConfig.apiKey && modelConfig.baseUrl && modelConfig.modelName)
)

const activePage = computed(() => {
  if (!outline.value || activeTabId.value === DIAGRAM_TAB) return null
  const pages = outline.value.pages
  if (!pages?.length) return null
  return pages.find((page) => page.id === activeTabId.value) ?? pages[0]
})

const activeState = computed(() => (activePage.value ? pageStates[activePage.value.id] : null))

const canChat = computed(() => !sending.value && !generatingOutline.value)

function loadMessages() {
  try {
    const raw = localStorage.getItem(CONVERSATION_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (item) =>
        item &&
        typeof item.content === 'string' &&
        (item.role === 'user' || item.role === 'assistant')
    )
  } catch {
    return []
  }
}

function persistMessages() {
  try {
    localStorage.setItem(CONVERSATION_KEY, JSON.stringify(messages.value))
  } catch {
    // localStorage 超限或不可用时忽略，聊天本身不受影响
  }
}

watch(messages, persistMessages, { deep: true })

function loadModelConfig() {
  let baseUrl = DEFAULT_BASE_URL
  let modelName = DEFAULT_MODEL
  try {
    const saved = JSON.parse(localStorage.getItem(CONFIG_KEY) || '{}')
    if (typeof saved.baseUrl === 'string' && saved.baseUrl) baseUrl = saved.baseUrl
    if (typeof saved.modelName === 'string' && saved.modelName) modelName = saved.modelName
  } catch {
    // 配置损坏时回退默认值
  }
  return {
    apiKey: sessionStorage.getItem(API_KEY) || '',
    baseUrl,
    modelName
  }
}

function openSettings() {
  settingsError.value = ''
  Object.assign(settingsDraft, {
    apiKey: modelConfig.apiKey,
    baseUrl: modelConfig.baseUrl,
    modelName: modelConfig.modelName,
    showKey: false
  })
  settingsOpen.value = true
}

function saveSettings() {
  const apiKey = settingsDraft.apiKey.trim()
  const baseUrl = settingsDraft.baseUrl.trim().replace(/\/+$/, '')
  const modelName = settingsDraft.modelName.trim()

  if (!apiKey || !baseUrl || !modelName) {
    settingsError.value = 'API Key、Base URL、模型名称都必填'
    return
  }
  if (!/^https?:\/\//.test(baseUrl)) {
    settingsError.value = 'Base URL 必须以 http:// 或 https:// 开头'
    return
  }

  Object.assign(modelConfig, { apiKey, baseUrl, modelName })
  sessionStorage.setItem(API_KEY, apiKey)
  localStorage.setItem(CONFIG_KEY, JSON.stringify({ baseUrl, modelName }))

  chatError.value = ''
  settingsError.value = ''
  settingsOpen.value = false
}

function clearSettings() {
  sessionStorage.removeItem(API_KEY)
  localStorage.removeItem(CONFIG_KEY)
  Object.assign(modelConfig, {
    apiKey: '',
    baseUrl: DEFAULT_BASE_URL,
    modelName: DEFAULT_MODEL
  })
  Object.assign(settingsDraft, {
    apiKey: '',
    baseUrl: DEFAULT_BASE_URL,
    modelName: DEFAULT_MODEL,
    showKey: false
  })
  settingsOpen.value = false
}

function ensureConfigured() {
  if (isConfigured.value) return true
  openSettings()
  return false
}

function userConfigPayload() {
  return {
    apiKey: modelConfig.apiKey,
    baseUrl: modelConfig.baseUrl,
    modelName: modelConfig.modelName
  }
}

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

async function postJson(url, payload, timeoutMs = 120000) {
  if (!isConfigured.value) {
    openSettings()
    throw new Error('请先在「模型设置」中填写你自己的 API Key（BYOK）')
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...payload, userConfig: userConfigPayload() }),
      signal: controller.signal
    })
    const data = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(extractError(data) || `请求失败（HTTP ${response.status}）`)
    }
    return data
  } catch (err) {
    if (err.name === 'AbortError') throw new Error('请求超时，请重试')
    if (err instanceof TypeError) throw new Error('连不上后端服务，请确认 Spring Boot 已在 8080 端口启动。')
    throw err
  } finally {
    clearTimeout(timer)
  }
}

function scrollChatToBottom() {
  nextTick(() => {
    if (chatBody.value) chatBody.value.scrollTop = chatBody.value.scrollHeight
  })
}

async function sendMessage() {
  const text = input.value.trim()
  if (!text || !canChat.value) return
  if (!ensureConfigured()) {
    chatError.value = '请先配置你自己的模型（BYOK）：填写 API Key、Base URL 和模型名称。'
    return
  }

  chatError.value = ''
  messages.value.push({ role: 'user', content: text })
  input.value = ''
  scrollChatToBottom()
  sending.value = true

  try {
    const data = await postJson('/api/chat', { messages: messages.value }, 120000)
    if (!data?.reply) throw new Error('AI 没有返回内容，请重试')
    messages.value.push({ role: 'assistant', content: data.reply })
  } catch (err) {
    chatError.value = err.message
  } finally {
    sending.value = false
    scrollChatToBottom()
    inputEl.value?.focus()
  }
}

async function generateOutline() {
  if (generatingOutline.value || sending.value) return
  if (!messages.value.length) {
    chatError.value = '先和 AI 描述你的网站想法'
    return
  }
  if (!ensureConfigured()) {
    outlineError.value = '请先配置你自己的模型（BYOK）'
    return
  }

  if (messages.value[messages.value.length - 1].role !== 'user') {
    messages.value.push({
      role: 'user',
      content: '信息已经足够，请按目前掌握的信息生成策划书大纲。'
    })
  }

  generatingOutline.value = true
  outlineError.value = ''

  try {
    const data = await postJson('/api/generate-outline', { messages: messages.value }, 180000)
    if (!data?.pages?.length) throw new Error('返回的大纲缺少 pages 字段')

    outline.value = data
    activeTabId.value = DIAGRAM_TAB
    Object.keys(pageStates).forEach((key) => delete pageStates[key])
    renderDiagram()
  } catch (err) {
    outlineError.value = err.message
  } finally {
    generatingOutline.value = false
  }
}

let diagramToken = 0

async function renderDiagram() {
  const token = ++diagramToken
  diagramSvg.value = ''
  diagramError.value = ''

  const code = outline.value?.systemDiagram
  if (!code) {
    diagramError.value = '本次大纲没有返回系统架构图'
    return
  }

  try {
    const mermaid = await getMermaid()
    const { svg } = await mermaid.render(`brief-diagram-${token}`, code)
    if (token !== diagramToken) return
    diagramSvg.value = svg
  } catch (err) {
    if (token !== diagramToken) return
    diagramError.value = `架构图解析失败：${err?.message || err}`
  }
}

function showDiagram() {
  activeTabId.value = DIAGRAM_TAB
  if (!diagramSvg.value && !diagramError.value) renderDiagram()
}

function selectPage(page) {
  activeTabId.value = page.id
  ensurePageHtml(page)
}

async function ensurePageHtml(page) {
  if (!pageStates[page.id]) {
    pageStates[page.id] = { loading: false, error: '', html: '' }
  }
  const state = pageStates[page.id]
  if (state.loading || state.html) return

  state.loading = true
  state.error = ''

  try {
    const data = await postJson(
      '/api/generate-page-html',
      {
        page: {
          id: page.id,
          name: page.name,
          path: page.path,
          purpose: page.purpose,
          sections: page.sections
        },
        styleGuide: outline.value?.styleGuide ?? {},
        site: {
          siteName: outline.value?.siteName ?? '',
          tagline: outline.value?.tagline ?? ''
        }
      },
      320000
    )
    if (!data?.html) throw new Error('AI 没有返回 HTML，请重试')
    state.html = data.html
  } catch (err) {
    state.error = err.message
  } finally {
    state.loading = false
  }
}

function retryActivePage() {
  if (!activePage.value) return
  const state = pageStates[activePage.value.id]
  if (state) {
    state.loading = false
    state.error = ''
    state.html = ''
  }
  ensurePageHtml(activePage.value)
}

function resetConversation() {
  if (!window.confirm('清空当前对话和策划书？')) return
  messages.value = []
  input.value = ''
  chatError.value = ''
  outline.value = null
  outlineError.value = ''
  activeTabId.value = ''
  diagramSvg.value = ''
  diagramError.value = ''
  Object.keys(pageStates).forEach((key) => delete pageStates[key])
  persistMessages()
}
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <span class="logo">✦</span>
        <div>
          <h1>Website Planning Brief AI</h1>
          <p>先聊需求，再生成策划书，最后逐页出概念稿</p>
        </div>
      </div>
      <div class="top-actions">
        <span class="stack">Vue 3 · Spring Boot · FastAPI</span>
        <button class="settings-btn" type="button" @click="openSettings">
          <span class="dot" :class="{ on: isConfigured }"></span>
          <span>{{ isConfigured ? modelConfig.modelName : '配置模型' }}</span>
        </button>
      </div>
    </header>

    <main class="layout">
      <aside class="panel chat-panel">
        <div class="panel-head">
          <div class="panel-head-left">
            <span class="panel-title">需求访谈</span>
            <span class="step-badge">STEP 1</span>
          </div>
          <button class="link-btn" type="button" @click="resetConversation">重新开始</button>
        </div>

        <div ref="chatBody" class="chat-body">
          <div v-if="!messages.length" class="chat-empty">
            <div class="chat-empty-icon">💬</div>
            <p>先描述你的网站想法，AI 会像产品经理一样，一次追问一个最关键的逻辑盲区。</p>
          </div>

          <div
            v-for="(message, index) in messages"
            :key="index"
            class="bubble-row"
            :class="message.role"
          >
            <div class="avatar">{{ message.role === 'user' ? '你' : 'AI' }}</div>
            <div class="bubble">{{ message.content }}</div>
          </div>

          <div v-if="sending" class="bubble-row assistant">
            <div class="avatar">AI</div>
            <div class="bubble typing"><span></span><span></span><span></span></div>
          </div>
        </div>

        <p v-if="chatError" class="chat-error">{{ chatError }}</p>

        <div class="composer">
          <textarea
            ref="inputEl"
            v-model="input"
            rows="2"
            placeholder="继续补充需求，Enter 发送，Shift + Enter 换行"
            @keydown.enter.exact.prevent="sendMessage"
          ></textarea>
          <button
            class="send-btn"
            type="button"
            :disabled="!input.trim() || !canChat"
            @click="sendMessage"
          >
            发送
          </button>
        </div>

        <button
          class="outline-btn"
          type="button"
          :disabled="generatingOutline || sending || !messages.length"
          @click="generateOutline"
        >
          {{ generatingOutline ? '正在生成策划书…' : '信息已完善，生成策划书' }}
        </button>
      </aside>

      <section class="panel preview-panel">
        <div v-if="!outline && !generatingOutline && !outlineError" class="state">
          <div class="state-icon">🗂️</div>
          <h2>策划书会显示在这里</h2>
          <p>在左侧和 AI 聊清楚需求后，点击「信息已完善，生成策划书」。</p>
        </div>

        <div v-else-if="generatingOutline" class="state">
          <div class="spinner"></div>
          <h2>正在整理策划书…</h2>
          <p>AI 正在把对话总结为站点结构、页面规划与系统架构图。</p>
        </div>

        <div v-else-if="outlineError" class="state error">
          <div class="state-icon">⚠️</div>
          <h2>策划书生成失败</h2>
          <p>{{ outlineError }}</p>
          <button class="retry" type="button" @click="generateOutline">重试</button>
        </div>

        <template v-else-if="outline">
          <div class="brief-head">
            <div class="brief-title">
              <h2>{{ outline.siteName }}</h2>
              <p>{{ outline.tagline }}</p>
            </div>
            <div class="colors" title="主色 / 辅助色">
              <span
                class="swatch"
                :style="{ background: outline.styleGuide?.primaryColor }"
              ></span>
              <span
                class="swatch"
                :style="{ background: outline.styleGuide?.secondaryColor }"
              ></span>
            </div>
          </div>

          <div class="brief-meta">
            <p v-if="outline.summary" class="brief-summary">{{ outline.summary }}</p>
            <div class="meta-row">
              <span v-if="outline.targetAudience" class="meta-item">
                目标用户：{{ outline.targetAudience }}
              </span>
              <span v-if="outline.styleGuide?.tone" class="meta-item">
                风格：{{ outline.styleGuide.tone }}
              </span>
            </div>
            <div v-if="outline.coreFeatures?.length" class="feature-row">
              <span v-for="feature in outline.coreFeatures" :key="feature" class="feature">
                {{ feature }}
              </span>
            </div>
          </div>

          <div class="tabs">
            <button
              type="button"
              class="tab"
              :class="{ active: activeTabId === DIAGRAM_TAB }"
              @click="showDiagram"
            >
              ◈ 架构图
            </button>
            <button
              v-for="page in outline.pages"
              :key="page.id"
              type="button"
              class="tab"
              :class="{ active: page.id === activeTabId }"
              @click="selectPage(page)"
            >
              <span>{{ page.name }}</span>
              <span v-if="pageStates[page.id]?.loading" class="tab-loading"></span>
              <span v-else-if="pageStates[page.id]?.html" class="tab-done">✓</span>
            </button>
          </div>

          <div class="preview-body">
            <template v-if="activeTabId === DIAGRAM_TAB">
              <div class="preview-meta">
                <code>systemDiagram</code>
                <span>系统架构与核心业务流向（由模型生成）</span>
              </div>

              <div v-if="diagramError" class="state small error">
                <p>{{ diagramError }}</p>
                <button class="retry" type="button" @click="renderDiagram">重新渲染</button>
              </div>

              <div v-else-if="diagramSvg" class="diagram-scroll" v-html="diagramSvg"></div>

              <div v-else class="state small">
                <div class="spinner"></div>
                <p>正在渲染架构图…</p>
              </div>
            </template>

            <template v-else>
              <div v-if="activePage" class="preview-meta">
                <code>{{ activePage.path }}</code>
                <span>{{ activePage.purpose }}</span>
              </div>

              <div v-if="!activePage" class="state small">
                <p>没有可预览的页面。</p>
              </div>

              <div v-else-if="activeState?.loading" class="state small">
                <div class="spinner"></div>
                <p>正在生成「{{ activePage.name }}」的概念稿，通常需要 30～60 秒。</p>
              </div>

              <div v-else-if="activeState?.error" class="state small error">
                <p>{{ activeState.error }}</p>
                <button class="retry" type="button" @click="retryActivePage">重试</button>
              </div>

              <iframe
                v-else-if="activeState?.html"
                class="frame"
                :srcdoc="activeState.html"
                sandbox=""
                :title="activePage.name"
              ></iframe>

              <div v-else class="state small">
                <div class="state-icon">🖥️</div>
                <p>点击上方页面标签，生成「{{ activePage.name }}」的 HTML 概念稿。</p>
                <button class="retry" type="button" @click="ensurePageHtml(activePage)">
                  立即生成
                </button>
              </div>
            </template>
          </div>
        </template>
      </section>
    </main>

    <div v-if="settingsOpen" class="modal-mask" @click.self="settingsOpen = false">
      <div class="modal">
        <div class="modal-head">
          <h3>模型设置</h3>
          <span class="byok-badge">BYOK</span>
        </div>
        <p class="modal-hint">
          本工具不提供内置额度，请填写你自己的 OpenAI 兼容模型配置。API Key 仅保存在当前标签页
          （sessionStorage），随请求转发给你的模型服务；本工具服务端不保存密钥。
        </p>

        <div class="field">
          <label for="cfg-key">API Key</label>
          <div class="key-row">
            <input
              id="cfg-key"
              v-model="settingsDraft.apiKey"
              :type="settingsDraft.showKey ? 'text' : 'password'"
              placeholder="填入你自己的 API Key"
              autocomplete="off"
              spellcheck="false"
            />
            <button
              class="eye"
              type="button"
              @click="settingsDraft.showKey = !settingsDraft.showKey"
            >
              {{ settingsDraft.showKey ? '隐藏' : '显示' }}
            </button>
          </div>
        </div>

        <div class="field">
          <label for="cfg-url">Base URL</label>
          <input
            id="cfg-url"
            v-model="settingsDraft.baseUrl"
            placeholder="https://open.bigmodel.cn/api/paas/v4"
            spellcheck="false"
          />
        </div>

        <div class="field">
          <label for="cfg-model">模型名称</label>
          <input
            id="cfg-model"
            v-model="settingsDraft.modelName"
            placeholder="glm-4.7-flash"
            spellcheck="false"
          />
        </div>

        <p class="preset">
          智谱示例：Base URL 填 https://open.bigmodel.cn/api/paas/v4 ，模型填 glm-4.7-flash
        </p>
        <p v-if="settingsError" class="settings-error">{{ settingsError }}</p>

        <div class="modal-actions">
          <button class="clear-btn" type="button" @click="clearSettings">清除配置</button>
          <div class="right">
            <button class="ghost" type="button" @click="settingsOpen = false">取消</button>
            <button class="primary" type="button" @click="saveSettings">保存</button>
          </div>
        </div>
      </div>
    </div>
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

.top-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}

.stack {
  font-size: 12px;
  color: var(--muted);
}

.settings-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 12px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #fff;
  color: #374151;
  font-size: 12px;
  cursor: pointer;
}

.settings-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #d1d5db;
}

.dot.on {
  background: #10b981;
}

.layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 430px minmax(0, 1fr);
  gap: 16px;
  padding: 16px;
}

.panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 14px;
  min-height: 0;
}

.chat-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}

.panel-head-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
}

.step-badge {
  padding: 1px 8px;
  border-radius: 999px;
  background: #eff6ff;
  color: var(--primary);
  font-size: 11px;
  font-weight: 600;
}

.link-btn {
  border: none;
  background: none;
  color: var(--muted);
  font-size: 12px;
  cursor: pointer;
}

.link-btn:hover {
  color: var(--primary);
}

.chat-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-empty {
  margin: auto;
  max-width: 280px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.7;
}

.chat-empty-icon {
  font-size: 34px;
  margin-bottom: 8px;
}

.bubble-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.bubble-row.user {
  flex-direction: row-reverse;
}

.avatar {
  flex: none;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #eef2ff;
  color: var(--primary);
  font-size: 11px;
  font-weight: 600;
}

.bubble-row.user .avatar {
  background: var(--primary);
  color: #fff;
}

.bubble {
  max-width: 82%;
  padding: 9px 12px;
  border-radius: 12px;
  background: #f3f4f6;
  color: #1f2937;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.bubble-row.user .bubble {
  background: var(--primary);
  color: #fff;
}

.bubble.typing {
  display: flex;
  gap: 4px;
  padding: 14px 14px;
}

.bubble.typing span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #9ca3af;
  animation: blink 1.2s infinite ease-in-out;
}

.bubble.typing span:nth-child(2) {
  animation-delay: 0.2s;
}

.bubble.typing span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes blink {
  0%,
  80%,
  100% {
    opacity: 0.3;
    transform: translateY(0);
  }
  40% {
    opacity: 1;
    transform: translateY(-2px);
  }
}

.chat-error {
  margin: 0;
  padding: 6px 16px;
  color: #b91c1c;
  font-size: 12px;
  line-height: 1.5;
}

.composer {
  display: flex;
  gap: 8px;
  padding: 12px 16px 8px;
  border-top: 1px solid var(--border);
}

.composer textarea {
  flex: 1;
  height: 60px;
  resize: none;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  outline: none;
  font-size: 13px;
  line-height: 1.5;
}

.composer textarea:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.send-btn {
  align-self: flex-end;
  height: 36px;
  padding: 0 18px;
  border: none;
  border-radius: 10px;
  background: var(--primary);
  color: #fff;
  font-size: 14px;
  cursor: pointer;
}

.send-btn:disabled {
  background: #93a3b8;
  cursor: not-allowed;
}

.outline-btn {
  margin: 0 16px 16px;
  padding: 12px 16px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #2563eb, #4f46e5);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s;
}

.outline-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.outline-btn:disabled {
  background: #93a3b8;
  cursor: not-allowed;
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

.state.small {
  padding: 16px;
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

.state.error p {
  color: #b91c1c;
}

.state-icon {
  font-size: 40px;
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

.retry:hover {
  background: #eff6ff;
}

.brief-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 20px 8px;
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

.brief-meta {
  padding: 0 20px 10px;
  border-bottom: 1px solid var(--border);
}

.brief-summary {
  margin: 0 0 6px;
  font-size: 13px;
  line-height: 1.6;
  color: #4b5563;
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  font-size: 12px;
  color: var(--muted);
}

.feature-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.feature {
  padding: 2px 9px;
  border-radius: 999px;
  background: #eff6ff;
  color: var(--primary);
  font-size: 11px;
}

.tabs {
  display: flex;
  gap: 6px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
}

.tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #fff;
  color: #374151;
  font-size: 13px;
  white-space: nowrap;
  cursor: pointer;
}

.tab:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.tab.active {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
}

.tab-loading {
  width: 10px;
  height: 10px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  opacity: 0.8;
}

.tab-done {
  font-size: 11px;
  opacity: 0.9;
}

.preview-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 10px 16px 16px;
}

.preview-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 2px 8px;
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

.diagram-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: grid;
  place-items: center;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fff;
}

.diagram-scroll :deep(svg) {
  max-width: 100%;
  height: auto;
}

.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(17, 24, 39, 0.45);
}

.modal {
  width: 100%;
  max-width: 460px;
  padding: 22px;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 24px 60px rgba(17, 24, 39, 0.25);
}

.modal-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.modal-head h3 {
  margin: 0;
  font-size: 17px;
}

.byok-badge {
  padding: 1px 8px;
  border-radius: 999px;
  background: #ecfdf5;
  color: #047857;
  font-size: 11px;
  font-weight: 600;
}

.modal-hint {
  margin: 10px 0 16px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--muted);
}

.field {
  margin-bottom: 12px;
}

.field label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #374151;
}

.field input {
  width: 100%;
  height: 38px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 9px;
  outline: none;
  font-size: 13px;
}

.field input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.key-row {
  display: flex;
  gap: 8px;
}

.key-row input {
  flex: 1;
  min-width: 0;
}

.eye {
  flex: none;
  height: 38px;
  padding: 0 12px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: #f9fafb;
  color: #374151;
  font-size: 12px;
  cursor: pointer;
}

.preset {
  margin: 4px 0 0;
  font-size: 11px;
  line-height: 1.6;
  color: var(--muted);
}

.settings-error {
  margin: 10px 0 0;
  font-size: 12px;
  color: #b91c1c;
}

.modal-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 18px;
}

.modal-actions .right {
  display: flex;
  gap: 8px;
}

.clear-btn {
  border: none;
  background: none;
  color: #b91c1c;
  font-size: 12px;
  cursor: pointer;
}

.ghost,
.primary {
  height: 36px;
  padding: 0 18px;
  border-radius: 9px;
  font-size: 13px;
  cursor: pointer;
}

.ghost {
  border: 1px solid var(--border);
  background: #fff;
  color: #374151;
}

.primary {
  border: none;
  background: var(--primary);
  color: #fff;
}

@media (max-width: 980px) {
  .layout {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(360px, 46vh) minmax(0, 1fr);
  }

  .stack {
    display: none;
  }
}
</style>
