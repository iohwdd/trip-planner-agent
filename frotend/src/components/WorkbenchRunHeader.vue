<script setup>
defineProps({
  showResult: {
    type: Boolean,
    default: false
  },
  statusLabel: {
    type: String,
    default: "正在生成"
  }
});

const emit = defineEmits(["back"]);
</script>

<template>
  <header class="panel workbench-run-header">
    <button class="ghost-button" type="button" @click="emit('back')">返回表单</button>
    <div class="workbench-run-header-copy">
      <p class="eyebrow">工作台运行</p>
      <strong>{{ showResult ? "结果面板" : statusLabel }}</strong>
    </div>
  </header>
</template>
