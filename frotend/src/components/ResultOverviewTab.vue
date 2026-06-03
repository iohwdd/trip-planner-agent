<script setup>
import MarkdownContent from "./MarkdownContent.vue";
import ProgressBar from "./ProgressBar.vue";
import RoutePreviewMap from "./RoutePreviewMap.vue";

defineProps({
  result: {
    type: Object,
    required: true
  },
  previewStops: {
    type: Array,
    default: () => []
  },
  previewSegments: {
    type: Array,
    default: () => []
  },
  budgetRows: {
    type: Array,
    default: () => []
  },
  budgetFillStyle: {
    type: Function,
    required: true
  },
  formatTimeSlot: {
    type: Function,
    required: true
  },
  formatCurrency: {
    type: Function,
    required: true
  }
});
</script>

<template>
  <div class="result-grid">
    <article class="info-card route-map-preview-card" v-if="previewStops.length">
      <div class="route-overview-header">
        <div>
          <h3>路线预览</h3>
          <MarkdownContent
            v-if="result.route_overview?.headline"
            class="result-markdown result-markdown-title"
            :content="result.route_overview.headline"
          />
          <p v-else>不看细节也能快速感知这版路线的大致走势与停靠节奏。</p>
        </div>
        <span class="route-preview-caption">
          {{ result.route_overview?.total_stops || previewStops.length }} 个关键停靠点
        </span>
      </div>

      <RoutePreviewMap
        :preview-stops="previewStops"
        :preview-segments="previewSegments"
        :format-time-slot="formatTimeSlot"
      />

      <MarkdownContent
        v-if="result.route_overview?.strategy"
        class="result-markdown"
        :content="result.route_overview.strategy"
      />
      <p v-if="result.route_overview?.pace">节奏：{{ result.route_overview.pace }}</p>
    </article>

    <article class="info-card">
      <h3>预算快照</h3>
      <p class="budget-total">{{ formatCurrency(result.budget_breakdown.estimated_total, result.budget_breakdown.currency) }}</p>
      <div class="budget-progress-list">
        <div v-for="item in budgetRows" :key="item.key" class="budget-progress-row">
          <div class="budget-progress-meta">
            <span>{{ item.label }}</span>
            <strong>{{ formatCurrency(item.value, result.budget_breakdown.currency) }}</strong>
          </div>
          <ProgressBar
            track-class="budget-progress-track"
            fill-class="budget-progress-fill"
            :fill-style="budgetFillStyle(item.value, result.budget_breakdown.estimated_total)"
          />
        </div>
      </div>
      <MarkdownContent v-if="result.budget_breakdown.note" class="result-markdown" :content="result.budget_breakdown.note" />
    </article>

    <details
      class="info-card result-disclosure-card"
      v-if="result.confirmed_constraints || result.alternatives?.length || result.revision_notes?.length"
    >
      <summary>
        <span>更多背景与备选</span>
        <span>默认收起</span>
      </summary>

      <div class="result-disclosure-body">
        <section v-if="result.confirmed_constraints">
          <h3>已确认条件</h3>
          <ul class="constraint-list">
            <li v-if="result.confirmed_constraints?.destination">目的地 · {{ result.confirmed_constraints.destination }}</li>
            <li v-if="result.confirmed_constraints?.departure_city">出发城市 · {{ result.confirmed_constraints.departure_city }}</li>
            <li v-if="result.confirmed_constraints?.start_date">出发日期 · {{ result.confirmed_constraints.start_date }}</li>
            <li v-if="result.confirmed_constraints?.end_date">返程日期 · {{ result.confirmed_constraints.end_date }}</li>
            <li v-if="result.confirmed_constraints?.days">天数 · {{ result.confirmed_constraints.days }} 天</li>
            <li v-if="result.confirmed_constraints?.travelers_count">人数 · {{ result.confirmed_constraints.travelers_count }} 人</li>
            <li v-if="result.confirmed_constraints?.budget">预算 · {{ result.confirmed_constraints.budget }} 元</li>
            <li v-if="result.confirmed_constraints?.must_visit_pois?.length">必去点位 · {{ result.confirmed_constraints.must_visit_pois.join(" / ") }}</li>
            <li v-if="result.confirmed_constraints?.transport_preferences?.length">交通偏好 · {{ result.confirmed_constraints.transport_preferences.join(" / ") }}</li>
          </ul>
        </section>

        <section v-if="result.alternatives?.length">
          <h3>替代路线</h3>
          <div v-for="item in result.alternatives" :key="item.title" class="alt-card">
            <MarkdownContent class="result-markdown result-markdown-title" :content="item.title" />
            <MarkdownContent class="result-markdown" :content="item.summary" />
            <MarkdownContent v-if="item.stop_names?.length" class="result-markdown" :content="`可替换点位：${item.stop_names.join(' / ')}`" />
            <MarkdownContent v-if="item.differences?.length" class="result-markdown" :content="item.differences.join('；')" />
          </div>
        </section>

        <section v-if="result.revision_notes?.length">
          <h3>修订线索</h3>
          <div v-for="note in result.revision_notes" :key="note.summary" class="alt-card">
            <MarkdownContent class="result-markdown result-markdown-title" :content="note.summary" />
            <MarkdownContent v-if="note.changes?.length" class="result-markdown" :content="note.changes.join('；')" />
          </div>
        </section>
      </div>
    </details>
  </div>
</template>
