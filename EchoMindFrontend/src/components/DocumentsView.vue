<template>
  <section class="page-view">
    <div class="page-heading"><div><span class="eyebrow">DOCUMENT CENTER</span><h1>标准文稿中心</h1><p>管理文稿导入、知识库切片和证据检索。</p></div><div class="stat-card"><span>知识片段</span><strong>{{ knowledgeCount }}</strong></div></div>
    <div class="two-column-grid">
      <article class="panel-card">
        <div class="section-heading"><div><span class="eyebrow">INGESTION</span><h2>导入文稿</h2></div></div>
        <label class="field"><span>文稿标题</span><input v-model="title" placeholder="例如：SA2 AI Service Continuity Discussion" /></label>
        <label class="field"><span>文稿内容</span><textarea v-model="content" rows="12" placeholder="粘贴标准文稿、机制说明或 TDoc 摘要"></textarea></label>
        <div class="form-actions"><label class="file-button">选择 TXT / MD / JSON<input type="file" accept=".txt,.md,.json" @change="upload" /></label><button class="primary" :disabled="busy || !title.trim() || !content.trim()" @click="submit">加入知识库</button></div>
        <p v-if="status" class="status-message">{{ status }}</p>
      </article>
      <article class="panel-card">
        <div class="section-heading"><div><span class="eyebrow">EVIDENCE SEARCH</span><h2>检索验证</h2></div></div>
        <label class="field"><span>检索问题</span><textarea v-model="query" rows="4" placeholder="输入标准机制、TDoc 主题或 Gap 关键词"></textarea></label>
        <button class="primary" :disabled="busy || !query.trim()" @click="search">检索证据</button>
        <div class="document-results"><article v-for="(item, index) in results" :key="`${item.title}-${index}`"><header><strong>{{ item.title || '未命名文稿' }}</strong><span>{{ item.score ?? '-' }}</span></header><p>{{ item.content }}</p><small>片段 {{ item.chunk ?? '-' }}</small></article><div v-if="!results.length" class="empty-inline">暂无检索结果</div></div>
      </article>
    </div>
  </section>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { addKnowledge, requestKnowledgeStats, requestSearch, uploadKnowledge } from '../lib/backends'
const props = defineProps({ settings: { type: Object, required: true } })
const title = ref(''); const content = ref(''); const query = ref('AI service continuity under UE mobility'); const results = ref([]); const knowledgeCount = ref('-'); const busy = ref(false); const status = ref('')
onMounted(refreshStats)
async function refreshStats() { try { const data = await requestKnowledgeStats(props.settings); knowledgeCount.value = data.total_chunks ?? '-' } catch { knowledgeCount.value = '-' } }
async function submit() { busy.value = true; status.value = ''; try { const data = await addKnowledge(props.settings, [{ title: title.value.trim(), content: content.value.trim() }]); status.value = data.message; title.value = ''; content.value = ''; await refreshStats() } catch (error) { status.value = error.message } finally { busy.value = false } }
async function upload(event) { const file = event.target.files?.[0]; event.target.value = ''; if (!file) return; busy.value = true; try { const data = await uploadKnowledge(props.settings, file); status.value = data.message; await refreshStats() } catch (error) { status.value = error.message } finally { busy.value = false } }
async function search() { busy.value = true; try { const data = await requestSearch(props.settings, query.value, 8); results.value = data.results || [] } catch (error) { status.value = error.message } finally { busy.value = false } }
</script>
