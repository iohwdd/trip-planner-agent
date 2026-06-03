<script setup>
defineProps({
  summary: {
    type: String,
    default: "旅行方案已生成"
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

const emit = defineEmits(["save-draft", "save-final"]);
</script>

<template>
  <section class="panel workbench-complete-banner">
    <div class="workbench-complete-copy">
      <p class="eyebrow">已完成</p>
      <strong>{{ summary }}</strong>
    </div>
    <div class="workbench-complete-actions">
      <button class="secondary-button" type="button" :disabled="saving" @click="emit('save-draft')">
        {{ saving && savingTarget === "draft" ? "草案保存中..." : "保存草案" }}
      </button>
      <button class="primary-button" type="button" :disabled="saving" @click="emit('save-final')">
        {{ saving && savingTarget === "final" ? "最终方案保存中..." : "保存最终方案" }}
      </button>
    </div>
  </section>
</template>
