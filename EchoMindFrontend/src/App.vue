<template>
  <main class="app-shell">
    <aside class="sidebar">
      <section class="brand">
        <div class="brand-mark">SP</div>
        <div>
          <h1>StandardPilot</h1>
          <p>通信标准研究智能工作台</p>
        </div>
      </section>

      <section class="panel connection-panel">
        <div class="panel-heading">
          <h2>工作区连接</h2>
          <span :class="['status-dot', healthOk ? 'online' : 'offline']"></span>
        </div>
        <label>
          <span>后端地址</span>
          <input v-model="settings.endpoint" @change="persist" placeholder="/api/python" />
        </label>
        <label>
          <span>研究者 ID</span>
          <input v-model="settings.userId" @change="persist" placeholder="researcher-001" />
        </label>
        <label>
          <span>会话 ID</span>
          <input v-model="settings.conversationId" @change="persist" placeholder="自动生成" />
        </label>
        <div class="actions">
          <button @click="checkHealth">检查连接</button>
          <button class="secondary" @click="loadStats">刷新状态</button>
        </div>
      </section>

      <section class="panel capability-panel">
        <div class="panel-heading">
          <h2>研究能力</h2>
          <span class="pill">Multi-Agent</span>
        </div>
        <button
          v-for="item in taskTemplates"
          :key="item.title"
          class="capability-item"
          @click="applyTemplate(item.prompt)"
        >
          <span class="capability-icon">{{ item.icon }}</span>
          <span>
            <strong>{{ item.title }}</strong>
            <small>{{ item.description }}</small>
          </span>
        </button>
      </section>

      <section class="panel status-panel">
        <div class="panel-heading">
          <h2>运行状态</h2>
          <span class="pill soft">{{ healthLabel }}</span>
        </div>
        <dl>
          <div><dt>服务状态</dt><dd :class="healthOk ? 'ok' : 'muted'">{{ healthLabel }}</dd></div>
          <div><dt>知识片段</dt><dd>{{ knowledgeCount }}</dd></div>
          <div><dt>当前会话</dt><dd class="truncate">{{ settings.conversationId || '未创建' }}</dd></div>
        </dl>
        <button class="text-button" @click="showDiagnostics = !showDiagnostics">
          {{ showDiagnostics ? '收起诊断信息' : '查看诊断信息' }}
        </button>
        <pre v-if="showDiagnostics && statusText">{{ statusText }}</pre>
      </section>
    </aside>

    <section class="workspace">
      <header class="workspace-header">
        <div>
          <span class="eyebrow">3GPP STANDARD RESEARCH</span>
          <h2>标准文稿分析工作台</h2>
          <p>围绕标准机制、TDoc、Gap、Proposal 与会议 Challenge 开展有证据的研究分析</p>
        </div>
        <div class="header-actions">
          <a :href="docsUrl" target="_blank" rel="noreferrer">API 文档</a>
          <a :href="metricsUrl" target="_blank" rel="noreferrer">Prometheus</a>
        </div>
      </header>

      <section class="research-layout">
        <section class="chat-panel">
          <div class="chat-heading">
            <div>
              <span class="eyebrow">RESEARCH COPILOT</span>
              <h3>标准研究对话</h3>
            </div>
            <button class="secondary compact" @click="startNewConversation">新建会话</button>
          </div>

          <div class="messages" ref="messageList">
            <div v-if="messages.length === 0" class="empty-state">
              <div class="empty-symbol">SP</div>
              <h3>从一个标准研究问题开始</h3>
              <p>可要求系统分析已有机制、总结 TDoc、识别标准化 Gap、生成 Proposal 草稿或准备会议 Challenge。</p>
              <div class="suggestion-grid">
                <button v-for="item in starterPrompts" :key="item" @click="applyTemplate(item)">{{ item }}</button>
              </div>
            </div>

            <article v-for="item in messages" :key="item.id" :class="['message', item.role]">
              <div class="message-meta">
                <span>{{ item.role === 'user' ? '研究者' : 'StandardPilot' }}</span>
                <small v-if="item.meta">{{ item.meta }}</small>
              </div>
              <p>{{ item.content }}</p>
            </article>
          </div>

          <form class="composer" @submit.prevent="sendMessage">
            <textarea
              v-model="draft"
              rows="4"
              placeholder="输入研究问题，例如：现有 5GC 机制是否覆盖 UE 移动场景下的 AI 推理服务连续性？请区分已有证据、合理推断和待确认内容。"
              @keydown.ctrl.enter.prevent="sendMessage"
            ></textarea>
            <div class="composer-footer">
              <span>Ctrl + Enter 发送 · 回答将自动显示意图、Agent 与 RAG 状态</span>
              <button :disabled="busy || !draft.trim()">{{ busy ? '分析中…' : '发送分析' }}</button>
            </div>
          </form>
        </section>

        <aside class="evidence-panel">
          <div class="panel-heading">
            <div>
              <span class="eyebrow">EVIDENCE RETRIEVAL</span>
              <h3>标准证据检索</h3>
            </div>
            <span class="pill soft">RAG</span>
          </div>
          <p class="panel-description">独立检索知识库，核对标准机制、文稿结论与研究证据。</p>
          <div class="search-box">
            <textarea v-model="searchQuery" rows="3" placeholder="输入标准机制、TDoc 主题或 Gap 关键词"></textarea>
            <button @click="searchKnowledge" :disabled="busy || !searchQuery.trim()">检索证据</button>
          </div>
          <div v-if="searchResults.length === 0" class="empty-evidence">暂无检索结果</div>
          <div class="result-list">
            <article v-for="(item, index) in searchResults" :key="`${item.title}-${index}`" class="result-item">
              <div class="result-title">
                <strong>{{ item.title || '未命名文稿' }}</strong>
                <span>score {{ item.score ?? '-' }}</span>
              </div>
              <p>{{ item.content }}</p>
              <small v-if="item.chunk !== undefined">片段 {{ item.chunk }}</small>
            </article>
          </div>
        </aside>
      </section>

      <section class="knowledge-panel">
        <div class="knowledge-heading">
          <div>
            <span class="eyebrow">KNOWLEDGE INGESTION</span>
            <h3>标准文稿入库</h3>
            <p>当前后端支持 TXT、Markdown 与 JSON 文档。导入后可直接用于对话和证据检索。</p>
          </div>
          <label class="file-button">
            上传标准文稿
            <input type="file" accept=".txt,.md,.json" @change="handleUpload" />
          </label>
        </div>
        <div class="knowledge-form">
          <label>
            <span>文稿标题</span>
            <input v-model="docTitle" placeholder="例如：SA2 AI Service Continuity Discussion" />
          </label>
          <label class="content-field">
            <span>文稿内容</span>
            <textarea v-model="docContent" rows="5" placeholder="粘贴标准文稿、机制说明或 TDoc 摘要内容"></textarea>
          </label>
          <button @click="submitKnowledge" :disabled="busy || !docTitle.trim() || !docContent.trim()">加入知识库</button>
        </div>
      </section>
    </section>
  </main>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import {
  addKnowledge,
  backendMeta,
  createInitialSettings,
  requestChat,
  requestHealth,
  requestKnowledgeStats,
  requestMonitor,
  requestSearch,
  saveSettings,
  uploadKnowledge
} from './lib/backends'

