<script setup>
defineProps({
  message: {
    type: String,
    default: ""
  },
  tone: {
    type: String,
    default: "info"
  }
});
</script>

<template>
  <transition name="fade-slide">
    <p v-if="message" class="save-feedback-banner" :data-tone="tone">{{ message }}</p>
  </transition>
</template>
