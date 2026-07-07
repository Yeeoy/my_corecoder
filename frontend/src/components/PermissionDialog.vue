<template>
  <div v-if="visible" class="overlay" @click.self="handleDeny">
    <div class="dialog">
      <div class="dialog-header">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" width="18" height="18">
          <path d="M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
        </svg>
        <span>Permission Required</span>
      </div>

      <div class="dialog-body">
        <div class="info-row">
          <span class="label">Tool</span>
          <span class="value mono">{{ request.tool }}</span>
        </div>
        <div class="info-row">
          <span class="label">Reason</span>
          <span class="value">{{ request.reason }}</span>
        </div>
        <div v-if="argsPreview" class="info-row">
          <span class="label">Arguments</span>
          <span class="value mono args">{{ argsPreview }}</span>
        </div>
      </div>

      <div class="dialog-actions">
        <button class="btn btn-deny" @click="handleDeny">
          Deny
        </button>
        <button class="btn btn-allow" @click="handleAllow">
          Allow
        </button>
        <button
          v-if="request.allow_dir"
          class="btn btn-allow-dir"
          @click="handleAllowDir"
        >
          Allow Directory
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  visible: Boolean,
  request: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['respond'])

const argsPreview = computed(() => {
  if (!props.request.arguments) return ''
  const args = props.request.arguments
  const entries = Object.entries(args)
  if (entries.length === 0) return ''
  return entries.map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`).join(', ')
})

function handleAllow() {
  emit('respond', 'allow')
}

function handleDeny() {
  emit('respond', 'deny')
}

function handleAllowDir() {
  emit('respond', 'allow_dir')
}
</script>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: grid;
  place-items: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.dialog {
  background: var(--surface-1);
  border: 0.5px solid var(--border-strong);
  border-radius: var(--radius-lg);
  padding: 20px;
  width: 400px;
  max-width: 90vw;
  animation: slideUp 0.2s ease;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.dialog-header {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--accent-text);
  font-weight: 500;
  font-size: 15px;
  margin-bottom: 16px;
}

.dialog-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}

.info-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.label {
  font-size: 12px;
  color: var(--text-muted);
}

.value {
  font-size: 13px;
  color: var(--text-primary);
}

.args {
  font-size: 12px;
  padding: 8px;
  background: var(--surface-2);
  border-radius: var(--radius);
  word-break: break-all;
}

.dialog-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.btn {
  padding: 8px 16px;
  border-radius: var(--radius);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border: 0.5px solid var(--border);
  transition: background 0.15s ease;
}

.btn-deny {
  background: var(--surface-2);
  color: var(--text-primary);
}

.btn-deny:hover {
  background: var(--danger-bg);
  border-color: var(--danger);
}

.btn-allow {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}

.btn-allow:hover {
  opacity: 0.9;
}

.btn-allow-dir {
  background: var(--surface-2);
  color: var(--accent-text);
  border-color: var(--accent);
}

.btn-allow-dir:hover {
  background: var(--accent-bg);
}
</style>
