<script setup>
import { computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAuth } from "../composables/useAuth";
import { usePlanner } from "../composables/usePlanner";
import { usePlanLibrary } from "../composables/usePlanLibrary";
import { useSessionLibrary } from "../composables/useSessionLibrary";
import { useWorkbench } from "../composables/useWorkbench";

const router = useRouter();
const auth = useAuth();
const planner = usePlanner();
const plans = usePlanLibrary();
const sessions = useSessionLibrary();
const workbench = useWorkbench();
const draftCount = computed(() => plans.state.statusCounts?.draft || 0);
const finalCount = computed(() => plans.state.statusCounts?.final || 0);

onMounted(async () => {
  await plans.refreshPlans();
});

async function continueEditing(item) {
  if (item.source_type === "workbench_run") {
    workbench.applyPlanSeed(item.constraints_snapshot || {});
    router.push("/workbench");
    return;
  }
  try {
    const payload = await plans.continueEditing(item.plan_id);
    if (!payload?.session_id) {
      return;
    }
    await planner.openSession(payload.session_id);
    await sessions.refreshSessions();
    router.push("/");
  } catch (_error) {}
}

async function removePlan(planId) {
  try {
    await plans.removePlan(planId);
  } catch (_error) {}
}

function openDetail(planId) {
  router.push(`/plans/${planId}`);
}

function planStatusLabel(item) {
  return item.status === "final" ? "最终方案" : "草案版本";
}

function planContinuationLabel(item) {
  if (item.status === "final") {
    return "这版已经适合作为出行决策依据；如果需求有变化，继续修订会从这个版本派生新的可编辑会话。";
  }
  return "这版草案适合继续压缩预算、调整节奏或替换点位，并在需要时沉淀成最终方案。";
}

function sourceTypeLabel(item) {
  return item.source_type === "workbench_run" ? "流程工作台" : "聊天规划";
}
</script>

<template>
  <section class="page-shell library-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">我的方案</p>
        <h1>草案、最终版与继续修订入口</h1>
      </div>
      <p class="page-copy">
        这里保存的是已经沉淀下来的路线判断结果。先确认哪一版最接近最终出行决策，再决定继续修订还是作为最终方案保留。
      </p>
    </header>

    <div class="summary-pills" v-if="auth.state.authenticated">
      <span class="constraint-pill">草案 {{ draftCount }}</span>
      <span class="constraint-pill">最终版 {{ finalCount }}</span>
      <span class="constraint-pill">总计 {{ plans.state.count }}</span>
    </div>

    <article v-if="!auth.state.authenticated" class="collection-state auth-callout">
      登录后才能查看和管理历史方案。
      <button class="primary-button" type="button" @click="auth.openDialog('登录后即可查看历史草案和最终方案。')">
        立即登录
      </button>
    </article>

    <div v-else-if="plans.state.loading" class="collection-state">正在加载方案列表...</div>
    <div v-else-if="plans.state.error" class="collection-state">{{ plans.state.error }}</div>
    <div v-else-if="plans.state.items.length === 0" class="collection-state">
      你还没有保存任何方案，先回到工作台生成一份草案吧。
    </div>

    <div v-else class="collection-grid">
      <article v-for="item in plans.state.items" :key="item.plan_id" class="collection-card">
        <p class="eyebrow">版本 {{ item.version }}</p>
        <h2>{{ item.title }}</h2>
        <p class="collection-copy">{{ item.result_summary || "这版方案还没有记录更详细的摘要。" }}</p>
        <p class="collection-copy">{{ planContinuationLabel(item) }}</p>
        <div class="summary-pills">
          <span class="constraint-pill">方案语义 · {{ planStatusLabel(item) }}</span>
          <span class="constraint-pill" v-if="item.constraints_snapshot?.destination">
            目的地 · {{ item.constraints_snapshot.destination }}
          </span>
          <span class="constraint-pill" v-if="item.constraints_snapshot?.days">
            天数 · {{ item.constraints_snapshot.days }}
          </span>
          <span class="constraint-pill">来源类型 · {{ sourceTypeLabel(item) }}</span>
          <span class="constraint-pill" v-if="item.source_session_id">来源会话 · {{ item.source_session_id }}</span>
          <span class="constraint-pill" v-if="item.source_job_id">来源运行 · {{ item.source_job_id }}</span>
        </div>

        <div class="card-actions">
          <button class="primary-button" type="button" @click="openDetail(item.plan_id)">
            查看详情
          </button>
          <button class="secondary-button" type="button" @click="continueEditing(item)">
            继续修订
          </button>
          <button class="ghost-button danger-text" type="button" @click="removePlan(item.plan_id)">
            删除
          </button>
        </div>
      </article>
    </div>
  </section>
</template>
