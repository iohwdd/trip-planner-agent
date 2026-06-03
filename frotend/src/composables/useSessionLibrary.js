import { reactive } from "vue";
import {
  deleteChatSession,
  listChatSessions,
  renameChatSession
} from "../lib/api";

const defaultState = () => ({
  items: [],
  count: 0,
  statusCounts: {},
  recentSessionId: null,
  loading: false,
  error: ""
});

const state = reactive(defaultState());

export function useSessionLibrary() {
  async function refreshSessions() {
    state.loading = true;
    state.error = "";
    try {
      const payload = await listChatSessions();
      state.items = payload.items || [];
      state.count = payload.count || state.items.length;
      state.statusCounts = payload.status_counts || {};
      state.recentSessionId = payload.recent_session_id || null;
      return state.items;
    } catch (error) {
      state.items = [];
      state.count = 0;
      state.statusCounts = {};
      state.recentSessionId = null;
      state.error = error.message || "会话列表加载失败";
      return [];
    } finally {
      state.loading = false;
    }
  }

  async function renameSession(sessionId, title) {
    await renameChatSession(sessionId, title);
    return refreshSessions();
  }

  async function removeSession(sessionId) {
    await deleteChatSession(sessionId);
    return refreshSessions();
  }

  return {
    state,
    refreshSessions,
    renameSession,
    removeSession
  };
}

export function resetSessionLibraryForTests() {
  Object.assign(state, defaultState());
}