const settings = reactive(createInitialSettings())
const messages = ref([])
const draft = ref('')
const busy = ref(false)
const healthOk = ref(false)
const healthLabel = ref('未检查')
const statusText = ref('')
const knowledgeCount = ref('-')
const searchQuery = ref('AI service continuity under UE mobility')
const searchResults = ref([])
const docTitle = ref('')
const docContent = ref('')
const messageList = ref(null)
const showDiagnostics = ref(false)

const taskTemplates = [
  { icon: 'QA', title: '标准机制问答', description: '查询 TS/TR 与 5GC 机制', prompt: '请说明现有 5GC 中与该问题相关的标准机制，并区分已有证据、合理推断和待确认内容。' },
  { icon: 'TD', title: 'TDoc 文稿摘要', description: '提取背景、问题与方案', prompt: '请总结这篇 TDoc，并提取 Background、Problem、Proposed Solution、Impacted Entities、Open Issues 和 Potential Controversies。' },
  { icon: 'GP', title: '标准化 Gap 分析', description: '判断覆盖范围与标准价值', prompt: '请分析该议题是否存在标准化 Gap，说明已有机制、覆盖边界、潜在空白、标准化价值和推进风险。' },
  { icon: 'PR', title: 'Proposal 草稿', description: '生成规范化 TDoc 初稿', prompt: '请基于现有证据生成一份 TDoc 草稿，包含 Title、Background、Discussion、Proposal 和 Conclusion。' },
  { icon: 'CH', title: '会议 Challenge', description: '准备审查问题与答辩', prompt: '请从 evidence、WG scope、实现问题、新增 NF 风险和信令开销角度生成会议 challenge，并给出 suggested answer。' }
]

