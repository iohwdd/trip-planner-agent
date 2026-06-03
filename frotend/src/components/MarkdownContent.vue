<script setup>
import { computed } from "vue";
import { renderMarkdown } from "../lib/markdown";

const props = defineProps({
  content: {
    type: String,
    default: ""
  },
  inline: {
    type: Boolean,
    default: false
  },
  tone: {
    type: String,
    default: ""
  }
});

const renderedHtml = computed(() => renderMarkdown(props.content || ""));
</script>

<template>
  <div
    class="markdown-content"
    :class="[
      inline ? 'markdown-inline' : '',
      tone ? `markdown-tone-${tone}` : ''
    ]"
    v-html="renderedHtml"
  ></div>
</template>
