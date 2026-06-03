<script setup>
const providerLabels = {
  amap: "高德",
  baidu: "百度",
  "heuristic-route": "启发式估算"
};

defineProps({
  source: {
    type: Object,
    required: true
  }
});

function formatProvider(provider) {
  return providerLabels[provider] || provider;
}

function formatTime(value) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    hour12: false
  });
}
</script>

<template>
  <div class="source-badge" :data-status="source.status">
    <strong>{{ source.label }}</strong>
    <span>{{ formatProvider(source.provider) }}</span>
    <small v-if="source.fetched_at">{{ formatTime(source.fetched_at) }}</small>
    <small v-if="source.note">{{ source.note }}</small>
  </div>
</template>
