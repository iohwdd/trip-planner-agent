<script setup>
import { computed, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import ResultPanel from "../components/ResultPanel.vue";
import { useAuth } from "../composables/useAuth";
import { usePlanLibrary } from "../composables/usePlanLibrary";
import { usePlanner } from "../composables/usePlanner";
import { useSessionLibrary } from "../composables/useSessionLibrary";
import { useWorkbench } from "../composables/useWorkbench";

const props = defineProps({
  planId: {
    type: String,
    required: true
  }
});

const router = useRouter();
const auth = useAuth();
const plans = usePlanLibrary();
const planner = usePlanner();
const sessions = useSessionLibrary();
const workbench = useWorkbench();

const resultSnapshot = computed(() => plans.state.activePlan?.result_snapshot || null);

async function loadPlan() {
  if (!auth.state.authenticated) {
    return;
  }
  try {
    await plans.loadPlan(props.planId);
  } catch (_error) {}
}

onMounted(loadPlan);
watch(() => props.planId, loadPlan);

async function continueEditing() {
  if (plans.state.activePlan?.source_type === "workbench_run") {
    workbench.applyPlanSeed(plans.state.activePlan.constraints_snapshot || {});
    router.push("/workbench");
    return;
  }
  try {
    const payload = await plans.continueEditing(props.planId);
    if (!payload?.session_id) {
      return;
    }
    await planner.openSession(payload.session_id);
    await sessions.refreshSessions();
    router.push("/");
  } catch (_error) {}
}

async function removePlan() {
  try {
    await plans.removePlan(props.planId);
    router.push("/plans");
  } catch (_error) {}
}
</script>

<template>
  <section class="page-shell detail-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">方案详情</p>
        <h1>{{ plans.state.activePlan?.title || "历史方案快照" }}</h1>
      </div>
      <p class="page-copy">
        这里展示的是保存当时的约束快照和结果快照。这个页面的价值不是归档，而是帮助你判断是否应当从该版本继续修订。
      </p>
    </header>

    <article v-if="!auth.state.authenticated" class="collection-state auth-callout">
      登录后才能查看方案详情。
      <button class="primary-button" type="button" @click="auth.openDialog('登录后即可查看保存过的旅行方案详情。')">
        立即登录
      </button>
    </article>

    <div v-else-if="plans.state.loading" class="collection-state">正在加载方案详情...</div>
    <div v-else-if="plans.state.error" class="collection-state">{{ plans.state.error }}</div>
    <div v-else-if="!plans.state.activePlan" class="collection-state">未找到对应的方案。</div>

    <div v-else class="detail-layout">
      <article class="collection-card sticky-summary">
        <p class="eyebrow">版本 {{ plans.state.activePlan.version }}</p>
        <h2>{{ plans.state.activePlan.status === "final" ? "接近出行版本的最终方案" : "仍可继续推敲的草案版本" }}</h2>
        <p class="collection-copy">
          {{
            plans.state.activePlan.status === "final"
              ? "适合拿来做最终行前确认；若需求改变，继续修订会基于这版内容新建会话。"
              : "这版更适合继续调整预算、点位和节奏，再决定是否沉淀为最终方案。"
          }}
        </p>
        <div class="summary-pills">
          <span class="constraint-pill">
            来源类型 · {{ plans.state.activePlan.source_type === "workbench_run" ? "流程工作台" : "聊天规划" }}
          </span>
          <span class="constraint-pill" v-if="plans.state.activePlan.constraints_snapshot?.destination">
            目的地 · {{ plans.state.activePlan.constraints_snapshot.destination }}
          </span>
          <span class="constraint-pill" v-if="plans.state.activePlan.constraints_snapshot?.days">
            天数 · {{ plans.state.activePlan.constraints_snapshot.days }}
          </span>
          <span class="constraint-pill" v-if="plans.state.activePlan.constraints_snapshot?.budget">
            预算 · {{ plans.state.activePlan.constraints_snapshot.budget }}
          </span>
          <span class="constraint-pill" v-if="plans.state.activePlan.source_session_id">
            来源会话 · {{ plans.state.activePlan.source_session_id }}
          </span>
          <span class="constraint-pill" v-if="plans.state.activePlan.source_job_id">
            来源运行 · {{ plans.state.activePlan.source_job_id }}
          </span>
        </div>
        <div class="card-actions">
          <button class="primary-button" type="button" @click="continueEditing">继续修订</button>
          <button class="ghost-button danger-text" type="button" @click="removePlan">删除方案</button>
        </div>
      </article>

      <ResultPanel :result="resultSnapshot" />
    </div>
  </section>
</template>
