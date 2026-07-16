<template>
  <aside class="trace-panel">
    <div class="section-heading">
      <div><span class="eyebrow">EXECUTION TRACE</span><h2>执行轨迹</h2></div>
      <span :class="['status-badge', status]">{{ statusLabel }}</span>
    </div>
    <div class="metric-grid compact">
      <div><span>首 Token</span><strong>{{ formatMs(metrics.ttftMs) }}</strong></div>
      <div><span>端到端</span><strong>{{ formatMs(metrics.e2eMs) }}</strong></div>
      <div><span>模型调用</span><strong>{{ metrics.llmCalls ?? '-' }}</strong></div>
      <div><span>输入 Token</span><strong>{{ metrics.inputTokens ?? '-' }}</strong></div>
      <div><span>输出 Token</span><strong>{{ metrics.outputTokens ?? '-' }}</strong></div>
      <div><span>总 Token</span><strong>{{ metrics.totalTokens ?? '-' }}</strong></div>
      <div><span>降级次数</span><strong>{{ metrics.fallbacks ?? 0 }}</strong></div>
    </div>
    <div class="route-card" v-if="route.selectedAgent">
      <span>{{ route.intent || 'other' }}</span><strong>{{ route.selectedAgent }}</strong>
      <small v-if="route.plannedAgents?.length">计划：{{ route.plannedAgents.join(' → ') }}</small>
    </div>
    <ol class="timeline">
      <li v-for="item in events" :key="item.key" :class="item.status">
        <span class="timeline-dot"></span>
        <div><strong>{{ label(item) }}</strong><small>{{ detail(item) }}</small></div>
      </li>
    </ol>
    <section class="evidence-list" v-if="calls.length">
      <h3>模型调用明细</h3>
      <article v-for="call in calls" :key="`${call.sequence}-${call.started_at_epoch}`">
        <div><strong>#{{ call.sequence }} · {{ call.stage }}</strong><span>{{ call.latency_ms }} ms</span></div>
        <p>{{ call.provider }} / {{ call.model }} · in {{ call.input_tokens ?? '-' }} · out {{ call.output_tokens ?? '-' }}</p>
        <small v-if="call.provider_request_id">request: {{ call.provider_request_id }}</small>
        <small v-if="call.provider_response_id">response: {{ call.provider_response_id }}</small>
      </article>
    </section>
    <section class="evidence-list" v-if="evidence.length">
      <h3>检索证据</h3>
      <article v-for="(item, index) in evidence" :key="`${item.title}-${index}`">
        <div><strong>{{ item.title }}</strong><span>{{ item.score ?? '-' }}</span></div><p>{{ item.content }}</p>
      </article>
    </section>
  </aside>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ events: { type: Array, default: () => [] }, metrics: { type: Object, default: () => ({}) }, route: { type: Object, default: () => ({}) }, evidence: { type: Array, default: () => [] }, calls: { type: Array, default: () => [] }, status: { type: String, default: 'idle' } })
const statusLabel = computed(() => ({ idle: '等待请求', running: '执行中', ok: '已完成', error: '失败' }[props.status] || props.status))
function formatMs(value) { return value === null || value === undefined ? '-' : `${Math.round(value)} ms` }
function label(item) { if (item.type === 'agent') return `Agent · ${item.agent}`; if (item.type === 'fallback') return `降级 · ${item.from_agent} → ${item.to_agent}`; if (item.type === 'first_token') return '首 Token 到达'; return item.stage || item.type }
function detail(item) { if (item.type === 'fallback') return item.reason || '主 Agent 执行失败'; if (item.type === 'first_token') return formatMs(item.ttft_ms); if (item.latency_ms !== undefined) return formatMs(item.latency_ms); return item.status || '' }
</script>
