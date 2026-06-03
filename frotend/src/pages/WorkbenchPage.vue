<script setup>
import { computed, ref } from "vue";
import ExecutionTimeline from "../components/ExecutionTimeline.vue";
import PlannerForm from "../components/PlannerForm.vue";
import ResultPanel from "../components/ResultPanel.vue";
import SaveFeedbackBanner from "../components/SaveFeedbackBanner.vue";
import WorkbenchCompletionBanner from "../components/WorkbenchCompletionBanner.vue";
import WorkbenchRunHeader from "../components/WorkbenchRunHeader.vue";
import { useAuth } from "../composables/useAuth";
import { usePlanLibrary } from "../composables/usePlanLibrary";
import { useWorkbench } from "../composables/useWorkbench";

const auth = useAuth();
const plans = usePlanLibrary();
const workbench = useWorkbench();
const savingTarget = ref("");
const running = computed(() => Boolean(workbench.isRunning.value));
const isRunView = computed(() => Boolean(workbench.isRunView.value));
const showTimeline = computed(() => Boolean(workbench.state.runId));
const showResult = computed(() => Boolean(workbench.state.result));
const isClarificationResult = computed(() => workbench.state.result?.status === "clarification");
const canPersistResult = computed(() => showResult.value && !["clarification", "failed"].includes(workbench.state.result?.status));
const showCompletionNotice = computed(() => canPersistResult.value && !running.value);
const timelineStatus = computed(() => {
  if (running.value) {
    return workbench.state.runStatus;
  }
  if (isClarificationResult.value) {
    return "waiting_for_clarification";
  }
  if (showResult.value) {
    return "completed";
  }
  return workbench.state.runStatus;
});
const runHeaderShowsResult = computed(() => showResult.value && !isClarificationResult.value);
const runHeaderStatusLabel = computed(() => {
  if (running.value) {
    return "正在生成";
  }
  if (isClarificationResult.value) {
    return "等待补充信息";
  }
  if (workbench.state.error) {
    return "运行异常";
  }
  return "正在生成";
});
const saveFeedbackTone = computed(() => {
  if (plans.state.loading) {
    return "pending";
  }
  if (plans.state.error) {
    return "error";
  }
  return "success";
});

async function savePlan(status) {
  if (!workbench.state.runId || !canPersistResult.value) {
    workbench.setFlash("当前还没有可保存的工作台结果。");
    return;
  }
  if (!auth.state.authenticated) {
    auth.openDialog("登录后可保存工作台方案。");
    return;
  }
  savingTarget.value = status;
  workbench.setFlash(status === "final" ? "正在保存最终方案..." : "正在保存草案...");
  try {
    await plans.saveRunPlan(workbench.state.runId, status);
    workbench.setFlash(plans.state.info || "方案已保存。");
  } catch (_error) {
    workbench.setFlash(plans.state.error || "方案保存失败。");
  } finally {
    savingTarget.value = "";
  }
}
</script>

<template>
  <section class="page-shell workspace-page workbench-page workbench-page-streamlined">
    <main v-if="!isRunView" class="workspace workbench-form-stage">
      <section class="workspace-chat workbench-form-column workbench-form-column-full">
        <PlannerForm
          :model-value="workbench.state.form"
          :busy="running"
          @update:model-value="workbench.state.form = $event"
          @submit="workbench.submitForm"
          @reset="workbench.resetForm"
        />
      </section>
    </main>

    <main v-else class="workspace workbench-result-stage">
      <section class="workbench-run-shell">
        <WorkbenchRunHeader
          :show-result="runHeaderShowsResult"
          :status-label="runHeaderStatusLabel"
          @back="workbench.returnToForm"
        />

        <ExecutionTimeline
          v-if="showTimeline"
          compact
          :status="timelineStatus"
          :steps="workbench.state.steps"
          :error="workbench.state.error"
        />

        <WorkbenchCompletionBanner
          v-if="showCompletionNotice"
          :summary="workbench.state.result?.trip_summary || '旅行方案已生成'"
          :saving="plans.state.loading"
          :saving-target="savingTarget"
          @save-draft="savePlan('draft')"
          @save-final="savePlan('final')"
        />

        <SaveFeedbackBanner
          :message="workbench.state.flash"
          :tone="saveFeedbackTone"
        />

        <ResultPanel
          v-if="showResult"
          :result="workbench.state.result"
          clarification-mode="form"
          @resolve-clarification="workbench.returnToForm"
        />
        <p v-if="workbench.state.error" class="error-message">{{ workbench.state.error }}</p>
      </section>
    </main>
  </section>
</template>
