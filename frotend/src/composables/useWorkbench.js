import { computed, reactive } from "vue";
import { createPlanRun, getPlanRun, streamPlanRun } from "../lib/api";
import {
  buildPlannerRequestPayload,
  defaultPlannerForm,
  seedPlannerFormFromConstraints
} from "../lib/plannerForm";

const defaultState = () => ({
  form: defaultPlannerForm(),
  view: "form",
  runId: "",
  runStatus: "idle",
  steps: [],
  result: null,
  error: "",
  flash: "",
  pollTimer: null
});

const state = reactive(defaultState());

function applyConstraintSeed(constraints = {}) {
  state.form = seedPlannerFormFromConstraints(constraints);
}

function stopPolling() {
  if (state.pollTimer) {
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
}

function upsertStep(step) {
  const existingIndex = state.steps.findIndex((item) => item.key === step.key);
  if (existingIndex === -1) {
    state.steps = [...state.steps, step];
    return;
  }
  state.steps = state.steps.map((item, index) => (index === existingIndex ? step : item));
}

export function useWorkbench() {
  const isRunning = computed(() => ["queued", "running"].includes(state.runStatus));
  const hasResult = computed(() => Boolean(state.result));
  const isRunView = computed(() => state.view === "run");

  async function pollRun(runId = state.runId) {
    if (!runId) {
      return null;
    }
    try {
      const run = await getPlanRun(runId);
      state.runId = run.run_id;
      state.runStatus = run.status;
      state.steps = run.steps || [];
      state.result = run.result || null;
      state.error = run.error || "";
      if (["queued", "running"].includes(run.status)) {
        schedulePoll(runId);
      }
      return run;
    } catch (error) {
      state.error = error.message || "规划结果加载失败";
      state.runStatus = "failed";
      return null;
    }
  }

  function schedulePoll(runId) {
    stopPolling();
    state.pollTimer = setTimeout(async () => {
      await pollRun(runId);
    }, 900);
  }

  async function submitForm() {
    stopPolling();
    state.error = "";
    state.flash = "";
    state.view = "run";
    state.steps = [];
    state.result = null;
    state.runStatus = "queued";
    const requestPayload = buildPlannerRequestPayload(state.form);

    let receivedStreamEvent = false;
    try {
      await streamPlanRun(requestPayload, {
        onEvent: async ({ event, data }) => {
          receivedStreamEvent = true;

          if (event === "run.created") {
            state.runId = data.run_id;
            state.runStatus = data.status || "queued";
            return;
          }

          if (event === "run.status") {
            state.runId = data.run_id || state.runId;
            state.runStatus = data.status || state.runStatus;
            return;
          }

          if (event === "run.step" && data.step) {
            upsertStep(data.step);
            return;
          }

          if (event === "run.result" && data.result) {
            state.result = data.result;
            return;
          }

          if (event === "run.complete") {
            state.runStatus = data.status || "completed";
            if (data.result) {
              state.result = data.result;
            }
            return;
          }

          if (event === "run.error") {
            state.runStatus = "failed";
            state.error = data.error || "规划执行失败";
          }
        }
      });

      if (state.runId) {
        await pollRun(state.runId);
      }
      return state.runId;
    } catch (error) {
      if (!receivedStreamEvent) {
        const payload = await createPlanRun(requestPayload);
        state.runId = payload.run_id;
        state.runStatus = payload.status;
        await pollRun(payload.run_id);
        return payload.run_id;
      }
      state.error = error.message || "规划执行失败";
      throw error;
    }
  }

  function resetForm() {
    state.form = defaultPlannerForm();
  }

  function returnToForm() {
    state.view = "form";
  }

  function applyPlanSeed(constraints) {
    applyConstraintSeed(constraints);
    stopPolling();
    state.view = "form";
    state.runId = "";
    state.runStatus = "idle";
    state.steps = [];
    state.result = null;
    state.error = "";
    state.flash = "已把历史方案约束填充到流程工作台。";
  }

  function clearRun() {
    stopPolling();
    state.view = "form";
    state.runId = "";
    state.runStatus = "idle";
    state.steps = [];
    state.result = null;
    state.error = "";
    state.flash = "";
  }

  function setFlash(message) {
    state.flash = message;
  }

  return {
    state,
    isRunning,
    hasResult,
    isRunView,
    submitForm,
    pollRun,
    resetForm,
    returnToForm,
    applyPlanSeed,
    clearRun,
    setFlash
  };
}

export function resetWorkbenchStateForTests() {
  stopPolling();
  Object.assign(state, defaultState());
}
