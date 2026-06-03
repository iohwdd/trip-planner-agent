<script setup>
defineProps({
  label: {
    type: String,
    default: ""
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
  actions: {
    type: Array,
    default: () => []
  },
  tone: {
    type: String,
    default: "idle"
  }
});

const emit = defineEmits(["action"]);

function buttonClass(tone) {
  if (tone === "primary") {
    return "primary-button";
  }
  if (tone === "secondary") {
    return "secondary-button";
  }
  return "ghost-button";
}
</script>

<template>
  <section class="workspace-stage-hero" :data-tone="tone">
    <div class="workspace-stage-copy">
      <p class="eyebrow">{{ label }}</p>
      <h1>{{ headline }}</h1>
      <p>{{ description }}</p>
    </div>
    <div class="workspace-stage-metrics">
      <span v-for="item in metrics" :key="item" class="constraint-pill">{{ item }}</span>
    </div>
    <div class="workspace-stage-prompts">
      <button
        v-for="action in actions"
        :key="action.key"
        :class="buttonClass(action.tone)"
        type="button"
        :disabled="action.disabled"
        @click="emit('action', action.key)"
      >
        {{ action.label }}
      </button>
    </div>
  </section>
</template>
