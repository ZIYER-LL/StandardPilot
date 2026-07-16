<template>
  <section class="page-view">
    <div class="page-heading"><div><span class="eyebrow">OBSERVABILITY</span><h1>运行观测中心</h1><p>查看真实首 Token、端到端时延、模型用量、Agent 路由和失败降级。</p></div><button @click="load">刷新数据</button></div>
    <div class="metric-grid">
      <article><span>样本数</span><strong>{{ summary.sample_size ?? 0 }}</strong></article>
      <article><span>成功率</span><strong>{{ percent(summary.success_rate) }}</strong></article>
      <article><span>模型调用</span><strong>{{ summary.total_llm_calls ?? 0 }}</strong></article>
      <article><span>输入 Token</span><strong>{{ summary.total_input_tokens ?? 0 }}</strong></article>
      <article><span>输出 Token</span><strong>{{ summary.total_output_tokens ?? 0 }}</strong></article>
      <article><span>TTFT P50</span><strong>{{ ms(summary.ttft_ms?.p50) }}</strong></article>
      <article><span>TTFT P95</span><strong>{{ ms(summary.ttft_ms?.p95) }}</strong></article>
      <article><span>E2E P95</span><strong>{{ ms(summary.e2e_latency_ms?.p95) }}</strong></article>
    </div>
    <div class="two-column-grid observability-grid">
      <article class="panel-card"><div class="section-heading"><div><span class="eyebrow">AGENT DISTRIBUTION</span><h2>Agent 调用分布</h2></div></div><div class="agent-bars"><div v-for="item in agentRows" :key="item.name"><span>{{ item.name }}</span><div><i :style="{ width: `${item.percent}%` }"></i></div><strong>{{ item.count }}</strong></div><div v-if="!agentRows.length" class="empty-inline">暂无数据</div></div></article>
      <article class="panel-card"><div class="section-heading"><div><span class="eyebrow">LATENCY</span><h2>时延摘要</h2></div></div><dl class="latency-list"><div><dt>TTFT 平均</dt><dd>{{ ms(summary.ttft_ms?.avg) }}</dd></div><div><dt>TTFT P50</dt><dd>{{ ms(summary.ttft_ms?.p50) }}</dd></div><div><dt>TTFT P95</dt><dd>{{ ms(summary.ttft_ms?.p95) }}</dd></div><div><dt>E2E 平均</dt><dd>{{ ms(summary.e2e_latency_ms?.avg) }}</dd></div><div><dt>E2E P50</dt><dd>{{ ms(summary.e2e_latency_ms?.p50) }}</dd></div><div><dt>E2E P95</dt><dd>{{ ms(summary.e2e_latency_ms?.p95) }}</dd></div></dl></article>
    </div>
    <article class="panel-card trace-table-card"><div class="section-heading"><div><span class="eyebrow">RECENT TRACES</span><h2>最近请求</h2></div></div><div class="trace-table"><div class="trace-row header"><span>状态</span><span>问题</span><span>Agent</span><span>TTFT</span><span>E2E</span><span>调用</span></div><button v-for="trace in traces" :key="trace.trace_id" class="trace-row" @click="selected = trace"><span :class="['trace-status', trace.status]">{{ trace.status }}</span><span class="trace-question">{{ trace.question }}</span><span>{{ trace.selected_agent || '-' }}</span><span>{{ ms(trace.ttft_ms) }}</span><span>{{ ms(trace.e2e_latency_ms) }}</span><span>{{ trace.llm_call_count ?? '-' }}</span></button></div></article>
    <article v-if="selected" class="panel-card trace-detail">
      <div class="section-heading"><div><span class="eyebrow">TRACE DETAIL</span><h2>{{ selected.trace_id }}</h2></div><button @click="selected = null">关闭</button></div>
      <div class="trace-detail-grid"><div><span>Intent</span><strong>{{ selected.intent || '-' }}</strong></div><div><span>Agent</span><strong>{{ selected.selected_agent || '-' }}</strong></div><div><span>模型调用</span><strong>{{ selected.llm_call_count ?? 0 }}</strong></div><div><span>Token</span><strong>{{ selected.input_tokens ?? 0 }} in / {{ selected.output_tokens ?? 0 }} out</strong></div></div>
      <ol class="timeline detailed"><li v-for="span in selected.spans || []" :key="span.span_id" :class="span.status"><span class="timeline-dot"></span><div><strong>{{ span.name }}</strong><small>{{ ms(span.latency_ms) }} · {{ span.status }}</small></div></li></ol>
      <div class="trace-table" v-if="selected.llm_calls?.length"><div class="trace-row header"><span>#</span><span>阶段</span><span>模型</span><span>输入</span><span>输出</span><span>请求 ID</span></div><div v-for="call in selected.llm_calls" :key="`${call.sequence}-${call.started_at_epoch}`" class="trace-row"><span>{{ call.sequence }}</span><span>{{ call.stage }}</span><span>{{ call.model }}</span><span>{{ call.input_tokens ?? '-' }}</span><span>{{ call.output_tokens ?? '-' }}</span><span class="trace-question">{{ call.provider_request_id || call.provider_response_id || '-' }}</span></div></div>
    </article>
  </section>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { listTraces, requestObservabilitySummary } from '../lib/backends'
const props = defineProps({ settings: { type: Object, required: true } })
const summary = ref({}); const traces = ref([]); const selected = ref(null)
const agentRows = computed(() => { const entries = Object.entries(summary.value.agent_counts || {}); const total = entries.reduce((sum, [, count]) => sum + count, 0); return entries.map(([name, count]) => ({ name, count, percent: total ? Math.round((count / total) * 100) : 0 })) })
onMounted(load)
async function load() { const [summaryData, traceData] = await Promise.all([requestObservabilitySummary(props.settings, 200), listTraces(props.settings, { limit: 100 })]); summary.value = summaryData; traces.value = traceData.traces || []; if (selected.value) selected.value = traces.value.find((item) => item.trace_id === selected.value.trace_id) || null }
function ms(value) { return value === null || value === undefined ? '-' : `${Math.round(value)} ms` }
function percent(value) { return `${Math.round(Number(value || 0) * 100)}%` }
</script>
