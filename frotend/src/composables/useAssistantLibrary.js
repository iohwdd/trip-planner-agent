import { reactive } from "vue";
import {
  deleteAssistantConversation,
  listAssistantConversations,
  renameAssistantConversation
} from "../lib/api";

const defaultState = () => ({
  items: [],
  count: 0,
  recentConversationId: null,
  loading: false,
  error: ""
});

const state = reactive(defaultState());

export function useAssistantLibrary() {
  async function refreshConversations() {
    state.loading = true;
    state.error = "";
    try {
      const payload = await listAssistantConversations();
      state.items = payload.items || [];
      state.count = payload.count || state.items.length;
      state.recentConversationId = payload.recent_conversation_id || null;
      return state.items;
    } catch (error) {
      state.items = [];
      state.count = 0;
      state.recentConversationId = null;
      state.error = error.message || "助手会话列表加载失败";
      return [];
    } finally {
      state.loading = false;
    }
  }

  async function renameConversation(conversationId, title) {
    await renameAssistantConversation(conversationId, title);
    return refreshConversations();
  }

  async function removeConversation(conversationId) {
    await deleteAssistantConversation(conversationId);
    return refreshConversations();
  }

  return {
    state,
    refreshConversations,
    renameConversation,
    removeConversation
  };
}

export function resetAssistantLibraryForTests() {
  Object.assign(state, defaultState());
}
