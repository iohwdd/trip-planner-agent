<script setup>
import { computed, onMounted, ref, watch } from "vue";
import ChatWorkspace from "../components/ChatWorkspace.vue";
import SaveFeedbackBanner from "../components/SaveFeedbackBanner.vue";
import { useAssistant } from "../composables/useAssistant";
import { useAssistantLibrary } from "../composables/useAssistantLibrary";
import { useAuth } from "../composables/useAuth";

const auth = useAuth();
const assistant = useAssistant();
const library = useAssistantLibrary();
const { busy } = assistant;
const switchingConversationId = ref("");
const currentConversationId = computed(() => assistant.state.conversationId);
const recentItems = computed(() => library.state.items.slice(0, 8));
const hasConversations = computed(() => recentItems.value.length > 0);
const isSwitchingConversation = computed(() => Boolean(switchingConversationId.value));
const chatWorkspaceKey = computed(() => assistant.state.conversationId || "assistant-empty");
const identityKey = computed(() => (
  auth.state.authenticated && auth.state.user?.id
    ? `user:${auth.state.user.id}`
    : "guest"
));

onMounted(async () => {
  await Promise.all([
    assistant.initialize(),
    library.refreshConversations()
  ]);
});

watch(identityKey, async (nextKey, previousKey) => {
  if (!previousKey || nextKey === previousKey) {
    return;
  }
  await Promise.all([
    assistant.reconnectForIdentity(),
    library.refreshConversations()
  ]);
});

async function handleNewConversation() {
  await assistant.createConversation();
  await library.refreshConversations();
}

async function handleOpenConversation(conversationId) {
  if (conversationId === assistant.state.conversationId || switchingConversationId.value) {
    return;
  }
  switchingConversationId.value = conversationId;
  try {
    await assistant.openConversation(conversationId);
    void library.refreshConversations();
  } finally {
    switchingConversationId.value = "";
  }
}
</script>

<template>
  <section class="page-shell workspace-page assistant-page">
    <SaveFeedbackBanner
      :message="assistant.state.error"
      tone="error"
    />

    <main class="workspace chat-first-layout assistant-layout">
      <aside class="assistant-conversation-rail panel" aria-label="最近会话">
        <div class="assistant-rail-header">
          <div>
            <p class="eyebrow">智能助手</p>
            <h2>最近会话</h2>
          </div>
          <button
            class="primary-button compact"
            type="button"
            :disabled="busy || isSwitchingConversation"
            @click="handleNewConversation"
          >
            新建会话
          </button>
        </div>

        <div v-if="library.state.loading && !hasConversations" class="assistant-rail-empty">
          正在加载最近会话...
        </div>
        <div v-else-if="library.state.error && !hasConversations" class="assistant-rail-empty">
          {{ library.state.error }}
        </div>
        <div v-else-if="!hasConversations" class="assistant-rail-empty">
          还没有助手会话，点击右上角开始一条新的对话。
        </div>

        <div v-else class="assistant-conversation-list">
          <button
            v-for="item in recentItems"
            :key="item.conversation_id"
            class="assistant-conversation-card"
            :class="{
              'is-active': currentConversationId === item.conversation_id,
              'is-switching': switchingConversationId === item.conversation_id
            }"
            type="button"
            :disabled="isSwitchingConversation"
            @click="handleOpenConversation(item.conversation_id)"
          >
            <div class="assistant-conversation-topline">
              <strong :title="item.title">{{ item.title }}</strong>
              <span
                v-if="library.state.recentConversationId === item.conversation_id"
                class="assistant-conversation-badge"
              >
                最近
              </span>
            </div>
            <p :title="item.latest_summary || '暂无摘要'">
              {{ item.latest_summary || "暂无摘要" }}
            </p>
            <span class="assistant-conversation-meta">
              {{ item.message_count || 0 }} 条消息
            </span>
          </button>
        </div>
      </aside>

      <section
        class="workspace-chat assistant-chat-panel"
        :class="{ 'is-switching': isSwitchingConversation }"
        :aria-busy="isSwitchingConversation ? 'true' : 'false'"
      >
        <transition name="assistant-session-fade" mode="out-in">
          <ChatWorkspace
            :key="chatWorkspaceKey"
            mode="assistant"
            :messages="assistant.state.messages"
            v-model:composer="assistant.state.composer"
            session-status="ready"
            :busy="busy"
            :confirmed-constraints="null"
            :clarification-questions="[]"
            @send="assistant.sendMessage"
            @reset-session="assistant.resetConversation"
          />
        </transition>
        <div v-if="isSwitchingConversation" class="assistant-chat-switch-indicator" aria-hidden="true">
          <span class="assistant-chat-switch-dot"></span>
        </div>
      </section>
    </main>
  </section>
</template>