const starterPrompts = [
  'NWDAF 在现有 5GC 中可以为 AI 推理服务提供哪些分析能力？',
  'UE 移动时执行位置重选是标准问题还是实现问题？',
  '请给出一份 SA2 Proposal 的审查清单。'
]

const currentBackend = computed(() => backendMeta(settings))
const docsUrl = computed(() => `${currentBackend.value.baseUrl}/docs`)
const metricsUrl = computed(() => `${currentBackend.value.baseUrl}/metrics`)

watch(() => settings.conversationId, persist)

onMounted(() => {
  checkHealth()
  loadStats()
})

function persist() {
  saveSettings(settings)
}

function applyTemplate(prompt) {
  draft.value = prompt
}

function startNewConversation() {
  settings.conversationId = ''
  messages.value = []
  searchResults.value = []
  persist()
}

async function sendMessage() {
  const content = draft.value.trim()
  if (!content || busy.value) return
  messages.value.push({ id: crypto.randomUUID(), role: 'user', content })
  draft.value = ''
  busy.value = true
  try {
    const response = await requestChat(settings, content)
    if (response.conversationId && !settings.conversationId) {
      settings.conversationId = response.conversationId
      persist()
    }
    const meta = [
      response.intent,
      response.agentType,
      response.knowledgeUsed ? 'RAG' : '',
      response.escalated ? '需人工确认' : '',
      response.latencyMs ? `${Math.round(response.latencyMs)} ms` : ''
    ].filter(Boolean).join(' · ')
    messages.value.push({ id: crypto.randomUUID(), role: 'assistant', content: response.response, meta })
  } catch (error) {
    messages.value.push({ id: crypto.randomUUID(), role: 'assistant', content: error.message, meta: '请求失败' })
  } finally {
    busy.value = false
    await nextTick()
    messageList.value?.scrollTo({ top: messageList.value.scrollHeight, behavior: 'smooth' })
  }
}

async function checkHealth() {
  try {
    const data = await requestHealth(settings)
    healthOk.value = data.status === 'ok'
    healthLabel.value = data.status === 'ok' ? '运行正常' : (data.status || '已连接')
    statusText.value = JSON.stringify(data, null, 2)
  } catch (error) {
    healthOk.value = false
    healthLabel.value = '连接失败'
    statusText.value = error.message
  }
}

async function loadStats() {
  const [stats, monitor] = await Promise.allSettled([
    requestKnowledgeStats(settings),
    requestMonitor(settings)
  ])
  if (stats.status === 'fulfilled') knowledgeCount.value = stats.value.total_chunks ?? '-'
  if (monitor.status === 'fulfilled') statusText.value = JSON.stringify(monitor.value, null, 2)
}

async function searchKnowledge() {
  busy.value = true
  try {
    const data = await requestSearch(settings, searchQuery.value, 5)
    searchResults.value = data.results || []
  } catch (error) {
    statusText.value = error.message
    showDiagnostics.value = true
  } finally {
    busy.value = false
  }
}

async function submitKnowledge() {
  busy.value = true
  try {
    const data = await addKnowledge(settings, [{ title: docTitle.value.trim(), content: docContent.value.trim() }])
    statusText.value = JSON.stringify(data, null, 2)
    docTitle.value = ''
    docContent.value = ''
    await loadStats()
  } catch (error) {
    statusText.value = error.message
    showDiagnostics.value = true
  } finally {
    busy.value = false
  }
}

async function handleUpload(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  busy.value = true
  try {
    const data = await uploadKnowledge(settings, file)
    statusText.value = JSON.stringify(data, null, 2)
    await loadStats()
  } catch (error) {
    statusText.value = error.message
    showDiagnostics.value = true
  } finally {
    busy.value = false
  }
}
</script>
