<script setup>
import { computed } from "vue";

const props = defineProps({
  questions: {
    type: Array,
    default: () => []
  },
  templateText: {
    type: String,
    default: ""
  },
  mode: {
    type: String,
    default: "composer"
  }
});

const emit = defineEmits(["quick-prompt", "resolve"]);

const primaryActionLabel = computed(() => (
  props.mode === "form" ? "返回表单补齐" : "填入补充模板"
));
const helperCopy = computed(() => (
  props.mode === "form"
    ? "补齐这些字段后重新生成，当前已填写的内容会保留。"
    : "先把缺口填进输入框，再发送一次，系统会基于当前上下文继续生成。"
));

function applyTemplate() {
  if (!props.templateText) {
    return;
  }
  emit("quick-prompt", props.templateText);
}

function applySingleQuestion(question) {
  if (!question?.replyTemplate) {
    return;
  }
  emit("quick-prompt", question.replyTemplate);
}
</script>

<template>
  <article class="info-card clarification-bridge-card">
    <div class="clarification-bridge-header">
      <div class="clarification-bridge-copy">
        <p class="eyebrow">继续完成此方案</p>
        <h3>还差 {{ questions.length }} 项关键信息</h3>
        <p>{{ helperCopy }}</p>
      </div>

      <div class="clarification-bridge-actions">
        <button
          v-if="mode === 'composer'"
          class="secondary-button compact"
          type="button"
          :disabled="!templateText"
          @click="applyTemplate"
        >
          {{ primaryActionLabel }}
        </button>
        <button
          v-else
          class="primary-button compact"
          type="button"
          @click="emit('resolve')"
        >
          {{ primaryActionLabel }}
        </button>
      </div>
    </div>

    <ol class="clarification-question-list">
      <li
        v-for="question in questions"
        :key="question.id || `${question.field}-${question.index}`"
        class="clarification-question-item"
      >
        <span class="clarification-question-index">{{ question.index }}</span>
        <div class="clarification-question-body">
          <div class="clarification-question-meta">
            <strong>{{ question.fieldLabel }}</strong>
            <button
              v-if="mode === 'composer'"
              class="ghost-button compact-button"
              type="button"
              @click="applySingleQuestion(question)"
            >
              只补这项
            </button>
          </div>
          <p>{{ question.prompt }}</p>
          <p v-if="question.reason" class="clarification-question-reason">{{ question.reason }}</p>
        </div>
      </li>
    </ol>
  </article>
</template>
