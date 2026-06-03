const fs = require('fs');

const content = `<script setup>
import { computed } from "vue";
import { calculateTravelDays } from "../lib/plannerForm";

const props = defineProps({
  modelValue: { type: Object, required: true },
  secondary: { type: Boolean, default: false },
  busy: { type: Boolean, default: false }
});

const emit = defineEmits(["update:modelValue", "submit", "reset", "close"]);

function updateField(field, value) {
  emit("update:modelValue", { ...props.modelValue, [field]: value });
}

function updateNumberField(field, value) {
  const num = Number(value);
  emit("update:modelValue", {
    ...props.modelValue,
    [field]: Number.isNaN(num) || value === '' ? '' : num
  });
}

const inferredDays = computed(() => (
  calculateTravelDays(props.modelValue.start_date, props.modelValue.end_date)
));

function updateDateField(field, value) {
  const nextForm = { ...props.modelValue, [field]: value };
  const nextDays = calculateTravelDays(nextForm.start_date, nextForm.end_date);
  emit("update:modelValue", { ...nextForm, days: nextDays || "" });
}
</script>

<template>
  <section class="panel form-panel refined-panel" :data-secondary="secondary">
    <div class="panel-header planner-form-header refined-header">
      <div>
        <p class="eyebrow">{{ secondary ? "表单补充" : "智能工作台" }}</p>
        <h2>{{ secondary ? "补齐本轮条件" : "定制专属旅行方案" }}</h2>
        <p class="planner-form-subtitle">只需简单几步，告诉我们您的出行想法，AI即可为您推导最优路线、天数并生成完整计划。</p>
      </div>
      <button v-if="secondary" class="ghost-button compact planner-form-close" type="button" @click="$emit('close')">关闭</button>
    </div>

    <div class="planner-form-layout">
      <!-- 基础出行 -->
      <section class="planner-section refined-section">
        <div class="section-title-wrapper">
          <div class="section-icon">🌎</div>
          <div>
            <h3>出行基础</h3>
            <p>规划您的时间和目的地，这是生成行程的基石。</p>
          </div>
        </div>
        <div class="field-grid planner-field-grid planner-field-grid-primary">
          <label class="refined-field field-span-5">
            <span>📍 目的地</span>
            <input :value="modelValue.destination" @input="updateField('destination', $event.target.value)" placeholder="例如：巴黎、东京、三亚..." />
          </label>
          <label class="refined-field field-span-3">
            <span>🛫 出发城市</span>
            <input :value="modelValue.departure_city" @input="updateField('departure_city', $event.target.value)" placeholder="例如：北京" />
          </label>
          <label class="refined-field field-span-2">
            <span>👥 人数</span>
            <input type="number" min="1" max="20" :value="modelValue.travelers_count" @input="updateNumberField('travelers_count', $event.target.value)" placeholder="1" />
          </label>
          <label class="refined-field field-span-2">
            <span>💰 总预算(原币)</span>
            <input type="number" min="0" :value="modelValue.budget" @input="updateNumberField('budget', $event.target.value)" placeholder="选填" />
          </label>
          <label class="refined-field field-span-4">
            <span>📅 出发日期</span>
            <input type="date" :value="modelValue.start_date" @input="updateDateField('start_date', $event.target.value)" />
          </label>
          <label class="refined-field field-span-4">
            <span>📅 返程日期</span>
            <input type="date" :min="modelValue.start_date || undefined" :value="modelValue.end_date" @input="updateDateField('end_date', $event.target.value)" />
          </label>
          <label class="refined-field field-span-4 field-readonly">
            <span>⏱️ 获取天数</span>
            <input type="text" class="readonly-input" :value="inferredDays ? '共 ' + inferredDays + ' 天' : ''" readonly placeholder="系统智能计算中..." />
            <small class="field-hint">{{ inferredDays ? "✨ 已根据日期自动计算" : "选择起止日期后自动测算" }}</small>
          </label>
        </div>
      </section>

      <!-- 偏好 -->
      <section class="planner-section refined-section">
        <div class="section-title-wrapper pref">
          <div class="section-icon">🎨</div>
          <div>
            <h3>偏好与限制</h3>
            <p>定制化信息可以让我们筛选更符合您心意的景点和节奏。</p>
          </div>
        </div>
        <div class="field-grid planner-field-grid planner-field-grid-secondary">
          <label class="refined-field field-span-6">
            <span>🎯 兴趣偏好</span>
            <input :value="modelValue.interests" @input="updateField('interests', $event.target.value)" placeholder="想要打卡地标？还是深度看展、夜景？" />
          </label>
          <label class="refined-field field-span-6">
            <span>🚇 交通偏好</span>
            <input :value="modelValue.transport_preferences" @input="updateField('transport_preferences', $event.target.value)" placeholder="例如：依赖公共交通、多打车少走路" />
          </label>
          <label class="refined-field field-span-4">
            <span>🍜 美食偏好</span>
            <input :value="modelValue.food_preferences" @input="updateField('food_preferences', $event.target.value)" placeholder="例如：体验本地特色、偏爱咖啡馆" />
          </label>
          <label class="refined-field field-span-4">
            <span>🏨 住宿建议</span>
            <input :value="modelValue.hotel_preferences" @input="updateField('hotel_preferences', $event.target.value)" placeholder="例如：住在市中心、交通枢纽旁" />
          </label>
          <label class="refined-field field-span-4">
            <span>⚠️ 约束条件</span>
            <input :value="modelValue.constraints" @input="updateField('constraints', $event.target.value)" placeholder="例如：行程不要太赶、拒绝早起" />
          </label>
        </div>
      </section>

      <!-- 补充 -->
      <section class="planner-section refined-section">
        <div class="section-title-wrapper notes">
          <div class="section-icon">✍️</div>
          <div>
            <h3>补充说明</h3>
            <p>如果有更多细节要求，比如同行人特质或必去之地，在此畅所欲言。</p>
          </div>
        </div>
        <div class="field-grid planner-field-grid">
          <label class="refined-field field-full">
            <textarea rows="4" :value="modelValue.notes" @input="updateField('notes', $event.target.value)" placeholder="例如：带两位老人同行，需要每天午休；某天晚上必须要去听一场音乐会..." />
          </label>
        </div>
      </section>
    </div>

    <div class="form-actions action-bar">
      <button class="btn-reset" :disabled="busy" @click="$emit('reset')">清空重填</button>
      <button class="btn-submit" :disabled="busy" @click="$emit('submit')">
        <span v-if="busy">⏳ 系统演算中...</span>
        <span v-else>{{ secondary ? "🚀 更新到当前行程" : "🚀 开启智能规划" }}</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.refined-panel {
  background: rgba(255, 255, 255, 0.45);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.8);
  padding: 36px;
  border-radius: 28px;
  box-shadow: 0 12px 40px rgba(31, 38, 135, 0.08);
  width: 100%;
}

.refined-header {
  margin-bottom: 30px;
}

.refined-header h2 {
  font-size: 2.2rem;
  font-weight: 800;
  background: linear-gradient(135deg, #1e40af, #3b82f6);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin-bottom: 12px;
  letter-spacing: -0.5px;
}

.refined-header .planner-form-subtitle {
  color: #64748b;
  font-size: 1.05rem;
  max-width: 600px;
  line-height: 1.6;
}

.refined-section {
  background: #ffffff;
  border-radius: 20px;
  padding: 28px;
  margin-bottom: 24px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.03);
  border: 1px solid rgba(226, 232, 240, 0.8);
  transition: transform 0.25s ease, box-shadow 0.25s ease;
}

.refined-section:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.05);
  border-color: rgba(59, 130, 246, 0.2);
}

.section-title-wrapper {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px dashed #e2e8f0;
}

.section-icon {
  width: 48px;
  height: 48px;
  background: #f0fdf4;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  box-shadow: inset 0 2px 4px rgba(255,255,255,0.5);
}

.section-title-wrapper.pref .section-icon {
  background: #fef2f2;
}

.section-title-wrapper.notes .section-icon {
  background: #eff6ff;
}

.section-title-wrapper h3 {
  font-size: 1.25rem;
  font-weight: 700;
  margin: 0 0 4px 0;
  color: #1e293b;
}

.section-title-wrapper p {
  margin: 0;
  font-size: 0.9rem;
  color: #94a3b8;
}

.refined-field {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  grid-column: span 6;
}

.field-span-2 { grid-column: span 2; }
.field-span-3 { grid-column: span 3; }
.field-span-4 { grid-column: span 4; }
.field-span-5 { grid-column: span 5; }
.field-span-6 { grid-column: span 6; }
.field-full { grid-column: 1 / -1; }

.refined-field span {
  font-weight: 600;
  font-size: 0.9rem;
  color: #475569;
  display: flex;
  align-items: center;
  gap: 6px;
}

.refined-field input, .refined-field textarea {
  width: 100%;
  padding: 14px 18px;
  border: 2px solid #f1f5f9;
  border-radius: 14px;
  background: #f8fafc;
  color: #0f172a;
  font-size: 1.05rem;
  transition: all 0.25s ease;
  box-sizing: border-box;
}

.refined-field input:focus, .refined-field textarea:focus {
  background: #ffffff;
  border-color: #3b82f6;
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.15);
  outline: none;
}

.refined-field input::placeholder, .refined-field textarea::placeholder {
  color: #94a3b8;
  font-weight: 400;
}

.readonly-input {
  background: #f1f5f9 !important;
  color: #64748b !important;
  border-color: transparent !important;
  font-weight: 600;
  cursor: default;
}

.field-hint {
  color: #8b5cf6;
  font-size: 0.8rem;
  margin-top: 4px;
  font-weight: 500;
  padding-left: 2px;
}

.btn-submit {
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  color: white;
  font-size: 1.15rem;
  font-weight: 600;
  padding: 16px 40px;
  border-radius: 16px;
  border: none;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.3);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.btn-submit:hover:not(:disabled) {
  transform: translateY(-3px) scale(1.02);
  box-shadow: 0 12px 28px rgba(37, 99, 235, 0.4);
  background: linear-gradient(135deg, #3b82f6, #2563eb);
}

.btn-submit:active:not(:disabled) {
  transform: translateY(0) scale(1);
}

.btn-submit:disabled {
  background: #94a3b8;
  opacity: 0.7;
  cursor: not-allowed;
  box-shadow: none;
  transform: none;
}

.action-bar {
  display: flex;
  gap: 16px;
  margin-top: 10px;
  justify-content: flex-end;
  padding-top: 20px;
}

.btn-reset {
  background: #f1f5f9;
  color: #64748b;
  font-weight: 600;
  padding: 16px 32px;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 1.05rem;
}

.btn-reset:hover:not(:disabled) {
  background: #e2e8f0;
  color: #475569;
  border-color: #cbd5e1;
}

@media (max-width: 960px) {
  .refined-panel { padding: 24px; }
  .refined-field { grid-column: span 6 !important; }
}

@media (max-width: 720px) {
  .refined-panel { padding: 16px; }
  .refined-section { padding: 20px 16px; }
  .refined-field { grid-column: 1 / -1 !important; }
  .action-bar { flex-direction: column; align-items: stretch; }
  .btn-submit, .btn-reset { width: 100%; padding: 14px; }
}
</style>
`;
fs.writeFileSync('/Users/mac/workspace/trip-planer-agent/frotend/src/components/PlannerForm.vue', content);
console.log("Written!");