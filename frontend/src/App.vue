<template>
  <n-config-provider :theme="darkTheme">
    <n-message-provider>
      <div class="app-shell">
        <Sidebar
          :todos="todos"
          :connection-status="connectionStatus"
          :message-count="messages.length"
          @clear="clearChat"
        />

        <main class="main-panel">
          <ChatPanel
            :messages="messages"
            :is-loading="isLoading"
            @send="sendMessage"
            @stop="stopAgent"
          />
        </main>

        <PermissionDialog
          :visible="permissionVisible"
          :request="permissionRequest"
          @respond="handlePermissionResponse"
        />
      </div>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { NConfigProvider, NMessageProvider, darkTheme } from 'naive-ui'

import Sidebar from './components/Sidebar.vue'
import ChatPanel from './components/ChatPanel.vue'
import PermissionDialog from './components/PermissionDialog.vue'

const STORAGE_KEY_MESSAGES = 'corecoder-messages'
const STORAGE_KEY_TODOS = 'corecoder-todos'

function loadFromStorage(key, defaultValue) {
  try {
    const stored = localStorage.getItem(key)
    return stored ? JSON.parse(stored) : defaultValue
  } catch {
    return defaultValue
  }
}

const messages = ref(loadFromStorage(STORAGE_KEY_MESSAGES, []))
const events = ref([])
const connectionStatus = ref('disconnected')
const permissionVisible = ref(false)
const permissionRequest = ref({})
const todos = ref(loadFromStorage(STORAGE_KEY_TODOS, []))
const isLoading = ref(false)

watch(messages, (val) => {
  localStorage.setItem(STORAGE_KEY_MESSAGES, JSON.stringify(val))
}, { deep: true })

watch(todos, (val) => {
  localStorage.setItem(STORAGE_KEY_TODOS, JSON.stringify(val))
}, { deep: true })

let ws = null
let reconnectTimer = null
let currentAssistantIdx = -1

function connectWebSocket() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    return
  }

  connectionStatus.value = 'connecting'

  ws = new WebSocket('ws://127.0.0.1:8000/ws/events')

  ws.onopen = () => {
    connectionStatus.value = 'connected'
    console.log('[CoreCoder WebSocket] connected')

    // 后端重启后清除旧状态
    messages.value = []
    todos.value = []
    currentAssistantIdx = -1
  }

  ws.onmessage = (rawEvent) => {
    try {
      const data = JSON.parse(rawEvent.data)
      console.log('[CoreCoder event]', data)
      handleServerEvent(data)
    } catch (error) {
      console.error('[CoreCoder WebSocket] invalid event:', rawEvent.data, error)
    }
  }

  ws.onerror = (error) => {
    connectionStatus.value = 'error'
    console.error('[CoreCoder WebSocket] error:', error)
  }

  ws.onclose = () => {
    connectionStatus.value = 'disconnected'
    console.log('[CoreCoder WebSocket] closed, reconnecting...')

    reconnectTimer = setTimeout(() => {
      connectWebSocket()
    }, 1000)
  }
}

function parseTodoText(text) {
  if (!text || text === 'No todos.') return []

  const lines = text.split('\n')
  const result = []

  for (const line of lines) {
    const match = line.match(/^(\d+)\.\s*\[([ x>])\]\s*(.+)$/)
    if (match) {
      const [, id, marker, content] = match
      let status = 'pending'
      if (marker === 'x') status = 'completed'
      if (marker === '>') status = 'in_progress'

      result.push({
        id: parseInt(id),
        content,
        status
      })
    }
  }

  return result
}

function handleServerEvent(event) {
  events.value.push(event)

  if (events.value.length > 300) {
    events.value = events.value.slice(-300)
  }

  if (event.type === 'websocket_connected') {
    return
  }

  if (event.type === 'user_message') {
    return
  }

  if (event.type === 'permission_request') {
    permissionRequest.value = event.payload
    permissionVisible.value = true
    return
  }

  if (event.type === 'core_event' && event.payload?.event === 'todo_updated') {
    const todoText = event.payload?.payload?.todo
    todos.value = parseTodoText(todoText)
    return
  }

  if (event.type === 'core_event' && event.payload?.event === 'after_tool_call') {
    const payload = event.payload?.payload
    if (payload?.name) {
      for (const msg of messages.value) {
        if (msg.type === 'tool' && msg.name === payload.name && msg.status === 'running') {
          msg.status = 'done'
          msg.duration = payload.duration_ms
          msg.result = payload.result_preview
          msg.resultChars = payload.result_chars
          break
        }
      }
    }
    return
  }

  if (event.type === 'tool_display') {
    currentAssistantIdx = -1

    messages.value.push({
      type: 'tool',
      name: event.payload.name,
      arguments: event.payload.arguments || {},
      status: 'running'
    })
    return
  }

  if (event.type === 'assistant_token') {
    if (currentAssistantIdx < 0) {
      messages.value.push({
        type: 'assistant',
        content: ''
      })
      currentAssistantIdx = messages.value.length - 1
    }

    messages.value[currentAssistantIdx].content += event.payload.token
    return
  }

  if (event.type === 'assistant_done') {
    isLoading.value = false
    if (event.payload.content) {
      if (currentAssistantIdx >= 0) {
        messages.value[currentAssistantIdx].content = event.payload.content
      } else {
        messages.value.push({
          type: 'assistant',
          content: event.payload.content
        })
      }
    }

    currentAssistantIdx = -1

    for (const msg of messages.value) {
      if (msg.type === 'tool' && msg.status === 'running') {
        msg.status = 'done'
      }
    }

    return
  }

  if (event.type === 'agent_error') {
    isLoading.value = false
    messages.value.push({
      type: 'assistant',
      content: `Error: ${event.payload.error}`
    })

    currentAssistantIdx = -1
  }
}

async function handlePermissionResponse(action) {
  permissionVisible.value = false

  try {
    const response = await fetch('http://127.0.0.1:8000/api/permission/respond', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ action })
    })

    const data = await response.json()
    console.log('[CoreCoder permission response]', data)
  } catch (error) {
    console.error('[CoreCoder permission error]', error)
  }
}

function clearChat() {
  messages.value = []
  todos.value = []
  currentAssistantIdx = -1
  isLoading.value = false
}

async function stopAgent() {
  try {
    await fetch('http://127.0.0.1:8000/api/stop', {
      method: 'POST'
    })
    isLoading.value = false
  } catch (error) {
    console.error('[CoreCoder] Failed to stop agent:', error)
  }
}

async function sendMessage(content) {
  const text = content.trim()
  if (!text) return

  messages.value.push({
    type: 'user',
    content: text
  })

  isLoading.value = true
  console.log('[CoreCoder chat submit]', text)

  try {
    const response = await fetch('http://127.0.0.1:8000/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        message: text
      })
    })

    const data = await response.json()
    console.log('[CoreCoder chat response]', data)

    if (!data.ok) {
      isLoading.value = false
      messages.value.push({
        type: 'assistant',
        content: `Error: ${data.error || 'Failed to start agent run.'}`
      })
    }
  } catch (error) {
    isLoading.value = false
    messages.value.push({
      type: 'assistant',
      content: `Network error: ${error.message}`
    })
  }
}

onMounted(() => {
  connectWebSocket()
})

onBeforeUnmount(() => {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
  }

  if (ws) {
    ws.close()
  }
})
</script>

<style scoped>
.app-shell {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  color: var(--text-primary);
  background: var(--bg-page);
  gap: 1px;
  background-color: var(--border);
}

.main-panel {
  min-width: 0;
  padding: 16px;
  overflow: hidden;
  background: var(--bg-page);
}
</style>
