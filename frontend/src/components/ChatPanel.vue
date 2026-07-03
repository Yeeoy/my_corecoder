<template>
  <section class="chat-panel">
    <header class="chat-header">
      <div class="header-left">
        <h1 class="title">Chat</h1>
        <span class="task-hint" v-if="currentTask !== 'Ready'">{{ currentTask }}</span>
      </div>
      <div class="header-right">
        <span :class="['badge', agentStatus]">
          <span v-if="agentStatus === 'running'" class="pulse"></span>
          {{ agentStatus }}
        </span>
      </div>
    </header>

    <div class="messages" ref="messagesRef">
      <template v-if="messages.length">
        <template v-for="(item, index) in messages" :key="`msg-${index}`">
          <!-- User message -->
          <div
            v-if="item.type === 'user'"
            class="msg user"
          >
            <div class="msg-content">{{ item.content }}</div>
          </div>

          <!-- Assistant message -->
          <div
            v-else-if="item.type === 'assistant'"
            class="msg assistant"
          >
            <div class="msg-avatar">C</div>
            <div class="msg-content">
              <div class="markdown-body" v-html="renderMarkdown(item.content)"></div>
            </div>
          </div>

          <!-- Tool call card -->
          <div
            v-else-if="item.type === 'tool'"
            class="tool-card"
            :class="[item.status, { expanded: item.expanded }]"
            @click="toggleToolExpand(index)"
          >
            <div class="tool-header">
              <div class="tool-icon">
                <svg v-if="item.status === 'done'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                  <path d="M20 6L9 17l-5-5"/>
                </svg>
                <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                  <circle cx="12" cy="12" r="10" stroke-dasharray="40" stroke-dashoffset="12"/>
                </svg>
              </div>
              <span class="tool-name mono">{{ item.name }}</span>
              <span v-if="item.duration" class="tool-duration mono">{{ item.duration }}ms</span>
              <svg class="tool-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                <path d="M6 9l6 6 6-6"/>
              </svg>
            </div>
            <div class="tool-args mono">{{ formatArgs(item.arguments) }}</div>
            <div v-if="item.expanded && item.result" class="tool-result">
              <div class="tool-result-label">Result:</div>
              <pre class="tool-result-content mono">{{ item.result }}</pre>
            </div>
          </div>
        </template>
      </template>

      <div v-else class="empty-state">
        <div class="empty-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="28" height="28">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
          </svg>
        </div>
        <h2>Start a conversation</h2>
        <p>Ask me to read files, write code, run commands, or search with MCP.</p>
        <div class="suggestions">
          <button class="suggestion" @click="emit('send', 'Analyze the project structure')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" width="14" height="14">
              <path d="M3 3v18h18"/>
              <path d="M18 17V9M13 17V5M8 17v-3"/>
            </svg>
            Analyze project
          </button>
          <button class="suggestion" @click="emit('send', 'Find and fix bugs in the codebase')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" width="14" height="14">
              <path d="M12 2a10 10 0 100 20 10 10 0 000-20zM12 8v4M12 16h.01"/>
            </svg>
            Find bugs
          </button>
          <button class="suggestion" @click="emit('send', 'Help me implement a new feature')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" width="14" height="14">
              <path d="M12 5v14M5 12h14"/>
            </svg>
            New feature
          </button>
        </div>
      </div>

      <!-- Loading indicator -->
      <div v-if="isLoading" class="loading-indicator">
        <div class="loading-dot"></div>
        <div class="loading-dot"></div>
        <div class="loading-dot"></div>
      </div>
    </div>

    <form class="composer" @submit.prevent="submit">
      <div class="input-wrapper">
        <input
          v-model="input"
          type="text"
          placeholder="Ask CoreCoder anything..."
          @compositionstart="onCompositionStart"
          @compositionend="onCompositionEnd"
          @keydown.enter.exact.prevent="onEnter"
        />
        <button
          v-if="isLoading"
          type="button"
          class="stop-button"
          aria-label="Stop"
          @click="$emit('stop')"
        >
          <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16">
            <rect x="6" y="6" width="12" height="12" rx="2"/>
          </svg>
        </button>
        <button v-else type="submit" aria-label="Send" :disabled="!input.trim()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="16" height="16">
            <path d="M5 12h14M13 6l6 6-6 6"/>
          </svg>
        </button>
      </div>
    </form>
  </section>
</template>

<script setup>
import { ref, watch, nextTick, computed } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  messages: {
    type: Array,
    default: () => []
  },
  isLoading: {
    type: Boolean,
    default: false
  }
})

const messagesRef = ref(null)
const input = ref('')
const isComposing = ref(false)

