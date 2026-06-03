<script setup>
import MarkdownContent from "./MarkdownContent.vue";

defineProps({
  result: {
    type: Object,
    required: true
  },
  refinementActions: {
    type: Array,
    default: () => []
  },
  formatCurrency: {
    type: Function,
    required: true
  },
  formatSeverity: {
    type: Function,
    required: true
  }
});

const emit = defineEmits(["quick-prompt"]);
</script>

<template>
  <div class="result-grid">
    <article class="info-card">
      <h3>预算拆解</h3>
      <p>总计：{{ formatCurrency(result.budget_breakdown.estimated_total, result.budget_breakdown.currency) }}</p>
      <p>住宿：{{ formatCurrency(result.budget_breakdown.accommodation, result.budget_breakdown.currency) }}</p>
      <p>交通：{{ formatCurrency(result.budget_breakdown.transportation, result.budget_breakdown.currency) }}</p>
      <p>餐饮：{{ formatCurrency(result.budget_breakdown.food, result.budget_breakdown.currency) }}</p>
      <p>活动：{{ formatCurrency(result.budget_breakdown.activities, result.budget_breakdown.currency) }}</p>
      <MarkdownContent v-if="result.budget_breakdown.note" class="result-markdown" :content="result.budget_breakdown.note" />
    </article>

    <article class="info-card">
      <h3>风险与提醒</h3>
      <ul class="warning-list">
        <li v-for="warning in result.warnings" :key="warning.message" :data-severity="warning.severity">
          <strong>{{ formatSeverity(warning.severity) }}</strong>
          <MarkdownContent class="result-markdown" :content="warning.message" />
        </li>
      </ul>
    </article>

    <article class="info-card">
      <h3>建议动作</h3>
      <ul>
        <li v-for="item in result.recommendations" :key="item.title">
          <MarkdownContent class="result-markdown" :content="`${item.title} · ${item.description}`" />
        </li>
      </ul>
    </article>

    <article class="info-card">
      <h3>直接改动线</h3>
      <div class="result-refinement-actions">
        <button
          v-for="action in refinementActions"
          :key="action.label"
          class="suggestion-chip"
          type="button"
          @click="emit('quick-prompt', action.prompt)"
        >
          {{ action.label }}
        </button>
      </div>
    </article>
  </div>
</template>
