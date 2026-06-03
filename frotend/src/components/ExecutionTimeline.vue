<script setup>
import { computed } from "vue";
import ProgressBar from "./ProgressBar.vue";

const providerLabels = {
  amap: "高德地图",
  baidu: "百度地图",
  "baidu-food": "百度本地生活",
  "baidu-hotel": "百度酒店候选",
  "heuristic-route": "启发式路段估算"
};

const formatProvider = (provider) => providerLabels[provider] || provider;
const statusLabels = {
  idle: "空闲",
  booting: "初始化中",
  queued: "排队中",
  running: "执行中",
  completed: "已完成",
  success: "已完成",
  degraded: "已完成",
  failed: "失败",
  pending: "待执行",
  ready: "已就绪",
  waiting_for_clarification: "等待补充信息"
};

const formatStatus = (status) => statusLabels[status] || status;
const workflowBlueprint = [
  { key: "normalize_input", title: "规范化用户输入" },
  { key: "assess_requirements", title: "判断回复模式" },
  { key: "fetch_live_data", title: "查询实时数据" },
  { key: "validate_live_data", title: "校验数据完备度" },
  { key: "plan_trip", title: "生成模型回复" },
  { key: "build_route_plan", title: "构建路段衔接" },
  { key: "verify_plan_consistency", title: "校验结果一致性" },
  { key: "assemble_output", title: "组装最终输出" }
];

const props = defineProps({
  status: {
    type: String,
    default: "idle"
  },
  compact: {
    type: Boolean,
    default: false
  },
  steps: {
    type: Array,
    default: () => []
  },
  error: {
    type: String,
    default: ""
  }
});

const normalizeStepStatus = (status) => (status === "degraded" ? "completed" : status);
const isRunning = computed(() => ["booting", "queued", "running"].includes(props.status));
const completedCount = computed(() => props.steps.filter((step) => normalizeStepStatus(step.status) === "completed").length);
const failedCount = computed(() => props.steps.filter((step) => step.status === "failed").length);
const activeStep = computed(() => props.steps.find((step) => ["running", "queued"].includes(step.status)) || props.steps.at(-1) || null);
const progressValue = computed(() => {
  if (!props.steps.length) {
    return isRunning.value ? 14 : 0;
  }
  const runningCount = props.steps.filter((step) => step.status === "running").length;
  const weightedProgress = completedCount.value + (runningCount ? 0.5 : 0);
  return Math.min(100, Math.round((weightedProgress / props.steps.length) * 100));
});
const progressFillStyle = computed(() => ({
  "--timeline-progress": `${progressValue.value}%`
}));
const totalCount = computed(() => stageItems.value.length || workflowBlueprint.length);
const headline = computed(() => {
  if (activeStep.value?.title) {
    return activeStep.value.title;
  }
  if (props.status === "waiting_for_clarification") {
    return "等待补充关键信息";
  }
  if (props.status === "completed") {
    return "规划结果已生成";
  }
  if (props.status === "failed") {
    return "规划执行失败";
  }
  return "正在准备规划运行";
});
const statusSummary = computed(() => {
  if (!props.steps.length) {
    return isRunning.value ? "正在建立本轮运行" : "暂无步骤";
  }
  if (failedCount.value) {
    return `${failedCount.value} 个步骤失败`;
  }
  return `${completedCount.value}/${props.steps.length} 个步骤完成`;
});
const pendingCopy = computed(() => {
  if (props.status === "failed") {
    return "运行已中断。";
  }
  if (props.status === "completed") {
    return "结果已写回。";
  }
  return "正在建立本轮运行。";
});
const subtleProgressLabel = computed(() => {
  if (!totalCount.value) {
    return "等待工作流启动";
  }
  if (failedCount.value) {
    return `${completedCount.value}/${totalCount.value} 已完成 · ${failedCount.value} 失败`;
  }
  return `${completedCount.value}/${totalCount.value} 节点已完成`;
});
const stageItems = computed(() => workflowBlueprint.map((stage) => {
  const matched = props.steps.find((item) => item.key === stage.key);
  if (matched) {
    return {
      ...matched,
      status: normalizeStepStatus(matched.status)
    };
  }

  const firstRunningIndex = props.steps.findIndex((item) => item.status === "running");
  const completedIndex = props.steps.findIndex((item) => item.key === stage.key);
  const stageIndex = workflowBlueprint.findIndex((item) => item.key === stage.key);
  let status = "pending";
  if (firstRunningIndex === -1 && isRunning.value && stageIndex === props.steps.length) {
    status = "running";
  }
  if (!isRunning.value && props.status === "completed" && stageIndex <= props.steps.length) {
    status = "completed";
  }
  if (completedIndex !== -1) {
    status = "completed";
  }
  return {
    ...stage,
    status,
    detail: matched?.detail || ""
  };
}));

