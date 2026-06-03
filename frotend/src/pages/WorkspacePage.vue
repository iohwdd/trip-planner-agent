<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import ChatWorkspace from "../components/ChatWorkspace.vue";
import ExecutionTimeline from "../components/ExecutionTimeline.vue";
import PlannerForm from "../components/PlannerForm.vue";
import ResultPanel from "../components/ResultPanel.vue";
import SaveFeedbackBanner from "../components/SaveFeedbackBanner.vue";
import WorkspaceStageHero from "../components/WorkspaceStageHero.vue";
import WorkspaceStatusBar from "../components/WorkspaceStatusBar.vue";
import { useAuth } from "../composables/useAuth";
import { usePlanner } from "../composables/usePlanner";
import { usePlanLibrary } from "../composables/usePlanLibrary";
import { useSessionLibrary } from "../composables/useSessionLibrary";

const router = useRouter();
const auth = useAuth();
const planner = usePlanner();
const { isRunning, clarificationQuestions } = planner;
const { resetConversation } = planner;
const plans = usePlanLibrary();
const sessions = useSessionLibrary();
const savingTarget = ref("");
const saveFeedbackTone = computed(() => {
  if (plans.state.loading) {
    return "pending";
  }
  if (plans.state.error) {
    return "error";
  }
  return "success";
});

const canSave = computed(() => Boolean(planner.state.sessionId && planner.state.result));
const assetSummary = computed(() => auth.state.assetSummary || {});
const sessionStatusLabel = computed(() => {
  if (isRunning.value) {
    return "正在生成中";
  }
  if (planner.state.result?.status === "clarification") {
    return "等待你补充关键信息";
  }
  if (canSave.value) {
    return "已有一版可继续细化的路线";
  }
  return "从一句模糊想法开始也可以";
});
const confirmedCount = computed(() => {
  const constraints = planner.state.confirmedConstraints || {};
  return Object.values(constraints).filter((value) => {
    if (value === null || value === "") {
      return false;
    }
    if (Array.isArray(value)) {
      return value.length > 0;
    }
    return true;
  }).length;
});
const compactStatusPills = computed(() => [
  auth.state.authenticated ? auth.userLabel : "游客模式",
  `${confirmedCount.value} 项条件已确认`,
  planner.state.result?.plan_state === "final" ? "接近最终版" : "持续迭代中"
]);
const hasContextSurface = computed(() => Boolean(
  isRunning.value
  || planner.state.result
  || planner.state.steps?.length
  || planner.state.error
));
const stageLabel = computed(() => {
  if (isRunning.value) {
    return "正在收敛路线";
  }
  if (planner.state.result?.status === "clarification") {
    return "等待补充信息";
  }
  if (canSave.value) {
    return "路线草案已形成";
  }
  return "开始一次新的旅行决策";
});
const stageHeadline = computed(() => {
  if (isRunning.value) {
    return "系统正在把你的约束整理成一版可判断的路线。";
  }
  if (planner.state.result?.status === "clarification") {
    return "先补关键条件，再继续把路线收敛下去。";
  }
  if (planner.state.result?.plan_state === "final") {
    return "这版路线已经接近最终出行版本。";
  }
  if (canSave.value) {
    return "你已经有一版草案，可以继续微调，也可以先保存。";
  }
  return "从一句模糊想法开始，让 Agent 帮你把旅行决策慢慢做清楚。";
});
const stageDescription = computed(() => {
  if (isRunning.value) {
    return "执行轨迹会持续告诉你系统现在检索了什么、确认了什么，以及什么时候适合继续提需求。";
  }
  if (planner.state.result?.status === "clarification") {
    return clarificationQuestions.value.length
      ? `当前还缺少 ${clarificationQuestions.value.length} 项关键信息；补齐后会继续生成更可执行的路线。`
      : "系统需要更多关键信息后才能继续生成更稳妥的路线。";
  }
  if (canSave.value) {
    return "先看结果是否满足当前决策，再决定继续修订、保存草案还是沉淀为最终方案。";
  }
  return assetSummary.value.recent_session_id
    ? "你也可以直接回到最近会话，接着上次停下来的地方继续。"
    : "聊天是主入口，快捷表单只负责快速补齐条件。";
});
const stageMetrics = computed(() => [
  `${confirmedCount.value} 项条件已确认`,
  `会话 ${assetSummary.value.session_count || 0}`,
  auth.state.authenticated ? `方案 ${assetSummary.value.plan_count || 0}` : "游客模式"
]);
const stageActions = computed(() => {
  const actions = [];
  if (planner.state.result?.status === "clarification" && firstClarificationPrompt.value) {
    actions.push({
      key: "apply-first-clarification",
      label: "补第一条关键信息",
      tone: "primary",
      disabled: false
    });
  }
  if (!planner.state.result && assetSummary.value.recent_session_id) {
    actions.push({
      key: "open-sessions",
      label: "回到最近会话",
      tone: "ghost",
      disabled: false
    });
  }
  if (canSave.value) {
    actions.push({
      key: "save-draft",
      label: plans.state.loading && savingTarget.value === "draft" ? "草案保存中..." : "先保存为草案",
      tone: "secondary",
      disabled: isRunning.value || plans.state.loading
    });
  }
  if (canSave.value && auth.state.authenticated) {
    actions.push({
      key: "save-final",
      label: plans.state.loading && savingTarget.value === "final" ? "最终方案保存中..." : "保存为最终方案",
      tone: "primary",
      disabled: isRunning.value || plans.state.loading
    });
  }
  if (canSave.value && !auth.state.authenticated) {
    actions.push({
      key: "login-to-save",
      label: "登录后保存资产",
      tone: "primary",
      disabled: false
    });
  }
  actions.push(
    {
      key: "open-form",
      label: "用表单补齐条件",
      tone: "ghost",
      disabled: false
    },
    {
      key: "open-profile",
      label: "查看账户与资产概览",
      tone: "ghost",
      disabled: false
    }
  );
  return actions;
});
const firstClarificationPrompt = computed(() => {
  const question = clarificationQuestions.value[0];
  if (!question) {
    return "";
  }
  if (question.field === "destination") {
    return "目的地先定在上海。";
  }
  if (question.field === "departure_city") {
    return "我从杭州出发。";
  }
  if (question.field === "start_date" || question.field === "departure_date") {
    return "计划 2026-04-10 出发。";
  }
  if (question.field === "days") {
    return "计划安排 2 天。";
  }
  if (question.field === "travelers_count") {
    return "这次一共 2 个人出行。";
  }
  if (question.field === "budget") {
    return "预算控制在 3000 元左右。";
  }
  if (question.field === "must_visit_pois") {
    return "想保留外滩和博物馆。";
  }
  return question.prompt;
});

