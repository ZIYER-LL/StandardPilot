<template>
  <div class="application-shell">
    <header class="topbar">
      <button class="brand-button" @click="navigate('home')">
        <span class="brand-mark">SP</span>
        <span><strong>StandardPilot</strong><small>通信标准研究工作台</small></span>
      </button>

      <nav>
        <button v-for="item in navigation" :key="item.id" :class="{ active: page === item.id }" @click="navigate(item.id)">
          {{ item.label }}
        </button>
      </nav>

      <div class="topbar-actions">
        <span :class="['connection-state', healthOk ? 'online' : 'offline']">{{ healthOk ? '服务在线' : '服务离线' }}</span>
        <button class="icon-button" title="系统设置" @click="showSettings = true">⚙</button>
      </div>
    </header>

    <main class="application-content">
      <HomeView v-if="page === 'home'" @navigate="navigate" />
      <WorkspaceView v-else-if="page === 'workspace'" :settings="settings" @conversation-change="changeConversation" />
      <DocumentsView v-else-if="page === 'documents'" :settings="settings" />
      <ObservabilityView v-else-if="page === 'observability'" :settings="settings" />
    </main>

    <div v-if="showSettings" class="modal-backdrop" @click.self="showSettings = false">
      <section class="settings-modal">
        <div class="section-heading"><div><span class="eyebrow">DEVELOPER SETTINGS</span><h2>系统连接</h2></div><button class="icon-button" @click="showSettings = false">×</button></div>
        <label class="field"><span>后端地址</span><input v-model="settings.endpoint" /></label>
        <label class="field"><span>研究者 ID</span><input v-model="settings.userId" /></label>
        <p>会话 ID 由工作台自动管理，不再作为普通用户的主界面字段。</p>
        <div class="form-actions"><button @click="checkHealth">测试连接</button><button class="primary" @click="saveAndClose">保存设置</button></div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import DocumentsView from './components/DocumentsView.vue'
import HomeView from './components/HomeView.vue'
import ObservabilityView from './components/ObservabilityView.vue'
import WorkspaceView from './components/WorkspaceView.vue'
import { createInitialSettings, requestHealth, saveSettings } from './lib/backends'

const navigation = [
  { id: 'home', label: '首页' },
  { id: 'workspace', label: '分析工作台' },
  { id: 'documents', label: '文稿中心' },
  { id: 'observability', label: '运行观测' }
]

const settings = reactive(createInitialSettings())
const page = ref(readPage())
const healthOk = ref(false)
const showSettings = ref(false)

onMounted(() => {
  checkHealth()
  window.addEventListener('hashchange', () => { page.value = readPage() })
})

function readPage() {
  const value = window.location.hash.replace(/^#\/?/, '')
  return navigation.some((item) => item.id === value) ? value : 'home'
}

function navigate(target) {
  window.location.hash = `/${target}`
  page.value = target
}

function changeConversation(conversationId) {
  settings.conversationId = conversationId
  saveSettings(settings)
}

async function checkHealth() {
  try {
    const data = await requestHealth(settings)
    healthOk.value = data.status === 'ok'
  } catch {
    healthOk.value = false
  }
}

async function saveAndClose() {
  saveSettings(settings)
  await checkHealth()
  showSettings.value = false
}
</script>
