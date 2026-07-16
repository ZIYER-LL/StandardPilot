<template>
  <section class="workspace-view">
    <aside class="conversation-sidebar">
      <div class="section-heading"><div><span class="eyebrow">CONVERSATIONS</span><h2>会话</h2></div><button class="icon-button" @click="startConversation">＋</button></div>
      <button class="new-conversation" @click="startConversation">新建研究会话</button>
      <div class="conversation-list">
        <button v-for="item in conversations" :key="item.conv_id" :class="['conversation-item', { active: item.conv_id === currentConversationId }]" @click="openConversation(item.conv_id)">
          <strong>{{ item.title || '未命名会话' }}</strong><span>{{ item.last_message || '暂无消息' }}</span><small>{{ item.message_count || 0 }} 条消息</small>
        </button>
      </div>
    </aside>

    <main class="chat-workspace">
      <div class="section-heading chat-title"><div><span class="eyebrow">RESEARCH COPILOT</span><h2>{{ currentTitle }}</h2></div><span class="stream-indicator"><i :class="traceStatus"></i>{{ traceStatus === 'running' ? '实时生成' : '就绪' }}</span></div>
      <div class="message-list" ref="messageList">
        <div v-if="messages.length === 0" class="empty-state">
          <span>SP</span><h3>从一个标准研究问题开始</h3><p>系统会同步展示 RAG、意图识别、Agent 路由、首 Token 和完整执行轨迹。</p>
          <div class="prompt-grid"><button v-for="prompt in prompts" :key="prompt" @click="draft = prompt">{{ prompt }}</button></div>
        </div>
        <article v-for="message in messages" :key="message.id" :class="['message-card', message.role]">
          <header><strong>{{ message.role === 'user' ? '研究者' : 'StandardPilot' }}</strong><small v-if="message.meta">{{ message.meta }}</small></header>
          <div class="message-content">{{ message.content }}<span v-if="message.streaming" class="cursor"></span></div>
        </article>
      </div>
      <form class="composer" @submit.prevent="send">
        <textarea v-model="draft" rows="4" placeholder="输入标准研究问题，Ctrl + Enter 发送" @keydown.ctrl.enter.prevent="send"></textarea>
        <div><span>回答将保留证据、Agent 链路与性能数据</span><button v-if="busy" type="button" class="danger" @click="stop">停止</button><button v-else class="primary" :disabled="!draft.trim()">发送分析</button></div>
      </form>
    </main>

    <TracePanel :events="traceEvents" :metrics="traceMetrics" :route="route" :evidence="evidence" :status="traceStatus" />
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import TracePanel from './TracePanel.vue'
import { getConversation, listConversations, streamChat } from '../lib/backends'

const props = defineProps({ settings: { type: Object, required: true } })
const emit = defineEmits(['conversation-change'])
const conversations = ref([])
const messages = ref([])
const draft = ref('')
const busy = ref(false)
const messageList = ref(null)
const traceEvents = ref([])
const traceMetrics = ref({})
const route = ref({})
const evidence = ref([])
const traceStatus = ref('idle')
let controller = null
const prompts = ['NWDAF 在现有 5GC 中可以为 AI 推理服务提供哪些分析能力？', 'UE 移动时执行位置重选是标准问题还是实现问题？', '请分析该议题是否存在标准化 Gap，并区分证据、推断和待确认内容。']
const currentConversationId = computed(() => props.settings.conversationId || '')
const currentTitle = computed(() => conversations.value.find((item) => item.conv_id === currentConversationId.value)?.title || '标准文稿分析工作台')

onMounted(async () => { await refreshConversations(); if (currentConversationId.value) await openConversation(currentConversationId.value) })

