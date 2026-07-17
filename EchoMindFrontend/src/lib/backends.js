const DEFAULT_ENDPOINT = import.meta.env.VITE_API_URL || import.meta.env.VITE_PYTHON_API_URL || '/api/python'

export function createInitialSettings() {
  const saved = readSettings()
  return {
    endpoint: saved.endpoint || saved.endpoints?.python || DEFAULT_ENDPOINT,
    userId: saved.userId || 'researcher-001',
    conversationId: saved.conversationId || ''
  }
}

export function saveSettings(settings) {
  localStorage.setItem('standardpilot.frontend.settings', JSON.stringify(settings))
