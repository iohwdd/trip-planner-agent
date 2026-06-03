import { reactive } from "vue";
import {
  deleteTripPlan,
  getTripPlan,
  listTripPlans,
  resumeTripPlan,
  saveRunTripPlan,
  saveTripPlan
} from "../lib/api";
import { useAuth } from "./useAuth";

const defaultState = () => ({
  items: [],
  count: 0,
  statusCounts: {},
  activePlan: null,
  loading: false,
  error: "",
  info: ""
});

const state = reactive(defaultState());

export function usePlanLibrary() {
  const auth = useAuth();

  async function refreshPlans() {
    if (!auth.state.authenticated) {
      state.items = [];
      state.count = 0;
      state.statusCounts = {};
      state.activePlan = null;
      state.error = "";
      return [];
    }
    state.loading = true;
    state.error = "";
    try {
      const payload = await listTripPlans();
      state.items = payload.items || [];
      state.count = payload.count || state.items.length;
      state.statusCounts = payload.status_counts || {};
      return state.items;
    } catch (error) {
      state.items = [];
      state.count = 0;
      state.statusCounts = {};
      state.error = error.message || "方案列表加载失败";
      return [];
    } finally {
      state.loading = false;
    }
  }

  async function saveCurrentPlan(sessionId, status, title = "") {
    if (!auth.requireLogin("登录后才能保存旅行方案并继续管理版本。")) {
      state.error = "保存方案前请先登录。";
      return null;
    }
    state.loading = true;
    state.error = "";
    try {
      const plan = await saveTripPlan(sessionId, { status, title: title || null });
      state.info = status === "final" ? "已保存为最终方案。" : "已保存为草案。";
      await refreshPlans();
      return plan;
    } catch (error) {
      state.error = error.message || "保存方案失败";
      throw error;
    } finally {
      state.loading = false;
    }
  }

  async function saveRunPlan(runId, status, title = "") {
    if (!auth.requireLogin("登录后才能保存旅行方案并继续管理版本。")) {
      state.error = "保存方案前请先登录。";
      return null;
    }
    state.loading = true;
    state.error = "";
    try {
      const plan = await saveRunTripPlan(runId, { status, title: title || null });
      state.info = status === "final" ? "已保存为最终方案。" : "已保存为草案。";
      await refreshPlans();
      return plan;
    } catch (error) {
      state.error = error.message || "保存方案失败";
      throw error;
    } finally {
      state.loading = false;
    }
  }

  async function loadPlan(planId) {
    if (!auth.requireLogin("登录后才能查看历史方案详情。")) {
      return null;
    }
    state.loading = true;
    state.error = "";
    try {
      const plan = await getTripPlan(planId);
      state.activePlan = plan;
      return plan;
    } catch (error) {
      state.activePlan = null;
      state.error = error.message || "方案详情加载失败";
      throw error;
    } finally {
      state.loading = false;
    }
  }

  async function removePlan(planId) {
    if (!auth.requireLogin("登录后才能删除旅行方案。")) {
      return false;
    }
    await deleteTripPlan(planId);
    await refreshPlans();
    if (state.activePlan?.plan_id === planId) {
      state.activePlan = null;
    }
    return true;
  }

  async function continueEditing(planId) {
    if (!auth.requireLogin("登录后才能基于历史方案继续修订。")) {
      return null;
    }
    const payload = await resumeTripPlan(planId);
    state.info = "已基于历史方案创建新的继续修订会话。";
    return payload;
  }

  return {
    state,
    refreshPlans,
    saveCurrentPlan,
    saveRunPlan,
    loadPlan,
    removePlan,
    continueEditing
  };
}

export function resetPlanLibraryForTests() {
  Object.assign(state, defaultState());
}
