<script setup>
import { computed } from "vue";

const props = defineProps({
  previewStops: {
    type: Array,
    default: () => []
  },
  previewSegments: {
    type: Array,
    default: () => []
  },
  formatTimeSlot: {
    type: Function,
    required: true
  }
});

const routeLinePoints = computed(() => props.previewStops
  .map((stop) => `${stop.mapX},${stop.mapY}`)
  .join(" "));

const renderedStops = computed(() => props.previewStops.map((stop, index) => ({
  ...stop,
  labelSide: index % 2 === 0 ? "top" : "bottom"
})));
</script>

<template>
  <div class="route-map-preview">
    <div class="route-map-grid"></div>
    <svg
      v-if="previewStops.length"
      class="route-map-svg"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <polyline
        class="route-map-track"
        :points="routeLinePoints"
      />
      <polyline
        class="route-map-line"
        :points="routeLinePoints"
      />
      <circle
        v-for="stop in previewStops"
        :key="`${stop.stop_id}-${stop.day}-${stop.order}-marker`"
        class="route-map-node"
        :cx="stop.mapX"
        :cy="stop.mapY"
        r="1.9"
      />
    </svg>
    <article
      v-for="stop in renderedStops"
      :key="`${stop.stop_id}-${stop.day}-${stop.order}`"
      class="route-map-pin"
      :data-side="stop.labelSide"
      :style="stop.pinStyle"
    >
      <span class="route-map-pin-dot"></span>
      <div class="route-map-pin-card">
        <strong>{{ stop.name }}</strong>
        <p>D{{ stop.day }} · {{ formatTimeSlot(stop.time_slot) }}</p>
      </div>
    </article>
  </div>
</template>
