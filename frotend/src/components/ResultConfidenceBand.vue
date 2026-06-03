<script setup>
import MarkdownContent from "./MarkdownContent.vue";

defineProps({
  tone: {
    type: String,
    default: "neutral"
  },
  headline: {
    type: String,
    default: ""
  },
  description: {
    type: String,
    default: ""
  },
  metrics: {
    type: Array,
    default: () => []
  },
  guidanceCards: {
    type: Array,
    default: () => []
  }
});
</script>

<template>
  <section class="result-confidence-band" :data-tone="tone">
    <div class="result-confidence-copy">
      <p class="eyebrow">可信度与可用性摘要</p>
      <MarkdownContent class="result-markdown result-markdown-hero" :content="headline" />
      <MarkdownContent class="result-markdown" :content="description" />
    </div>
    <div class="result-confidence-metrics" v-if="metrics.length">
      <span
        v-for="item in metrics"
        :key="item.label"
        class="constraint-pill"
      >
        {{ item.label }} · {{ item.value }}
      </span>
    </div>
    <div class="result-confidence-grid" v-if="guidanceCards.length">
      <article
        v-for="item in guidanceCards"
        :key="item.label"
        class="result-confidence-card"
      >
        <span>{{ item.label }}</span>
        <MarkdownContent class="result-markdown result-markdown-title" :content="item.title" />
        <MarkdownContent class="result-markdown" :content="item.detail" />
      </article>
    </div>
  </section>
</template>
