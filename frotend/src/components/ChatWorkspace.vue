<script setup>
import MarkdownContent from "./MarkdownContent.vue";
import { useStickyAutoScroll } from "../composables/useStickyAutoScroll";

const props = defineProps({
  messages: {
    type: Array,
    default: () => []
  },
  mode: {
    type: String,
    default: "travel"
  },
  composer: {
    type: String,
    default: ""
  },
  sessionStatus: {
    type: String,
    default: "idle"
  },
  busy: {
    type: Boolean,
    default: false
  },
  confirmedConstraints: {
    type: Object,
    default: null
  },
  clarificationQuestions: {
    type: Array,
    default: () => []
  }
});

const emit = defineEmits([
  "update:composer",
  "send",
  "toggle-form",
  "reset-session"
]);

const {
  bottomAnchor: chatBottomAnchor,
  scrollContent: chatScrollContent,
  scrollRegion: chatScrollRegion,
  scheduleScrollToBottom
} = useStickyAutoScroll(
  () => [props.messages.length, props.messages.at(-1)?.content, props.busy],
  {
    stickWhen: () => props.busy,
    forceOnChange: () => props.busy,
    hasContent: () => props.messages.length > 0
  }
);

function onSubmit() {
  scheduleScrollToBottom({ force: true });
  emit("send");
}
</script>

<template>
  <section class="chat-workspace minimal-chat-workspace">
    <div ref="chatScrollRegion" class="chat-scroll-region">
      <div ref="chatScrollContent" class="chat-scroll-content">
        <div v-if="messages.length" class="chat-log">
          <article
            v-for="message in messages"
            :key="message.message_id"
            class="message-card"
            :data-role="message.role"
            :data-type="message.message_type"
          >
            <span class="message-role">{{ message.role === "user" ? "你" : "助手" }}</span>
            <MarkdownContent
              class="message-content"
              :tone="message.role === 'user' ? 'inverse' : ''"
              :content="message.content || (busy && message.role === 'assistant' ? '...' : '')"
            />
          </article>
        </div>
        <div v-else class="chat-empty chat-empty-minimal">
          <p>暂无消息</p>
        </div>
        <div ref="chatBottomAnchor" class="chat-bottom-anchor" aria-hidden="true"></div>
      </div>
    </div>

    <div class="composer-panel composer-panel-minimal">
      <textarea
        class="composer-textarea"
        rows="3"
        :value="composer"
        :disabled="busy"
        placeholder="输入内容"
        @input="$emit('update:composer', $event.target.value)"
        @keydown.meta.enter.prevent="onSubmit"
        @keydown.ctrl.enter.prevent="onSubmit"
      />

      <div class="composer-footer composer-footer-bar">
        <div class="composer-actions-left">
          <span class="composer-shortcut">⌘ / Ctrl + Enter</span>
        </div>
        <button class="primary-button" type="button" :disabled="busy || !composer.trim()" @click="onSubmit">
          {{ busy ? "处理中..." : "发送" }}
        </button>
      </div>
    </div>
  </section>
</template>
