<script setup>
defineProps({
  trackClass: {
    type: String,
    required: true
  },
  fillClass: {
    type: String,
    required: true
  },
  fillStyle: {
    type: Object,
    default: () => ({})
  }
});
</script>

<template>
  <div :class="trackClass">
    <span :class="fillClass" :style="fillStyle"></span>
  </div>
</template>