const currentTask = computed(() => {
  if (props.messages.length === 0) return 'Ready'
  const lastUser = [...props.messages].reverse().find(m => m.type === 'user')
  if (lastUser) {
    const text = lastUser.content
    return text.length > 40 ? text.slice(0, 40) + '...' : text
  }
  return 'Processing...'
})

const agentStatus = computed(() => {
  const lastMsg = props.messages[props.messages.length - 1]
  if (!lastMsg) return 'idle'
  if (lastMsg.type === 'tool' && lastMsg.status === 'running') return 'running'
  return 'idle'
})

function scrollToBottom() {
  nextTick(() => {
    const el = messagesRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

watch(() => props.messages.length, scrollToBottom)
watch(
  () => {
    const last = props.messages[props.messages.length - 1]
    return last ? last.content : ''
  },
  scrollToBottom
)

const emit = defineEmits(['send', 'stop'])

function renderMarkdown(content) {
  if (!content) return ''
  return marked(content, {
    breaks: true,
    gfm: true
  })
}

function onCompositionStart() {
  isComposing.value = true
}

function onCompositionEnd() {
  isComposing.value = false
}

function onEnter() {
  if (isComposing.value) return
  submit()
}

function submit() {
  const content = input.value.trim()
  if (!content) return
  emit('send', content)
  input.value = ''
}

function formatArgs(args) {
  if (!args) return ''
  const entries = Object.entries(args)
  if (entries.length === 0) return ''
  const [key, val] = entries[0]
  const display = typeof val === 'string' && val.length > 30 ? val.slice(0, 30) + '...' : val
  return `${key}=${display}`
}

function toggleToolExpand(index) {
  const msg = props.messages[index]
  if (msg && msg.type === 'tool') {
    msg.expanded = !msg.expanded
  }
}
</script>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 0.5px solid var(--border);
  margin-bottom: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.task-hint {
  font-size: 12px;
  color: var(--text-muted);
  padding: 2px 8px;
  background: var(--surface-1);
  border-radius: 4px;
}

.header-right {
  display: flex;
  align-items: center;
}

.badge {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 20px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.badge.running {
  background: var(--accent-bg);
  color: var(--accent-text);
}

.badge.idle {
  background: var(--surface-1);
  color: var(--text-muted);
}

.pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 1.4s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.messages {
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 4px 0;
}

.msg {
  display: flex;
  gap: 10px;
  animation: fadeUp 0.3s ease;
}

@keyframes fadeUp {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

.msg.user {
  justify-content: flex-end;
}

.msg-avatar {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  background: var(--accent-bg);
  color: var(--accent-text);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}

.msg-content {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.5;
}

.msg.user .msg-content {
  background: var(--accent);
  color: white;
  border-bottom-right-radius: 4px;
  white-space: pre-wrap;
  word-break: break-word;
}

.msg.assistant .msg-content {
  background: var(--surface-1);
  color: var(--text-primary);
  border: 0.5px solid var(--border);
  border-bottom-left-radius: 4px;
}

/* GitHub 风格 Markdown 样式 */
.markdown-body {
  font-size: 14px;
  line-height: 1.6;
  word-wrap: break-word;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  margin-top: 16px;
  margin-bottom: 8px;
  font-weight: 600;
  line-height: 1.25;
}

.markdown-body :deep(h1) {
  font-size: 1.5em;
  padding-bottom: 0.3em;
  border-bottom: 1px solid var(--border);
}

.markdown-body :deep(h2) {
  font-size: 1.25em;
  padding-bottom: 0.3em;
  border-bottom: 1px solid var(--border);
}

.markdown-body :deep(h3) {
  font-size: 1.1em;
}

.markdown-body :deep(h4) {
  font-size: 1em;
}

.markdown-body :deep(p) {
  margin-top: 0;
  margin-bottom: 10px;
}

.markdown-body :deep(blockquote) {
  margin: 0;
  padding: 0 1em;
  color: var(--text-secondary);
  border-left: 0.25em solid var(--border-strong);
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin-top: 0;
  margin-bottom: 10px;
  padding-left: 2em;
}

.markdown-body :deep(li) {
  margin-top: 0.25em;
}

.markdown-body :deep(li + li) {
  margin-top: 0.25em;
}

.markdown-body :deep(code) {
  padding: 0.2em 0.4em;
  margin: 0;
  font-size: 85%;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 6px;
  font-family: 'JetBrains Mono', monospace;
}

.markdown-body :deep(pre) {
  padding: 12px;
  overflow: auto;
  font-size: 85%;
  line-height: 1.45;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 6px;
  margin-top: 0;
  margin-bottom: 10px;
}

.markdown-body :deep(pre code) {
  padding: 0;
  margin: 0;
  background: transparent;
  border-radius: 0;
  font-size: 100%;
}

.markdown-body :deep(table) {
  border-spacing: 0;
  border-collapse: collapse;
  margin-top: 0;
  margin-bottom: 10px;
  width: auto;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 6px 13px;
  border: 1px solid var(--border);
}

.markdown-body :deep(th) {
  font-weight: 600;
  background: rgba(255, 255, 255, 0.04);
}

.markdown-body :deep(tr) {
  background: transparent;
  border-top: 1px solid var(--border);
}

.markdown-body :deep(tr:nth-child(2n)) {
  background: rgba(255, 255, 255, 0.02);
}

.markdown-body :deep(hr) {
  height: 0.25em;
  padding: 0;
  margin: 16px 0;
  background: var(--border);
  border: 0;
  border-radius: 2px;
}

.markdown-body :deep(a) {
  color: var(--accent-text);
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

.markdown-body :deep(img) {
  max-width: 100%;
  border-radius: 6px;
}

.markdown-body :deep(strong) {
  font-weight: 600;
}

.markdown-body :deep(del) {
  color: var(--text-muted);
}

.tool-card {
  background: var(--surface-1);
  border: 0.5px solid var(--border);
  border-radius: 8px;
  padding: 6px 10px;
  margin-left: 38px;
  font-size: 12px;
  animation: fadeUp 0.3s ease;
  max-width: fit-content;
  cursor: pointer;
  transition: border-color 0.15s ease;
}

.tool-card:hover {
  border-color: var(--border-strong);
}

.tool-card.expanded {
  max-width: fit-content;
  border-color: var(--border-strong);
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tool-icon {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.tool-card.running .tool-icon {
  color: var(--accent-text);
  animation: spin 1.2s linear infinite;
}

.tool-card.done .tool-icon {
  color: var(--success);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.tool-name {
  color: var(--text-primary);
  font-weight: 500;
}

.tool-args {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
  padding-left: 18px;
  word-break: break-all;
  line-height: 1.4;
}

.tool-duration {
  color: var(--text-muted);
  font-size: 11px;
  flex-shrink: 0;
}

.tool-chevron {
  color: var(--text-muted);
  flex-shrink: 0;
  transition: transform 0.15s ease;
}

.tool-card.expanded .tool-chevron {
  transform: rotate(180deg);
}

.tool-result {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 0.5px solid var(--border);
}

.tool-result-label {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.tool-result-content {
  margin: 0;
  padding: 8px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 6px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-secondary);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  max-width: 500px;
  overflow-y: auto;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: var(--text-muted);
}

.empty-icon {
  width: 56px;
  height: 56px;
  margin: 0 auto 16px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  color: var(--accent-text);
  background: var(--accent-bg);
}

.empty-state h2 {
  margin: 0 0 8px;
  color: var(--text-primary);
  font-size: 16px;
  font-weight: 600;
}

.empty-state p {
  margin: 0 0 24px;
  font-size: 13px;
  max-width: 300px;
}

.suggestions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
}

.suggestion {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: var(--surface-1);
  border: 0.5px solid var(--border);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.suggestion:hover {
  background: var(--surface-2);
  border-color: var(--border-strong);
  color: var(--text-primary);
}

.suggestion svg {
  flex-shrink: 0;
}

.loading-indicator {
  display: flex;
  gap: 4px;
  padding: 12px 14px;
  margin-left: 38px;
  animation: fadeUp 0.3s ease;
}

.loading-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  animation: loadingBounce 1.4s ease-in-out infinite;
}

.loading-dot:nth-child(1) {
  animation-delay: 0s;
}

.loading-dot:nth-child(2) {
  animation-delay: 0.2s;
}

.loading-dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes loadingBounce {
  0%, 80%, 100% {
    transform: scale(0.6);
    opacity: 0.4;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

.composer {
  padding-top: 12px;
  border-top: 0.5px solid var(--border);
  flex-shrink: 0;
}

.input-wrapper {
  display: flex;
  gap: 8px;
  max-width: 600px;
  margin: 0 auto;
}

.input-wrapper input {
  flex: 1;
  background: var(--surface-1);
  border: 0.5px solid var(--border);
  border-radius: 10px;
  padding: 0 16px;
  height: 48px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s ease;
}

.input-wrapper input:focus {
  border-color: var(--border-strong);
}

.input-wrapper input::placeholder {
  color: var(--text-muted);
}

.input-wrapper button {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  background: var(--accent);
  border: none;
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity 0.15s ease;
  flex-shrink: 0;
}

.input-wrapper button:hover {
  opacity: 0.9;
}

.input-wrapper button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.stop-button {
  background: var(--danger) !important;
}

.stop-button:hover {
  opacity: 0.9;
}

.mono {
  font-family: 'JetBrains Mono', monospace;
}
</style>
