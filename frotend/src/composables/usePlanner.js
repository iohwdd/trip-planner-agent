import { computed, reactive } from "vue";
import {
  createChatSession,
  createChatTurn,
  getChatSession,
  getChatTurn,
  getRecentChatSession,
  streamChatTurn
} from "../lib/api";
import { buildPlannerRequestPayload, defaultPlannerForm } from "../lib/plannerForm";
import { useAuth } from "./useAuth";

const SESSION_KEY_PREFIX = "trip-planner.active-session";

const defaultState = () => ({
  form: defaultPlannerForm(),
  formOpen: false,
  composer: "",
  sessionId: "",
  sessionTitle: "未命名会话",
  sessionStatus: "booting",
  activeTurnId: "",
  turnStatus: "idle",
  turnPhase: "idle",
  messages: [],
  confirmedConstraints: null,
  result: null,
  steps: [],
  error: "",
  flash: "",
  streamConnected: false,
  pollTimer: null,
  initPromise: null
});

const state = reactive(defaultState());

function canUseStorage() {
  return typeof window !== "undefined" && Boolean(window.localStorage);
}

function currentSessionStorageKey() {
  const auth = useAuth();
  if (auth.state.authenticated && auth.state.user?.id) {
    return `${SESSION_KEY_PREFIX}.user.${auth.state.user.id}`;
  }
  return `${SESSION_KEY_PREFIX}.guest`;
}

function readPersistedSessionId() {
  return canUseStorage() ? window.localStorage.getItem(currentSessionStorageKey()) || "" : "";
}

function persistSessionId(sessionId) {
  if (!canUseStorage()) {
    return;
  }
  if (!sessionId) {
    window.localStorage.removeItem(currentSessionStorageKey());
    return;
  }
  window.localStorage.setItem(currentSessionStorageKey(), sessionId);
}

function cloneForm(form) {
  return { ...form };
}

function extractTurnResult(turn) {
  return turn?.result || turn?.result_payload || null;
}

function deriveTurnPhase(turn) {
  if (!turn) {
    return "idle";
  }
  if (["queued", "running", "failed"].includes(turn.status)) {
    return turn.status;
  }
  const result = extractTurnResult(turn);
  if (result?.status === "clarification") {
    return "clarification";
  }
  if (result?.status === "failed") {
    return "failed";
  }
  return turn.status === "completed" ? "completed" : turn.status;
}

