<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <div class="brand">
        <div class="logo">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="18" height="18">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
          </svg>
        </div>
        <div class="brand-text">
          <div class="title">CoreCoder</div>
          <div class="subtitle">AI Agent</div>
        </div>
      </div>

      <div class="status-bar">
        <span class="status-dot" :class="connectionStatus"></span>
        <span class="status-text">{{ connectionStatus }}</span>
      </div>
    </div>

    <div class="sidebar-content">
      <!-- Todo Section -->
      <div v-if="todos.length" class="section">
        <div class="section-header">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" width="14" height="14">
            <path d="M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>
          </svg>
          <span>Todo</span>
          <span class="count">{{ todos.length }}</span>
        </div>

        <div class="todo-list">
          <div
            v-for="todo in todos"
            :key="todo.id"
            class="todo-item"
            :class="todo.status"
          >
            <div class="todo-marker">
              <svg v-if="todo.status === 'completed'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                <path d="M20 6L9 17l-5-5"/>
              </svg>
              <svg v-else-if="todo.status === 'in_progress'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                <circle cx="12" cy="12" r="10" stroke-dasharray="40" stroke-dashoffset="12"/>
              </svg>
              <div v-else class="dot"></div>
            </div>
            <span class="todo-content">{{ todo.content }}</span>
          </div>
        </div>
      </div>

      <!-- Tools Section -->
      <div v-if="tools.length" class="section">
        <div class="section-header">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" width="14" height="14">
            <path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/>
          </svg>
          <span>Tools</span>
          <span class="count">{{ tools.length }}</span>
        </div>

        <div class="tool-list">
          <div
            v-for="tool in tools"
            :key="tool.name"
            class="tool-item"
            :title="tool.description"
          >
            <span class="tool-name mono">{{ tool.name }}</span>
          </div>
        </div>
      </div>

      <!-- Skills Section -->
      <div v-if="skills.length" class="section">
        <div class="section-header">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" width="14" height="14">
            <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
          </svg>
          <span>Skills</span>
          <span class="count">{{ skills.length }}</span>
        </div>

        <div class="skill-list">
          <div
            v-for="skill in skills"
            :key="skill.name"
            class="skill-item"
            :title="skill.description"
          >
            <span class="skill-name">{{ skill.display_name }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="sidebar-footer">
      <div class="session-info">
        <div class="info-row">
          <span class="info-label">Messages</span>
          <span class="info-value">{{ messageCount }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">Mode</span>
          <span class="info-value">default</span>
        </div>
      </div>
      <div class="footer-item" @click="$emit('clear')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" width="14" height="14">
          <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
        </svg>
        <span>Clear Chat</span>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'

const props = defineProps({
  todos: {
    type: Array,
    default: () => []
  },
  connectionStatus: {
    type: String,
    default: 'disconnected'
  },
  messageCount: {
    type: Number,
    default: 0
  }
})

defineEmits(['clear'])

const tools = ref([])
const skills = ref([])

async function fetchTools() {
  try {
    const response = await fetch('http://127.0.0.1:8000/api/tools')
    const data = await response.json()
    if (data.ok) {
      tools.value = data.tools
    }
  } catch (error) {
    console.error('[CoreCoder] Failed to fetch tools:', error)
  }
}

async function fetchSkills() {
  try {
    const response = await fetch('http://127.0.0.1:8000/api/skills')
    const data = await response.json()
    if (data.ok) {
      skills.value = data.skills
    }
  } catch (error) {
    console.error('[CoreCoder] Failed to fetch skills:', error)
  }
}

function fetchAll() {
  fetchTools()
  fetchSkills()
}

watch(() => props.connectionStatus, (status) => {
  if (status === 'connected') {
    fetchAll()
  }
})

onMounted(() => {
  fetchAll()
})
</script>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--surface-1);
  border-right: 0.5px solid var(--border);
}

.sidebar-header {
  padding: 16px;
  border-bottom: 0.5px solid var(--border);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.logo {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  background: var(--accent-bg);
  color: var(--accent-text);
  border-radius: 8px;
}

.brand-text {
  flex: 1;
}

.title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.subtitle {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 1px;
}

.status-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-muted);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
}

.status-dot.connected {
  background: var(--success);
}

.status-dot.connecting {
  background: var(--accent);
  animation: pulse 1.2s ease-in-out infinite;
}

.status-dot.disconnected,
.status-dot.error {
  background: var(--danger);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.sidebar-content {
  flex: 1;
  overflow: auto;
  padding: 12px;
}

.section {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 0 4px 8px;
}

.count {
  margin-left: auto;
  background: var(--surface-2);
  padding: 1px 6px;
  border-radius: 10px;
  font-size: 10px;
  color: var(--text-secondary);
}

.todo-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  transition: background 0.15s ease;
}

.todo-item:hover {
  background: var(--surface-2);
}

.todo-item.completed {
  color: var(--text-muted);
  text-decoration: line-through;
}

.todo-item.in_progress {
  color: var(--text-primary);
}

.todo-marker {
  flex-shrink: 0;
  margin-top: 2px;
}

.todo-marker svg {
  display: block;
}

.todo-item.completed .todo-marker svg {
  color: var(--success);
}

.todo-item.in_progress .todo-marker svg {
  color: var(--accent-text);
  animation: spin 1.2s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
}

.todo-content {
  line-height: 1.4;
}

.empty-hint {
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 4px;
}

.tool-list,
.skill-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tool-item,
.skill-item {
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  transition: background 0.15s ease;
}

.tool-item:hover,
.skill-item:hover {
  background: var(--surface-2);
}

.tool-name {
  color: var(--accent-text);
  font-size: 11px;
}

.skill-name {
  color: var(--text-primary);
  font-size: 12px;
}

.sidebar-footer {
  padding: 12px 16px;
  border-top: 0.5px solid var(--border);
}

.session-info {
  margin-bottom: 10px;
  padding: 8px;
  background: var(--surface-2);
  border-radius: 6px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  padding: 2px 0;
}

.info-label {
  color: var(--text-muted);
}

.info-value {
  color: var(--text-secondary);
  font-family: 'JetBrains Mono', monospace;
}

.footer-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  padding: 6px 8px;
  border-radius: 6px;
  transition: all 0.15s ease;
}

.footer-item:hover {
  color: var(--danger);
  background: var(--danger-bg);
}
</style>
