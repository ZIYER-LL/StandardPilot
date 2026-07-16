<template>
  <section class="home-view">
    <div class="hero-card">
      <span class="eyebrow">3GPP RESEARCH OPERATING SYSTEM</span>
      <h1>StandardPilot</h1>
      <p class="hero-copy">面向通信标准研究的智能工作台，把文稿证据、Agent 执行链路与研究结论放在同一条可追踪流程中。</p>
      <div class="hero-actions">
        <button class="primary" @click="$emit('navigate', 'workspace')">进入分析工作台</button>
        <button @click="$emit('navigate', 'documents')">导入标准文稿</button>
        <button @click="$emit('navigate', 'observability')">查看运行观测</button>
      </div>
    </div>

    <div class="feature-grid">
      <article>
        <span>01</span>
        <h3>有证据的研究分析</h3>
        <p>围绕 3GPP 机制、TDoc、Gap、Proposal 和会议 Challenge 组织回答，并保留检索证据。</p>
      </article>
      <article>
        <span>02</span>
        <h3>可解释的 Agent 链路</h3>
        <p>每轮请求展示意图识别、RAG、路由、Agent、降级和记忆写入等阶段。</p>
      </article>
      <article>
        <span>03</span>
        <h3>真实的时延指标</h3>
        <p>通过流式输出记录首 Token、生成时延和端到端时延，而不是只展示完整响应耗时。</p>
      </article>
    </div>
  </section>
</template>

<script setup>
defineEmits(['navigate'])
</script>
