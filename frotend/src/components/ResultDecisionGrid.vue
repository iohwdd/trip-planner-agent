<script setup>
defineProps({
  decisionCards: {
    type: Array,
    default: () => []
  }
});
</script>

<template>
  <div v-if="decisionCards.length" class="result-stage-grid">
    <article v-for="item in decisionCards" :key="item.label" class="result-stage-card">
      <span>{{ item.label }}</span>
      <strong>{{ item.value }}</strong>
      <p>{{ item.detail }}</p>
    </article>
  </div>
</template>
