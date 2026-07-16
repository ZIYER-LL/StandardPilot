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
      <div class="section-heading chat-title"><div><span class="eyebrow">ADAPTIVE RESEARCH COPILOT</span><h2>{{ currentTitle }}</h2></div><span class="stream-indicator"><i :class="traceStatus"></i>{{ traceStatus === 'running' ? '自适应执行中' : '就绪' }}</span></div>
      <div class="message-list" ref="messageList">
        <div v-if="messages.length === 0" class="empty-state">
          <span>SP</span><h3>从一个标准研究问题开始</h3><p>系统会自主选择零模型工具、RAG、专业 Agent 或 Manager 模式，并展示决策原因。</p>
          <div class="prompt-grid"><button v-for="prompt in prompts" :key="prompt" @click="draft = prompt">{{ prompt }}</button></div>
        </div>
        <article v-for="message in messages" :key="message.id" :class="['message-card', message.role]">
          <header><strong>{{ message.role === 'user' ? '研究者' : 'StandardPilot' }}</strong><small v-if="message.meta">{{ message.meta }}</small></header>
          <div class="message-content">{{ message.content }}<span v-if="message.streaming" class="cursor"></span></div>
        </article>
      </div>
      <form class="composer" @submit.prevent="send">
        <textarea v-model="draft" rows="4" placeholder="输入标准研究问题，Ctrl + Enter 发送" @keydown.ctrl.enter.prevent="send"></textarea>
        <div><span>回答将保留路由决策、检索深度、模型降级与精确用量</span><button v-if="busy" type="button" class="danger" @click="stop">停止</button><button v-else class="primary" :disabled="!draft.trim()">发送分析</button></div>
      </form>
    </main>

    <TracePanel :events="traceEvents" :metrics="traceMetrics" :route="route" :evidence="evidence" :calls="llmCalls" :status="traceStatus" />
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import TracePanel from './TracePanel.vue'
import { getConversation, listConversations } from '../lib/backends'
import { streamAdaptiveChat } from '../lib/adaptive'

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
const llmCalls = ref([])
const traceStatus = ref('idle')
let controller = null
let pendingText = ''
let paintFrame = 0
const prompts = ['知识库目前有多少个文档片段？', 'NWDAF 在现有 5GC 中可以为 AI 推理服务提供哪些分析能力？', '总结相关文稿、判断标准化 Gap，并给出提案建议。']
const currentConversationId = computed(() => props.settings.conversationId || '')
const currentTitle = computed(() => conversations.value.find((item) => item.conv_id === currentConversationId.value)?.title || '标准文稿分析工作台')

onMounted(async () => { await refreshConversations(); if (currentConversationId.value) await openConversation(currentConversationId.value) })

async function refreshConversations() { try { const data = await listConversations(props.settings); conversations.value = data.conversations || [] } catch { conversations.value = [] } }
function startConversation() { emit('conversation-change', ''); messages.value = []; resetTrace() }
async function openConversation(convId) {
  if (busy.value) return
  emit('conversation-change', convId)
  const data = await getConversation(props.settings, convId)
  messages.value = (data.messages || []).map((item) => reactive({ id: crypto.randomUUID(), role: item.role, content: item.content, meta: item.meta ? [item.meta.intent, item.meta.agent_type, formatMs(item.meta.ttft_ms), formatMs(item.meta.e2e_latency_ms)].filter(Boolean).join(' · ') : '' }))
  const latest = data.traces?.[data.traces.length - 1]
  if (latest) applyStoredTrace(latest)
  await scrollBottom()
}

function scheduleTokenPaint(assistant) {
  if (paintFrame) return
  paintFrame = requestAnimationFrame(async () => {
    paintFrame = 0
    if (pendingText) { assistant.content += pendingText; pendingText = ''; await scrollBottom() }
  })
}
function flushTokens(assistant) {
  if (paintFrame) cancelAnimationFrame(paintFrame)
  paintFrame = 0
  if (pendingText) { assistant.content += pendingText; pendingText = '' }
}