async function refreshConversations() { try { const data = await listConversations(props.settings); conversations.value = data.conversations || [] } catch { conversations.value = [] } }
function startConversation() { emit('conversation-change', ''); messages.value = []; resetTrace() }
async function openConversation(convId) {
  if (busy.value) return
  emit('conversation-change', convId)
  const data = await getConversation(props.settings, convId)
  messages.value = (data.messages || []).map((item) => ({ id: crypto.randomUUID(), role: item.role, content: item.content, meta: item.meta ? [item.meta.intent, item.meta.agent_type, formatMs(item.meta.ttft_ms), formatMs(item.meta.e2e_latency_ms)].filter(Boolean).join(' · ') : '' }))
  const latest = data.traces?.[data.traces.length - 1]
  if (latest) applyStoredTrace(latest)
  await scrollBottom()
}

async function send() {
  const content = draft.value.trim()
  if (!content || busy.value) return
  draft.value = ''; busy.value = true; resetTrace(); traceStatus.value = 'running'
  messages.value.push({ id: crypto.randomUUID(), role: 'user', content })
  const assistant = { id: crypto.randomUUID(), role: 'assistant', content: '', meta: '', streaming: true }
  messages.value.push(assistant)
  controller = new AbortController()
  await scrollBottom()
  try {
    await streamChat(props.settings, content, { onEvent(event) {
      if (event.type === 'meta') { if (!currentConversationId.value) emit('conversation-change', event.conv_id) }
      else if (event.type === 'delta') { assistant.content += event.content || ''; scrollBottom() }
      else if (event.type === 'stage') { upsertTraceEvent(event); if (event.evidence) evidence.value = event.evidence }
      else if (['agent', 'fallback', 'first_token'].includes(event.type)) { upsertTraceEvent(event); if (event.type === 'first_token') traceMetrics.value.ttftMs = event.ttft_ms }
      else if (event.type === 'route') { route.value = { intent: event.intent, selectedAgent: event.selected_agent, plannedAgents: event.planned_agents }; upsertTraceEvent({ ...event, type: 'stage', stage: 'agent.route', status: 'completed' }) }
      else if (event.type === 'done') {
        traceStatus.value = 'ok'
        traceMetrics.value = { ttftMs: event.ttft_ms, e2eMs: event.e2e_latency_ms, generationMs: event.generation_ms, llmCalls: event.llm_call_count_estimate, fallbacks: event.fallback_count }
        assistant.meta = [event.intent, event.agent_type, event.knowledge_used ? 'RAG' : '', `TTFT ${formatMs(event.ttft_ms)}`, `E2E ${formatMs(event.e2e_latency_ms)}`].filter(Boolean).join(' · ')
      }
    } }, controller.signal)
  } catch (error) {
    if (error.name !== 'AbortError') { assistant.content ||= error.message; assistant.meta = '请求失败'; traceStatus.value = 'error' }
    else { assistant.meta = '已停止'; traceStatus.value = 'idle' }
  } finally {
    assistant.streaming = false; busy.value = false; controller = null; await refreshConversations(); await scrollBottom()
  }
}

function stop() { controller?.abort() }
function resetTrace() { traceEvents.value = []; traceMetrics.value = {}; route.value = {}; evidence.value = []; traceStatus.value = 'idle' }
function upsertTraceEvent(event) { const key = event.span_id || `${event.type}-${event.stage || event.agent || traceEvents.value.length}`; const index = traceEvents.value.findIndex((item) => item.key === key); const value = { ...event, key }; if (index >= 0) traceEvents.value[index] = value; else traceEvents.value.push(value) }
function applyStoredTrace(trace) { traceStatus.value = trace.status === 'ok' ? 'ok' : trace.status; traceEvents.value = (trace.spans || []).map((span) => ({ ...span, type: 'stage', stage: span.name, key: span.span_id })); traceMetrics.value = { ttftMs: trace.ttft_ms, e2eMs: trace.e2e_latency_ms, generationMs: trace.generation_ms, llmCalls: trace.llm_call_count_estimate, fallbacks: trace.fallback_count }; route.value = { intent: trace.intent, selectedAgent: trace.selected_agent, plannedAgents: trace.planned_agents }; evidence.value = trace.evidence || [] }
async function scrollBottom() { await nextTick(); messageList.value?.scrollTo({ top: messageList.value.scrollHeight, behavior: 'smooth' }) }
function formatMs(value) { return value === null || value === undefined ? '' : `${Math.round(value)} ms` }
</script>
