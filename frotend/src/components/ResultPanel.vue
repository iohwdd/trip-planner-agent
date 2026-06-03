<script setup>
import { computed, ref, toRef, watch } from "vue";
import ResultClarificationPanel from "./ResultClarificationPanel.vue";
import ResultConfidenceBand from "./ResultConfidenceBand.vue";
import ResultHeroCard from "./ResultHeroCard.vue";
import ResultOverviewTab from "./ResultOverviewTab.vue";
import ResultResourcesTab from "./ResultResourcesTab.vue";
import ResultRiskTab from "./ResultRiskTab.vue";
import ResultRouteTab from "./ResultRouteTab.vue";
import ResultSourcesPanel from "./ResultSourcesPanel.vue";
import { useResultPresentation } from "../composables/useResultPresentation";

const props = defineProps({
  result: {
    type: Object,
    default: null
  },
  clarificationMode: {
    type: String,
    default: "composer"
  }
});

const emit = defineEmits(["quick-prompt", "resolve-clarification"]);

const activeTab = ref("overview");
const tabItems = [
  { key: "overview", label: "概览" },
  { key: "route", label: "路线" },
  { key: "risk", label: "预算与风险" },
  { key: "resources", label: "候选资源" }
];
const resultRef = toRef(props, "result");
const {
  budgetFillStyle,
  budgetRows,
  clarificationItems,
  clarificationReplyTemplate,
  confidenceDescription,
  confidenceGuidanceCards,
  confidenceHeadline,
  confidenceMetrics,
  formatCurrency,
  formatDistance,
  formatDuration,
  formatSeverity,
  formatStopKind,
  formatTimeSlot,
  planStateLabels,
  previewSegments,
  previewStops,
  resultConfidenceTone,
  routeDays,
  statusLabels,
  summaryPills
} = useResultPresentation(resultRef);

const showClarificationPanel = computed(() => (
  props.result?.assistant_mode !== "general"
  && props.result?.status === "clarification"
  && clarificationItems.value.length > 0
));
const visibleTabItems = computed(() => {
  if (showClarificationPanel.value) {
    const items = [{ key: "overview", label: "概览" }];
    if (props.result?.source_references?.length) {
      items.push({ key: "resources", label: "候选资源" });
    }
    return items;
  }
  return tabItems;
});

const activeRouteDay = ref(1);

const activeRouteDayData = computed(() => {
  if (!routeDays.value.length) {
    return null;
  }
  return routeDays.value.find((item) => item.day === activeRouteDay.value) || routeDays.value[0];
});

watch(
  () => props.result?.generated_at || props.result?.trip_summary,
  () => {
    activeTab.value = "overview";
    activeRouteDay.value = routeDays.value[0]?.day || 1;
  }
);

watch(
  visibleTabItems,
  (tabs) => {
    if (!tabs.some((tab) => tab.key === activeTab.value)) {
      activeTab.value = tabs[0]?.key || "overview";
    }
  },
  { immediate: true }
);

watch(
  routeDays,
  (days) => {
    if (!days.length) {
      activeRouteDay.value = 1;
      return;
    }
    if (!days.some((item) => item.day === activeRouteDay.value)) {
      activeRouteDay.value = days[0].day;
    }
  },
  { immediate: true }
);
</script>

<template>
  <section class="panel result-panel modern-result-panel">
    <div class="panel-header glass-header">
      <div>
        <p class="eyebrow">工作台结论</p>
        <h2>{{ result?.assistant_mode === "general" ? "对话回复结果" : "智能旅游规划方案" }}</h2>
      </div>
      <div v-if="result && result.assistant_mode !== 'general'" class="result-tabs modern-tabs">
        <button
          v-for="tab in visibleTabItems"
          :key="tab.key"
          class="result-tab modern-tab"
          :class="{ 'is-active': activeTab === tab.key }"
          type="button"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>
    </div>

    <div v-if="!result" class="result-empty glass-card">
      <div class="empty-icon">🏖️</div>
      <p>智能体正在等待您的指令，这里将展示生成的规划结构。</p>
      <ul class="result-empty-list">
        <li>👉 先告诉我目的地、天数或节奏偏好。</li>
        <li>👉 执行过程中会实时显示当前步骤和阶段结果。</li>
        <li>👉 产出草案后，可继续围绕预算、顺路程度和雨天方案微调。</li>
      </ul>
    </div>

    <template v-else>
      <div v-if="result.assistant_mode === 'general'" class="glass-card general-answer-card">
        <h3>通用回答</h3>
        <p>这一轮是通用问答模式，智能助理已直接用中文回复你的问题。</p>
        <p>如果你接下来开始提供目的地、天数、预算或必去点位，它会自动切回旅行规划模式。</p>
      </div>

      <div class="result-split-layout" v-else>
        <!-- 左侧：AI 会话与洞察面板 (Chat / Summary / Clarification) -->
        <aside class="result-ai-column">
          <div class="ai-column-inner">
            <ResultHeroCard
              :result="result"
              :status-labels="statusLabels"
              :plan-state-labels="planStateLabels"
              :summary-pills="summaryPills"
            />

            <ResultClarificationPanel
              v-if="showClarificationPanel"
              :questions="clarificationItems"
              :template-text="clarificationReplyTemplate"
              :mode="clarificationMode"
              @quick-prompt="emit('quick-prompt', $event)"
              @resolve="emit('resolve-clarification')"
            />
            
            <ResultConfidenceBand
              v-if="activeTab === 'overview'"
              :tone="resultConfidenceTone"
              :headline="confidenceHeadline"
              :description="confidenceDescription"
              :metrics="confidenceMetrics"
              :guidance-cards="confidenceGuidanceCards"
            />
          </div>
        </aside>

        <!-- 右侧：详情面板 (Detail Content) -->
        <main class="result-detail-column glass-card">
          <transition name="fade-slide" mode="out-in">
            <ResultOverviewTab
              v-if="activeTab === 'overview' && result.status !== 'clarification'"
              :result="result"
              :preview-stops="previewStops"
              :preview-segments="previewSegments"
              :budget-rows="budgetRows"
              :budget-fill-style="budgetFillStyle"
              :format-time-slot="formatTimeSlot"
              :format-currency="formatCurrency"
            />

            <ResultRouteTab
              v-else-if="activeTab === 'route'"
              :result="result"
              :route-days="routeDays"
              :active-route-day="activeRouteDay"
              :active-route-day-data="activeRouteDayData"
              :format-time-slot="formatTimeSlot"
              :format-stop-kind="formatStopKind"
              :format-duration="formatDuration"
              :format-distance="formatDistance"
              @select-day="activeRouteDay = $event"
            />

            <ResultRiskTab
              v-else-if="activeTab === 'risk'"
              :result="result"
              :refinement-actions="refinementActions"
              :format-currency="formatCurrency"
              :format-severity="formatSeverity"
              @quick-prompt="emit('quick-prompt', $event)"
            />

            <ResultResourcesTab
              v-else-if="activeTab === 'resources'"
              :result="result"
            />
          </transition>
        </main>
      </div>

      <ResultSourcesPanel v-if="result.source_references && result.source_references.length" :source-references="result.source_references" class="sources-panel-modern" />
    </template>
  </section>
</template>
