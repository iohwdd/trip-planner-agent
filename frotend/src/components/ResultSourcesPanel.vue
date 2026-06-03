<script setup>
import SourceBadge from "./SourceBadge.vue";

defineProps({
  sourceReferences: {
    type: Array,
    default: () => []
  }
});
</script>

<template>
  <details class="source-panel source-panel-collapsed" v-if="sourceReferences.length">
    <summary>
      <span>来源与时效</span>
      <span>{{ sourceReferences.length }} 条</span>
    </summary>
    <div class="source-grid">
      <SourceBadge
        v-for="source in sourceReferences"
        :key="`${source.provider}-${source.label}`"
        :source="source"
      />
    </div>
  </details>
</template>