function stepCaption(step) {
  if (normalizeStepStatus(step.status) === "completed") {
    return "已通过";
  }
  if (step.status === "failed") {
    return "已中断";
  }
  if (step.status === "running") {
    return "正在执行";
  }
  if (step.status === "queued") {
    return "等待调度";
  }
  return "尚未进入";
}
</script>

<template>
  <section class="panel timeline-panel live-timeline-panel" :data-status="status" :data-compact="compact ? 'true' : 'false'">
    <template v-if="compact">
      <div class="timeline-minimal-header">
        <div>
          <p class="eyebrow">LangGraph 工作流</p>
          <h2>{{ activeStep?.title || headline }}</h2>
        </div>
        <span class="status-pill" :data-status="status">{{ formatStatus(status) }}</span>
      </div>

      <div class="timeline-process-rail" :data-running="isRunning ? 'true' : 'false'">
        <div class="timeline-process-line"></div>
        <article
          v-for="(step, index) in stageItems"
          :key="step.key"
          class="timeline-process-node"
          :data-status="step.status"
        >
          <span class="timeline-process-index">{{ index + 1 }}</span>
          <div class="timeline-process-body">
            <strong>{{ step.title }}</strong>
            <p>{{ stepCaption(step) }}</p>
          </div>
        </article>
      </div>

      <div class="timeline-minimal-meta">
        <span>{{ subtleProgressLabel }}</span>
      </div>

      <p v-if="isRunning && activeStep?.detail" class="timeline-minimal-detail">{{ activeStep.detail }}</p>
      <p
        v-else-if="isRunning && activeStep?.provider_statuses?.length"
        class="timeline-minimal-detail"
      >
        {{ activeStep.provider_statuses.map((provider) => `${formatProvider(provider.provider)} ${formatStatus(provider.status)}`).join(" · ") }}
      </p>
    </template>

    <template v-else>
      <div class="panel-header">
        <div>
          <p class="eyebrow">生成进度</p>
          <h2>{{ headline }}</h2>
        </div>
        <span class="status-pill" :data-status="status">{{ formatStatus(status) }}</span>
      </div>

      <div class="timeline-summary-card timeline-stage-summary">
        <div class="timeline-summary-topline">
          <span>{{ statusSummary }}</span>
          <span v-if="activeStep">当前：{{ activeStep.title }}</span>
        </div>
        <ProgressBar
          track-class="timeline-progress-track"
          fill-class="timeline-progress-fill"
          :fill-style="progressFillStyle"
        />
        <p v-if="activeStep?.detail">{{ activeStep.detail }}</p>
        <p v-else-if="isRunning">正在同步 LangGraph 运行状态。</p>
      </div>

      <ol class="timeline timeline-live-list">
        <li v-for="step in stageItems" :key="step.key" class="timeline-item" :data-status="step.status">
          <div class="timeline-marker"></div>
          <div class="timeline-card">
            <header>
              <strong>{{ step.title }}</strong>
              <span class="status-pill" :data-status="step.status">{{ formatStatus(step.status) }}</span>
            </header>
            <p class="timeline-step-index">步骤 {{ stageItems.findIndex((item) => item.key === step.key) + 1 }} / {{ stageItems.length }}</p>
            <p v-if="step.detail">{{ step.detail }}</p>
            <p v-else-if="step.status === 'running'">正在执行当前节点。</p>
            <p v-else-if="step.status === 'pending'">等待进入该节点。</p>

            <div class="provider-grid" v-if="step.provider_statuses?.length">
              <span
                v-for="provider in step.provider_statuses"
                :key="provider.provider"
                class="provider-pill"
                :data-status="provider.status"
              >
                {{ formatProvider(provider.provider) }} · {{ formatStatus(provider.status) }}
              </span>
            </div>
          </div>
        </li>
      </ol>
    </template>

    <div v-if="!steps.length" class="timeline-pending-state">
      <span class="timeline-pending-dot"></span>
      <p>{{ pendingCopy }}</p>
    </div>

    <p class="error-message" v-if="error">{{ error }}</p>
  </section>
</template>
