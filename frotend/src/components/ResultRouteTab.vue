<script setup>
import { computed } from "vue";

const props = defineProps({
  result: {
    type: Object,
    required: true
  },
  routeDays: {
    type: Array,
    default: () => []
  },
  activeRouteDay: {
    type: Number,
    default: 1
  },
  activeRouteDayData: {
    type: Object,
    default: null
  },
  formatTimeSlot: {
    type: Function,
    required: true
  },
  formatStopKind: {
    type: Function,
    required: true
  },
  formatDuration: {
    type: Function,
    required: true
  },
  formatDistance: {
    type: Function,
    required: true
  }
});

const emit = defineEmits(["select-day"]);

function selectDay(day) {
  emit("select-day", day);
}

const placeholderEntries = new Set([
  "",
  "待补充",
  "Flexible sightseeing",
  "Neighborhood walk",
  "Explore the destination core",
  "Flexible dining block",
  "Review live dining options on the day"
]);

const routeStopsByDay = computed(() => {
  const grouped = new Map();
  for (const stop of props.result.route_stops || []) {
    if (!grouped.has(stop.day)) {
      grouped.set(stop.day, []);
    }
    grouped.get(stop.day).push(stop);
  }
  return grouped;
});

function normalizeEntries(entries = []) {
  return entries.filter((item) => {
    const value = String(item || "").trim();
    return value && !placeholderEntries.has(value);
  });
}

function fallbackEntries(dayNumber, slot) {
  const stops = routeStopsByDay.value.get(dayNumber) || [];
  return stops
    .filter((stop) => stop.time_slot === slot && stop.kind !== "hotel")
    .map((stop) => stop.name);
}

function formatDayEntries(day, slot) {
  const normalized = normalizeEntries(day?.[slot] || []);
  if (normalized.length) {
    return normalized.join(" / ");
  }
  const fallback = fallbackEntries(day.day, slot);
  return fallback.length ? fallback.join(" / ") : "待补充";
}
</script>

<template>
  <div class="result-grid result-grid-single">
    <article class="info-card route-overview-board" v-if="routeDays.length">
      <div class="route-overview-header">
        <div>
          <h3>路线总览</h3>
          <p>按天切换查看停靠点节奏、转场强度和当天主题。</p>
        </div>
        <div class="route-day-switcher">
          <button
            v-for="item in routeDays"
            :key="item.day"
            class="route-day-chip"
            :class="{ 'is-active': activeRouteDay === item.day }"
            type="button"
            @click="selectDay(item.day)"
          >
            Day {{ item.day }}
          </button>
        </div>
      </div>

      <div class="route-day-summary-grid">
        <article
          v-for="item in routeDays"
          :key="item.day"
          class="route-day-summary-card"
          :class="{ 'is-active': activeRouteDay === item.day }"
        >
          <span class="route-stop-badge">第 {{ item.day }} 天</span>
          <strong>{{ item.theme }}</strong>
          <p>{{ item.stops.length }} 个停靠点 · {{ item.totalMinutes || '待确认' }} 分钟转场</p>
          <p>{{ item.totalDistance ? `${item.totalDistance} km` : '距离待确认' }}</p>
        </article>
      </div>
    </article>

    <article class="info-card route-map-card" v-if="activeRouteDayData">
      <div class="route-overview-header">
        <div>
          <h3>第 {{ activeRouteDayData.day }} 天路线展开</h3>
          <p>{{ activeRouteDayData.theme }}</p>
        </div>
        <div class="route-map-meta">
          <span>{{ activeRouteDayData.stops.length }} 个停靠点</span>
          <span>{{ activeRouteDayData.totalMinutes ? `${activeRouteDayData.totalMinutes} 分钟转场` : '转场时长待确认' }}</span>
          <span>{{ formatDistance(activeRouteDayData.totalDistance) }}</span>
        </div>
      </div>

      <ol class="route-visual-flow">
        <li
          v-for="(stop, index) in activeRouteDayData.stops"
          :key="`${stop.stop_id}-${stop.day}-${stop.order}`"
          class="route-visual-node"
        >
          <div class="route-visual-marker">
            <span>{{ index + 1 }}</span>
          </div>
          <div class="route-visual-content">
            <div class="route-visual-card">
              <div class="route-visual-card-topline">
                <span class="route-stop-badge">{{ formatTimeSlot(stop.time_slot) }}</span>
                <span class="route-kind-label">{{ formatStopKind(stop.kind) }}</span>
              </div>
              <strong>{{ stop.name }}</strong>
              <p>{{ stop.address || stop.description || '地址待确认' }}</p>
            </div>

            <div
              v-if="activeRouteDayData.legs[index]"
              class="route-visual-leg"
              :data-status="activeRouteDayData.legs[index].status"
            >
              <span>{{ activeRouteDayData.legs[index].recommended_mode }}</span>
              <span>{{ formatDuration(activeRouteDayData.legs[index].estimated_duration_minutes) }}</span>
              <span>{{ formatDistance(activeRouteDayData.legs[index].estimated_distance_km) }}</span>
            </div>
          </div>
        </li>
      </ol>
    </article>

    <article class="info-card" v-if="result.route_stops?.length">
      <h3>停靠点顺序</h3>
      <ol class="route-list route-timeline-list">
        <li v-for="stop in result.route_stops" :key="`${stop.stop_id}-${stop.day}-${stop.order}`">
          <div class="route-stop-card">
            <span class="route-stop-badge">D{{ stop.day }} · {{ formatTimeSlot(stop.time_slot) }}</span>
            <strong>第 {{ stop.order }} 站 · {{ stop.name }}</strong>
            <p>{{ formatStopKind(stop.kind) }} / {{ stop.address || stop.description || "地址待确认" }}</p>
          </div>
        </li>
      </ol>
    </article>

    <article class="info-card" v-if="result.route_legs?.length">
      <h3>路段衔接</h3>
      <div
        v-for="leg in result.route_legs"
        :key="leg.leg_id"
        class="leg-card"
        :data-status="leg.status"
      >
        <strong>{{ leg.from_stop_name }} → {{ leg.to_stop_name }}</strong>
        <p>{{ leg.recommended_mode }} · {{ formatDuration(leg.estimated_duration_minutes) }}</p>
        <p>{{ leg.suggestion }}</p>
      </div>
    </article>

    <article class="info-card" v-if="result.daily_itinerary?.length">
      <h3>逐日安排</h3>
      <div v-for="day in result.daily_itinerary" :key="day.day" class="day-card">
        <strong>第 {{ day.day }} 天 · {{ day.theme }}</strong>
        <p>上午：{{ formatDayEntries(day, "morning") }}</p>
        <p>下午：{{ formatDayEntries(day, "afternoon") }}</p>
        <p>晚上：{{ formatDayEntries(day, "evening") }}</p>
        <p>餐饮：{{ formatDayEntries(day, "dining") }}</p>
      </div>
    </article>
  </div>
</template>
