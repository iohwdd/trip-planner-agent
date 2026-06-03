<script setup>
import { computed, onMounted, reactive } from "vue";
import { useRouter } from "vue-router";
import { useAssistant } from "../composables/useAssistant";
import { useAssistantLibrary } from "../composables/useAssistantLibrary";

const router = useRouter();
const assistant = useAssistant();
const library = useAssistantLibrary();
const renameState = reactive({
  conversationId: "",
  title: ""
});
const recentConversationId = computed(() => library.state.recentConversationId);

onMounted(async () => {
  await library.refreshConversations();
});

async function continueConversation(conversationId) {
  await assistant.openConversation(conversationId);
  router.push("/");
}

function startRename(item) {
  renameState.conversationId = item.conversation_id;
  renameState.title = item.title;
}

async function submitRename(conversationId) {
  await library.renameConversation(conversationId, renameState.title);
  renameState.conversationId = "";
  renameState.title = "";
}

async function removeConversation(conversationId) {
  await library.removeConversation(conversationId);
}
</script>

<template>
  <section class="page-shell library-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">助手会话</p>
        <h1>继续之前的智能助手对话</h1>
      </div>
      <p class="page-copy">
        这里保存的是独立于旅行工作台的助手对话。它们只负责问答、解释和想法整理，不再承担结构化规划生成。
      </p>
    </header>

    <div class="collection-state" v-if="library.state.loading">正在加载助手会话...</div>
    <div class="collection-state" v-else-if="library.state.error">{{ library.state.error }}</div>
    <div class="collection-state" v-else-if="library.state.items.length === 0">
      还没有助手会话，先去智能助手页发起一轮对话吧。
    </div>

    <div v-else class="collection-grid">
      <article v-for="item in library.state.items" :key="item.conversation_id" class="collection-card">
        <p class="eyebrow">{{ recentConversationId === item.conversation_id ? "最近会话" : "历史会话" }}</p>
        <h2>{{ item.title }}</h2>
        <p class="collection-copy">{{ item.latest_summary || "这条助手会话还没有形成摘要。" }}</p>

        <label class="field" v-if="renameState.conversationId === item.conversation_id">
          <span>新标题</span>
          <input v-model="renameState.title" placeholder="输入新的会话标题" />
        </label>

        <div class="card-actions">
          <button class="primary-button" type="button" @click="continueConversation(item.conversation_id)">
            继续对话
          </button>
          <button
            class="ghost-button"
            type="button"
            v-if="renameState.conversationId !== item.conversation_id"
            @click="startRename(item)"
          >
            重命名
          </button>
          <button
            class="secondary-button"
            type="button"
            v-else
            @click="submitRename(item.conversation_id)"
          >
            保存标题
          </button>
          <button class="ghost-button danger-text" type="button" @click="removeConversation(item.conversation_id)">
            删除
          </button>
        </div>
      </article>
    </div>
  </section>
</template>