onMounted(async () => {
  await planner.initialize();
  await sessions.refreshSessions();
  if (auth.state.authenticated) {
    await plans.refreshPlans();
  }
});

async function savePlan(status) {
  if (!canSave.value) {
    planner.setFlash("当前还没有可保存的路线结果。");
    return;
  }
  savingTarget.value = status;
  planner.setFlash(status === "final" ? "正在保存最终方案..." : "正在保存草案...");
  try {
    await plans.saveCurrentPlan(
      planner.state.sessionId,
      status,
      planner.state.sessionTitle
    );
    planner.setFlash(plans.state.info || "方案已保存。");
    await sessions.refreshSessions();
    if (auth.state.authenticated) {
      await plans.refreshPlans();
    }
  } catch (_error) {
    planner.setFlash(plans.state.error || "方案保存失败。");
  } finally {
    savingTarget.value = "";
  }
}

function goToSessions() {
  router.push("/sessions");
}

function goToPlans() {
  router.push("/plans");
}

function openProfile() {
  router.push("/profile");
}

function applySuggestedReply() {
  if (!firstClarificationPrompt.value) {
    return;
  }
  planner.updateComposer(firstClarificationPrompt.value);
}

function handleStageAction(actionKey) {
  if (actionKey === "apply-first-clarification") {
    applySuggestedReply();
    return;
  }
  if (actionKey === "open-sessions") {
    goToSessions();
    return;
  }
  if (actionKey === "save-draft") {
    savePlan("draft");
    return;
  }
  if (actionKey === "save-final") {
    savePlan("final");
    return;
  }
  if (actionKey === "login-to-save") {
    auth.openDialog("登录后可以把当前路线保存为草案或最终方案，并长期管理你的旅行资产。");
    return;
  }
  if (actionKey === "open-form") {
    planner.toggleForm(true);
    return;
  }
  if (actionKey === "open-profile") {
    openProfile();
  }
}

</script>

<template>
  <section class="page-shell workspace-page">
    <WorkspaceStatusBar
      :session-status-label="sessionStatusLabel"
      :compact-status-pills="compactStatusPills"
      :can-save="canSave"
      :busy="isRunning"
      :saving="plans.state.loading"
      :saving-target="savingTarget"
      @reset-session="resetConversation"
      @open-sessions="goToSessions"
      @open-plans="goToPlans"
      @save-draft="savePlan('draft')"
      @save-final="savePlan('final')"
    />

    <SaveFeedbackBanner
      :message="planner.state.flash"
      :tone="saveFeedbackTone"
    />

    <WorkspaceStageHero
      :label="stageLabel"
      :headline="stageHeadline"
      :description="stageDescription"
      :metrics="stageMetrics"
      :actions="stageActions"
      :tone="isRunning ? 'running' : 'idle'"
      @action="handleStageAction"
    />

    <main class="workspace chat-first-layout workspace-route workspace-workbench" :data-context-visible="hasContextSurface ? 'true' : 'false'">
      <section class="workspace-chat">
        <ChatWorkspace
          :messages="planner.state.messages"
          v-model:composer="planner.state.composer"
          :session-status="planner.state.sessionStatus"
          :busy="isRunning"
          :confirmed-constraints="planner.state.confirmedConstraints"
          :clarification-questions="clarificationQuestions"
          @send="planner.sendMessage"
          @toggle-form="planner.toggleForm"
          @reset-session="planner.resetConversation"
        />

        <transition name="drawer-slide">
          <PlannerForm
            v-if="planner.state.formOpen"
            :model-value="planner.state.form"
            :busy="isRunning"
            secondary
            @update:model-value="planner.state.form = $event"
            @submit="planner.submitForm"
            @reset="planner.resetForm"
            @close="planner.toggleForm"
          />
        </transition>
      </section>

      <aside v-if="hasContextSurface" class="workspace-context-column" aria-label="结果与过程">
        <ResultPanel
          :result="planner.state.result"
          @quick-prompt="planner.updateComposer"
        />
        <ExecutionTimeline
          :status="planner.state.turnStatus === 'idle' ? planner.state.sessionStatus : planner.state.turnStatus"
          :steps="planner.state.steps"
          :error="planner.state.error"
        />
      </aside>
    </main>
  </section>
</template>
