<script setup>
defineProps({
  sessionStatusLabel: {
    type: String,
    default: ""
  },
  compactStatusPills: {
    type: Array,
    default: () => []
  },
  canSave: {
    type: Boolean,
    default: false
  },
  busy: {
    type: Boolean,
    default: false
  },
  saving: {
    type: Boolean,
    default: false
  },
  savingTarget: {
    type: String,
    default: ""
  }
});

const emit = defineEmits([
  "reset-session",
  "open-sessions",
  "open-plans",
  "save-draft",
  "save-final"
]);
</script>

<template>
  <header class="workspace-toolbar">
    <div class="workspace-toolbar-left">
      <span class="badge-pill" :class="{ running: busy }">{{ sessionStatusLabel }}</span>
      <span v-for="item in compactStatusPills" :key="item" class="badge-pill muted">{{ item }}</span>
    </div>
    <details class="workspace-actions-menu">
      <summary class="ghost-button compact-button">工作台操作</summary>
      <div class="workspace-actions-popover">
        <button class="ghost-button compact-button" type="button" @click="emit('reset-session')">新会话</button>
        <button class="ghost-button compact-button" type="button" @click="emit('open-sessions')">历史会话</button>
        <button class="ghost-button compact-button" type="button" @click="emit('open-plans')">我的方案</button>
        <template v-if="canSave">
          <button class="secondary-button compact" type="button" :disabled="busy || saving" @click="emit('save-draft')">
            {{ saving && savingTarget === "draft" ? "草案保存中..." : "暂存草案" }}
          </button>
          <button class="primary-button compact" type="button" :disabled="busy || saving" @click="emit('save-final')">
            {{ saving && savingTarget === "final" ? "方案保存中..." : "保存方案" }}
          </button>
        </template>
      </div>
    </details>
  </header>
</template>
