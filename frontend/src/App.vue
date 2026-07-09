<template>
  <n-config-provider :theme="darkTheme">
    <n-message-provider>
      <div class="app-shell">
        <Sidebar
          :todos="todos"
          :connection-status="connectionStatus"
          :message-count="messages.length"
          :sessions="sessions"
          :current-session-id="currentSessionId"
          @clear="clearChat"
          @switch="switchSession"
          @new="newSession"
          @delete="deleteSession"
          @insert-prompt="insertPrompt"
        />

        <main class="main-panel">
          <ChatPanel
            :messages="messages"
            :is-loading="isLoading"
            :draft="composerDraft"
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
import { openaiToUiMessages } from './utils/messageFormat'
import { API_BASE, WS_BASE } from './config'

// 对话历史的真相在后端(sessions/*.json),前端连上后从 /api/session 拉取渲染,
// 不再用 localStorage 存对话 —— 单一数据源,避免前后端不一致。
const messages = ref([])
const connectionStatus = ref('disconnected')
const permissionVisible = ref(false)
const permissionRequest = ref({})
const todos = ref([])
const isLoading = ref(false)

// 会话管理状态
const sessions = ref([])
const currentSessionId = ref(null)

// 点击侧栏能力项(skill/tool)时,往输入框插入的提示词草稿。
// 用 seq 让「连点同一项」也能触发 ChatPanel 的 watch。
const composerDraft = ref({ text: '', seq: 0 })

let ws = null
let reconnectTimer = null
let reconnectAttempts = 0
let currentAssistantIdx = -1

function connectWebSocket() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    return
  }

  connectionStatus.value = 'connecting'

  ws = new WebSocket(`${WS_BASE}/ws/events`)

  ws.onopen = () => {
    connectionStatus.value = 'connected'
    console.log('[CoreCoder WebSocket] connected')

    // 连上就重置退避计数,下次断开重新从 1s 起算
    reconnectAttempts = 0

    // 后端重启后清除旧状态
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

    // 指数退避:1s, 2s, 4s ... 封顶 30s,避免后端挂掉时疯狂重连刷屏
    const delay = Math.min(1000 * 2 ** reconnectAttempts, 30000)
    reconnectAttempts += 1
    console.log(`[CoreCoder WebSocket] closed, reconnecting in ${delay}ms`)

    reconnectTimer = setTimeout(() => {
      connectWebSocket()
    }, delay)
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

    // 对话已落盘,刷新会话列表(新会话首次对话会新增一条 session)
    refreshSessions()
    // 新会话首次对话后后端才生成 id,同步过来让侧边栏高亮当前项
    if (currentSessionId.value === null) {
      syncCurrentSessionId()
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
    const response = await fetch(`${API_BASE}/api/permission/respond`, {
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
    await fetch(`${API_BASE}/api/stop`, {
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
    const response = await fetch(`${API_BASE}/api/chat`, {
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

// ---- 会话管理 ----
// 会话真相在后端(sessions/*.json)。前端负责:拉列表、拉当前会话渲染、切换、新建。

async function refreshSessions() {
  try {
    const response = await fetch(`${API_BASE}/api/sessions`)
    const data = await response.json()
    if (data.ok) {
      sessions.value = data.sessions
    }
  } catch (error) {
    console.error('[CoreCoder] Failed to refresh sessions:', error)
  }
}

async function loadCurrentSession() {
  try {
    const response = await fetch(`${API_BASE}/api/session`)
    const data = await response.json()
    if (data.ok) {
      messages.value = openaiToUiMessages(data.messages)
      currentSessionId.value = data.session_id
      currentAssistantIdx = -1
    }
  } catch (error) {
    console.error('[CoreCoder] Failed to load current session:', error)
  }
}

// 新会话首次对话后,后端才生成 id;只同步 id(不重拉 messages,避免抹掉
// 实时事件填进去的 tool duration 等 UI-only 信息)
async function syncCurrentSessionId() {
  try {
    const response = await fetch(`${API_BASE}/api/session`)
    const data = await response.json()
    if (data.ok) {
      currentSessionId.value = data.session_id
    }
  } catch (error) {
    console.error('[CoreCoder] Failed to sync current session id:', error)
  }
}

async function switchSession(sessionId) {
  if (sessionId === currentSessionId.value) return

  try {
    const response = await fetch(`${API_BASE}/api/session/switch`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ session_id: sessionId })
    })
    const data = await response.json()
    if (data.ok) {
      messages.value = openaiToUiMessages(data.messages)
      currentSessionId.value = data.session_id
      // 切换后重置流式/加载状态,否则残留的 currentAssistantIdx 会把
      // 新会话的 token 拼到旧卡片上
      todos.value = []
      currentAssistantIdx = -1
      isLoading.value = false
    } else {
      console.error('[CoreCoder] Switch failed:', data.error)
    }
  } catch (error) {
    console.error('[CoreCoder] Failed to switch session:', error)
  }
}

async function newSession() {
  try {
    const response = await fetch(`${API_BASE}/api/session/new`, {
      method: 'POST'
    })
    const data = await response.json()
    if (data.ok) {
      // new 只返回 {ok},本地清空即可;新 id 等首次对话落盘后再同步
      messages.value = []
      todos.value = []
      currentSessionId.value = null
      currentAssistantIdx = -1
      isLoading.value = false
      refreshSessions()
    }
  } catch (error) {
    console.error('[CoreCoder] Failed to create new session:', error)
  }
}

async function deleteSession(sessionId) {
  try {
    const response = await fetch(`${API_BASE}/api/session/delete`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ session_id: sessionId })
    })
    const data = await response.json()
    if (data.ok) {
      // 后端返回删除后的当前会话 id;若删的是当前会话,后端已就地清空
      if (data.current === null) {
        messages.value = []
        todos.value = []
        currentSessionId.value = null
        currentAssistantIdx = -1
        isLoading.value = false
      }
      refreshSessions()
    } else {
      console.error('[CoreCoder] Delete failed:', data.error)
    }
  } catch (error) {
    console.error('[CoreCoder] Failed to delete session:', error)
  }
}

// 点击侧栏能力项 → 往输入框插入提示词草稿并聚焦。把「展示型」侧栏升级成「操作型」。
function insertPrompt(text) {
  composerDraft.value = { text, seq: composerDraft.value.seq + 1 }
}

onMounted(() => {
  connectWebSocket()
  loadCurrentSession()
  refreshSessions()
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
  grid-template-rows: minmax(0, 1fr);
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
  display:flex; flex-direction:column; min-height:0;
}
</style>
