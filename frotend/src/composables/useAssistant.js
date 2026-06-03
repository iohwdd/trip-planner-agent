import { computed, reactive } from "vue";
import {
  createAssistantConversation,
  getAssistantConversation,
  getRecentAssistantConversation,
  sendAssistantMessage,
  streamAssistantMessage
} from "../lib/api";
import { useAuth } from "./useAuth";

const CONVERSATION_KEY_PREFIX = "trip-planner.assistant-conversation";

const defaultState = () => ({
  conversationId: "",
  title: "未命名助手会话",
  messages: [],
  composer: "",
  loading: false,
  error: "",
  flash: "",
  initPromise: null
});

const state = reactive(defaultState());

function canUseStorage() {
  return typeof window !== "undefined" && Boolean(window.localStorage);
}

function currentConversationStorageKey() {
  const auth = useAuth();
  if (auth.state.authenticated && auth.state.user?.id) {
    return `${CONVERSATION_KEY_PREFIX}.user.${auth.state.user.id}`;
  }
  return `${CONVERSATION_KEY_PREFIX}.guest`;
}

function readPersistedConversationId() {
  return canUseStorage()
    ? window.localStorage.getItem(currentConversationStorageKey()) || ""
    : "";
}

function persistConversationId(conversationId) {
  if (!canUseStorage()) {
    return;
  }
  if (!conversationId) {
    window.localStorage.removeItem(currentConversationStorageKey());
    return;
  }
  window.localStorage.setItem(currentConversationStorageKey(), conversationId);
}

function applyConversation(conversation) {
  state.conversationId = conversation.conversation_id;
  state.title = conversation.title || "未命名助手会话";
  state.messages = conversation.messages || [];
  state.error = "";
  persistConversationId(conversation.conversation_id);
}

export function useAssistant() {
  const hasMessages = computed(() => state.messages.length > 0);
  const busy = computed(() => state.loading);

  async function initialize({ force = false, createIfMissing = true } = {}) {
    if (!force && state.conversationId) {
      return state.conversationId;
    }
    if (state.initPromise) {
      return state.initPromise;
    }

    state.initPromise = (async () => {
      if (force) {
        persistConversationId("");
        Object.assign(state, defaultState());
      }

      const persistedId = readPersistedConversationId();
      if (persistedId) {
        try {
          const conversation = await getAssistantConversation(persistedId);
          applyConversation(conversation);
          return conversation.conversation_id;
        } catch (_error) {
          persistConversationId("");
        }
      }

      try {
        const recent = await getRecentAssistantConversation();
        applyConversation(recent);
        return recent.conversation_id;
      } catch (_error) {}

      if (!createIfMissing) {
        return "";
      }

      const created = await createAssistantConversation();
      state.conversationId = created.conversation_id;
      state.title = created.title || "未命名助手会话";
      persistConversationId(created.conversation_id);
      return created.conversation_id;
    })();

    try {
      return await state.initPromise;
    } finally {
      state.initPromise = null;
    }
  }

  async function refreshConversation() {
    if (!state.conversationId) {
      return null;
    }
    const conversation = await getAssistantConversation(state.conversationId);
    applyConversation(conversation);
    return conversation;
  }

  async function openConversation(conversationId) {
    const conversation = await getAssistantConversation(conversationId);
    applyConversation(conversation);
    return conversationId;
  }

  async function createConversation() {
    state.loading = true;
    state.error = "";
    state.flash = "";
    try {
      const conversation = await createAssistantConversation();
      applyConversation({
        ...conversation,
        messages: conversation.messages || []
      });
      state.composer = "";
      state.flash = "已创建新的助手会话。";
      return conversation.conversation_id;
    } catch (error) {
      state.error = error.message || "创建助手会话失败";
      throw error;
    } finally {
      state.loading = false;
    }
  }

  async function reconnectForIdentity() {
    persistConversationId("");
    Object.assign(state, defaultState());
    return initialize({ force: true });
  }

  function updateComposer(value) {
    state.composer = value;
  }

  async function sendMessage(rawMessage = state.composer) {
    const message = rawMessage.trim();
    if (!message || state.loading) {
      return;
    }
    state.loading = true;
    state.error = "";
    state.flash = "";
    try {
      await initialize();
      const userMessage = {
        message_id: `local-user-${Date.now()}`,
        role: "user",
        content: message,
        message_type: "text"
      };
      const placeholderId = `local-assistant-${Date.now()}`;
      state.messages = [
        ...state.messages,
        userMessage,
        {
          message_id: placeholderId,
          role: "assistant",
          content: "",
          message_type: "text"
        }
      ];
      state.composer = "";

      let receivedEvent = false;
      let completed = false;
      let finalConversation = null;

      try {
        await streamAssistantMessage(state.conversationId, message, {
          onEvent: async ({ event, data }) => {
            receivedEvent = true;

            if (event === "message.delta") {
              state.messages = state.messages.map((item) => (
                item.message_id === placeholderId
                  ? {
                      ...item,
                      content: data.content || `${item.content || ""}${data.delta || ""}`,
                      message_type: data.message_type || item.message_type
                    }
                  : item
              ));
              return;
            }

            if (event === "message.complete") {
              completed = true;
              finalConversation = data.conversation || null;
              if (data.conversation) {
                applyConversation(data.conversation);
                return;
              }
              state.messages = state.messages.map((item) => (
                item.message_id === placeholderId ? data.message : item
              ));
              return;
            }

            if (event === "message.error") {
              throw new Error(data.error || "助手消息发送失败");
            }
          }
        });
      } catch (error) {
        state.messages = state.messages.filter((item) => item.message_id !== placeholderId);
        if (!receivedEvent) {
          const conversation = await sendAssistantMessage(state.conversationId, message);
          applyConversation(conversation);
          return conversation;
        }
        if (!completed) {
          const conversation = await refreshConversation();
          if (conversation) {
            return conversation;
          }
        }
        throw error;
      }

      if (finalConversation) {
        return finalConversation;
      }
      return refreshConversation();
    } catch (error) {
      state.error = error.message || "助手消息发送失败";
      throw error;
    } finally {
      state.loading = false;
    }
  }

  async function resetConversation() {
    await createConversation();
  }

  function setFlash(message) {
    state.flash = message;
  }

  return {
    state,
    busy,
    hasMessages,
    initialize,
    refreshConversation,
    openConversation,
    createConversation,
    reconnectForIdentity,
    updateComposer,
    sendMessage,
    resetConversation,
    setFlash
  };
}

export function resetAssistantStateForTests() {
  Object.assign(state, defaultState());
  if (canUseStorage()) {
    Object.keys(window.localStorage)
      .filter((key) => key.startsWith(CONVERSATION_KEY_PREFIX))
      .forEach((key) => window.localStorage.removeItem(key));
  }
}