async function send() {
  const content = draft.value.trim()
  if (!content || busy.value) return
  draft.value = ''; busy.value = true; resetTrace(); traceStatus.value = 'running'
  messages.value.push(reactive({ id: crypto.randomUUID(), role: 'user', content }))
  const assistant = reactive({ id: crypto.randomUUID(), role: 'assistant', content: '', meta: '', streaming: true })
  messages.value.push(assistant)
  controller = new AbortController()
  await scrollBottom()
  try {
    await streamAdaptiveChat(props.settings, content, { onEvent(event) {
      if (event.type === 'meta') { if (!currentConversationId.value) emit('conversation-change', event.conv_id) }
      else if (event.type === 'delta') { pendingText += event.content || ''; scheduleTokenPaint(assistant) }
      else if (event.type === 'first_token') { traceMetrics.value = { ...traceMetrics.value, ttftMs: event.ttft_ms }; upsertTraceEvent({ ...event, status: 'completed' }) }
      else if (event.type === 'decision') {
        upsertTraceEvent({ ...event, type: 'stage', stage: event.node, status: 'completed' })
        if (event.node === 'adaptive_router') route.value = { intent: event.task_type, selectedAgent: event.mode, plannedAgents: event.specialist ? [event.specialist] : [], reasonCodes: event.reason_codes, profile: event.response_profile }
        if (event.node === 'fast_gate' && event.matched) route.value = { intent: 'deterministic', selectedAgent: `direct:${event.action}`, plannedAgents: [], reasonCodes: [event.reason_code], profile: 'brief' }
      }
      else if (event.type === 'retrieval') { evidence.value = event.evidence || []; upsertTraceEvent({ ...event, type: 'stage', stage: `retrieval.${event.decision}`, status: 'completed' }) }
      else if (event.type === 'done') {
        flushTokens(assistant); traceStatus.value = 'ok'; llmCalls.value = event.llm_calls || []
        traceMetrics.value = { ttftMs: event.ttft_ms, e2eMs: event.e2e_latency_ms, llmCalls: event.llm_call_count, inputTokens: event.input_tokens, outputTokens: event.output_tokens, totalTokens: event.total_tokens, fallbacks: event.fallback_count || 0 }
        const decision = event.route_decision
        assistant.meta = [decision?.mode || (event.fast_gate?.matched ? `direct:${event.fast_gate.action}` : ''), decision?.response_profile, `TTFT ${formatMs(event.ttft_ms)}`, `E2E ${formatMs(event.e2e_latency_ms)}`, `${event.llm_call_count || 0} 次模型调用`].filter(Boolean).join(' · ')
      }
    } }, controller.signal)
  } catch (error) {
    flushTokens(assistant)
    if (error.name !== 'AbortError') { assistant.content ||= error.message; assistant.meta = '请求失败'; traceStatus.value = 'error' }
    else { assistant.meta = '已停止'; traceStatus.value = 'idle' }
  } finally {
    flushTokens(assistant); assistant.streaming = false; busy.value = false; controller = null; await refreshConversations(); await scrollBottom()
  }
}

function stop() { controller?.abort() }
function resetTrace() { traceEvents.value = []; traceMetrics.value = {}; route.value = {}; evidence.value = []; llmCalls.value = []; traceStatus.value = 'idle'; pendingText = ''; if (paintFrame) cancelAnimationFrame(paintFrame); paintFrame = 0 }
function upsertTraceEvent(event) { const key = event.span_id || `${event.stage || event.type}-${traceEvents.value.length}`; traceEvents.value.push({ ...event, key }) }
function applyStoredTrace(trace) { traceStatus.value = trace.status === 'ok' ? 'ok' : trace.status; traceEvents.value = [...(trace.decisions || []), ...(trace.spans || [])].map((item, index) => ({ ...item, type: 'stage', stage: item.node || item.name || item.type, key: item.span_id || `stored-${index}` })); traceMetrics.value = { ttftMs: trace.ttft_ms, e2eMs: trace.e2e_latency_ms, llmCalls: trace.llm_call_count, inputTokens: trace.input_tokens, outputTokens: trace.output_tokens, totalTokens: trace.total_tokens, fallbacks: trace.fallback_count }; llmCalls.value = trace.llm_calls || []; const decision = trace.route_decision || {}; route.value = { intent: decision.task_type, selectedAgent: decision.mode || trace.selected_agent, plannedAgents: decision.specialist ? [decision.specialist] : [], reasonCodes: decision.reason_codes, profile: decision.response_profile }; evidence.value = trace.evidence || [] }
async function scrollBottom() { await nextTick(); messageList.value?.scrollTo({ top: messageList.value.scrollHeight, behavior: 'auto' }) }
function formatMs(value) { return value === null || value === undefined ? '' : `${Math.round(value)} ms` }
</script>
