<script setup>
import MarkdownContent from "./MarkdownContent.vue";

defineProps({
  result: {
    type: Object,
    required: true
  },
  statusLabels: {
    type: Object,
    required: true
  },
  planStateLabels: {
    type: Object,
    required: true
  },
  summaryPills: {
    type: Array,
    default: () => []
  }
});
</script>

<template>
  <div class="hero-card hero-card-stack">
    <div class="hero-card-topline">
      <span class="status-pill" :data-status="result.status">{{ statusLabels[result.status] || result.status }}</span>
      <span class="status-pill plan-pill">{{ planStateLabels[result.plan_state] || result.plan_state }}</span>
    </div>
    <div>
      <MarkdownContent class="result-markdown result-markdown-hero" :content="result.trip_summary" />
      <MarkdownContent v-if="result.conversation_summary" class="conversation-copy result-markdown" :content="result.conversation_summary" />
    </div>
    <ul class="assumption-list" v-if="result.assumptions?.length">
      <li v-for="assumption in result.assumptions" :key="assumption">
        <MarkdownContent class="result-markdown" :content="assumption" />
      </li>
    </ul>
    <div class="result-summary-pills" v-if="summaryPills.length">
      <span v-for="item in summaryPills" :key="item" class="constraint-pill">{{ item }}</span>
    </div>
  </div>
</template>