function stopPolling() {
  if (state.pollTimer) {
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
}

function clearWorkspaceState() {
  stopPolling();
  state.sessionId = "";
  state.sessionTitle = "未命名会话";
  state.sessionStatus = "booting";
  state.activeTurnId = "";
  state.turnStatus = "idle";
  state.turnPhase = "idle";
  state.messages = [];
  state.confirmedConstraints = null;
  state.result = null;
  state.steps = [];
  state.error = "";
  state.streamConnected = false;
}

function resetExecution() {
  stopPolling();
  state.activeTurnId = "";
  state.turnStatus = "idle";
  state.turnPhase = "idle";
  state.steps = [];
  state.error = "";
  state.streamConnected = false;
}

function appendLocalUserMessage(content) {
  state.messages = [
    ...state.messages,
    {
      message_id: `local-user-${Date.now()}`,
      role: "user",
      content,
      message_type: "text"
    }
  ];
}

function upsertStep(step) {
  const index = state.steps.findIndex((item) => item.key === step.key);
  if (index >= 0) {
    state.steps.splice(index, 1, step);
    return;
  }
  state.steps = [...state.steps, step];
}

function ensureStreamingAssistantMessage(turnId, messageType = "result") {
  const index = state.messages.findIndex(
    (item) => item.turn_id === turnId && item.role === "assistant"
  );
  if (index >= 0) {
    return { item: state.messages[index], index };
  }

  const message = {
    message_id: `stream-assistant-${turnId}`,
    role: "assistant",
    content: "",
    turn_id: turnId,
    message_type: messageType
  };
  state.messages = [...state.messages, message];
  return { item: message, index: state.messages.length - 1 };
}

function applyStreamResult(result, phase = state.turnPhase) {
  if (!result) {
    return;
  }
  state.result = result;
  state.confirmedConstraints = result.confirmed_constraints || state.confirmedConstraints;
  state.turnPhase = phase;
}

async function handleStreamEvent({ event, data }) {
  switch (event) {
    case "turn.created":
      state.activeTurnId = data.turn_id;
      state.turnStatus = data.status || "queued";
      state.turnPhase = data.phase || "queued";
      state.sessionStatus = data.session_status || "running";
      state.streamConnected = true;
      return;
    case "turn.status":
      state.turnStatus = data.status || state.turnStatus;
      state.turnPhase = data.phase || state.turnPhase;
      state.sessionStatus = data.session_status || state.sessionStatus;
      return;
    case "turn.step":
      if (data.step) {
        upsertStep(data.step);
      }
      return;
    case "turn.result":
      applyStreamResult(data.result, data.phase || state.turnPhase);
      return;
    case "message.delta": {
      const { item, index } = ensureStreamingAssistantMessage(data.turn_id, data.message_type || "result");
      const next = {
        ...item,
        content: data.content || `${item.content || ""}${data.delta || ""}`,
        message_type: data.message_type || item.message_type
      };
      state.messages.splice(index, 1, next);
      return;
    }
    case "message.complete": {
      const message = data.message;
      if (!message) {
        return;
      }
      const { index } = ensureStreamingAssistantMessage(data.turn_id, message.message_type || "result");
      state.messages.splice(index, 1, message);
      return;
    }
    case "turn.complete":
      state.turnStatus = data.status || "completed";
      state.turnPhase = data.phase || "completed";
      applyStreamResult(data.result, data.phase || "completed");
      state.streamConnected = false;
      await refreshSession();
      return;
    case "turn.error":
      state.turnStatus = data.status || "failed";
      state.turnPhase = data.phase || "failed";
      state.error = data.error || "回合执行失败";
      state.streamConnected = false;
      await refreshSession().catch(() => {});
      return;
    default:
      return;
  }
}

function applySession(session) {
  state.sessionId = session.session_id;
  state.sessionTitle = session.title || "未命名会话";
  state.sessionStatus = session.status || "idle";
  state.messages = session.messages || [];
  state.confirmedConstraints = session.confirmed_constraints || null;
  state.result = session.latest_result || null;
  state.error = "";
  state.streamConnected = false;
  persistSessionId(session.session_id);

  const latestTurn = [...(session.turns || [])].at(-1);
  if (latestTurn) {
    state.turnStatus = latestTurn.status;
    state.turnPhase = deriveTurnPhase(latestTurn);
    state.steps = latestTurn.steps || [];
    state.error = latestTurn.error || "";
    state.activeTurnId = session.active_turn_id || latestTurn.turn_id;
    const turnResult = extractTurnResult(latestTurn);
    if (turnResult) {
      state.result = turnResult;
    }
    return;
  }

  state.turnStatus = "idle";
  state.turnPhase = "idle";
  state.activeTurnId = "";
  state.steps = [];
}

async function loadSession(sessionId) {
  stopPolling();
  const session = await getChatSession(sessionId);
  applySession(session);
  return session;
}

async function hydrateExistingOrRecentSession() {
  const persistedSessionId = readPersistedSessionId();
  if (persistedSessionId) {
    try {
      return await loadSession(persistedSessionId);
    } catch (_error) {
      persistSessionId("");
    }
  }

  try {
    const recent = await getRecentChatSession();
    applySession(recent);
    return recent;
  } catch (_error) {
    return null;
  }
}

export function usePlanner() {
  const hasResult = computed(() => Boolean(state.result));
  const isRunning = computed(() =>
    ["queued", "running"].includes(state.turnStatus) || state.sessionStatus === "running" || state.streamConnected
  );
  const clarificationQuestions = computed(
    () => state.result?.clarification_questions || []
  );

  function maybeSchedulePolling() {
    if (
      ["queued", "running"].includes(state.turnStatus)
      && state.activeTurnId
    ) {
      schedulePoll(state.activeTurnId);
    }
  }

  async function refreshSession() {
    if (!state.sessionId) {
      return null;
    }
    const session = await loadSession(state.sessionId);
    maybeSchedulePolling();
    return session;
  }

  async function initialize(options = {}) {
    const { force = false, createIfMissing = true } = options;
    if (!force && state.sessionId) {
      return state.sessionId;
    }
    if (state.initPromise) {
      return state.initPromise;
    }

    state.initPromise = (async () => {
      if (force) {
        clearWorkspaceState();
      }

      const existing = await hydrateExistingOrRecentSession();
      if (existing) {
        maybeSchedulePolling();
        return existing.session_id;
      }

      if (!createIfMissing) {
        return "";
      }

      const session = await createChatSession();
      state.sessionId = session.session_id;
      state.sessionTitle = session.title || "未命名会话";
      state.sessionStatus = session.status || "idle";
      persistSessionId(session.session_id);
      await refreshSession().catch(() => {});
      return session.session_id;
    })();

    try {
      return await state.initPromise;
    } finally {
      state.initPromise = null;
    }
  }

  async function reconnectForIdentity() {
    stopPolling();
    if (state.sessionId) {
      try {
        await loadSession(state.sessionId);
        maybeSchedulePolling();
        return state.sessionId;
      } catch (_error) {
        persistSessionId("");
      }
    }
    return initialize({ force: true });
  }

  function updateComposer(value) {
    state.composer = value;
  }

  function toggleForm(forceValue) {
    state.formOpen = typeof forceValue === "boolean" ? forceValue : !state.formOpen;
  }

  async function sendMessage(rawMessage = state.composer) {
    const message = rawMessage.trim();
    if (!message) {
      return;
    }
    await initialize();
    resetExecution();
    appendLocalUserMessage(message);
    state.composer = "";
    state.flash = "";

    try {
      await streamChatTurn(state.sessionId, { message }, { onEvent: handleStreamEvent });
    } catch (error) {
      try {
        const turn = await createChatTurn(state.sessionId, { message });
        state.activeTurnId = turn.turn_id;
        state.turnStatus = turn.status;
        state.turnPhase = turn.phase || turn.status;
        await refreshSession();
        stopPolling();
        await pollTurn(turn.turn_id);
      } catch (fallbackError) {
        state.error = fallbackError.message || error.message || "消息发送失败";
        state.turnStatus = "failed";
        state.turnPhase = "failed";
      }
    }
  }

  async function submitForm() {
    await initialize();
    resetExecution();
    state.formOpen = false;
    state.flash = "";

    try {
      await streamChatTurn(
        state.sessionId,
        {
          request: buildPlannerRequestPayload(state.form)
        },
        { onEvent: handleStreamEvent }
      );
    } catch (error) {
      try {
        const turn = await createChatTurn(state.sessionId, {
          request: buildPlannerRequestPayload(state.form)
        });
        state.activeTurnId = turn.turn_id;
        state.turnStatus = turn.status;
        state.turnPhase = turn.phase || turn.status;
        await refreshSession();
        stopPolling();
        await pollTurn(turn.turn_id);
      } catch (fallbackError) {
        state.error = fallbackError.message || error.message || "表单提交失败";
        state.turnStatus = "failed";
        state.turnPhase = "failed";
      }
    }
  }

async function pollTurn(turnId = state.activeTurnId) {
    if (!state.sessionId || !turnId) {
      return;
    }

    try {
      const turn = await getChatTurn(state.sessionId, turnId);
      state.turnStatus = turn.status;
      state.turnPhase = turn.phase || deriveTurnPhase(turn);
      state.steps = turn.steps || [];
      state.error = turn.error || "";
      const turnResult = extractTurnResult(turn);
      if (turnResult) {
        state.result = turnResult;
      }

      if (["queued", "running"].includes(turn.status)) {
        schedulePoll(turnId);
        return;
      }

      await refreshSession();
    } catch (error) {
      state.error = error.message || "轮询回合失败";
      state.turnStatus = "failed";
      state.turnPhase = "failed";
    }
  }

function schedulePoll(turnId) {
  stopPolling();
  state.pollTimer = setTimeout(async () => {
    await pollTurn(turnId);
  }, 1400);
}

  async function resetConversation() {
    persistSessionId("");
    clearWorkspaceState();
    state.composer = "";
    state.flash = "";
    await initialize({ force: true });
  }

  async function openSession(sessionId) {
    resetExecution();
    await loadSession(sessionId);
    state.flash = "已切换到选中的历史会话。";
    return sessionId;
  }

  function resetForm() {
    state.form = cloneForm(defaultPlannerForm());
  }

  function setFlash(message) {
    state.flash = message;
  }

  return {
    state,
    hasResult,
    isRunning,
    clarificationQuestions,
    handleStreamEvent,
    initialize,
    reconnectForIdentity,
    openSession,
    refreshSession,
    updateComposer,
    toggleForm,
    sendMessage,
    submitForm,
    resetConversation,
    resetForm,
    pollTurn,
    setFlash
  };
}

export function resetPlannerStateForTests() {
  stopPolling();
  Object.assign(state, defaultState());
  if (canUseStorage()) {
    Object.keys(window.localStorage)
      .filter((key) => key.startsWith(SESSION_KEY_PREFIX))
      .forEach((key) => window.localStorage.removeItem(key));
  }
}
