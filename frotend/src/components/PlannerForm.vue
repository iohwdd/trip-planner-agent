<script setup>
import { computed, reactive, watch } from "vue";
import { calculateTravelDays } from "../lib/plannerForm";

const CITY_SUGGESTIONS = [
  "北京市",
  "上海市",
  "广州市",
  "深圳市",
  "杭州市",
  "杭州市萧山区",
  "杭州萧山机场",
  "成都市",
  "重庆市",
  "西安市",
  "南京市",
  "苏州市",
  "武汉市",
  "长沙市",
  "青岛市",
  "厦门市",
  "三亚市",
  "昆明市",
  "大理市",
  "丽江市",
  "香港特别行政区",
  "澳门特别行政区"
];

const TAG_GROUPS = {
  interests: ["城市漫步", "博物馆", "亲子", "夜景", "自然风光", "展览", "美食打卡", "轻松慢游"],
  transport_preferences: ["地铁优先", "少步行", "打车优先", "高铁往返", "适合长辈", "路线紧凑"],
  food_preferences: ["特色小吃", "本地老店", "米其林", "咖啡馆", "夜宵", "清淡口味", "适合家庭"],
  hotel_preferences: ["地铁方便", "安静休息", "夜景", "亲子友好", "核心商圈", "性价比优先"],
  constraints: ["不赶行程", "少折返", "午后休息", "避开排队", "雨天可替换", "预算克制"]
};

const SURPRISE_PACKS = [
  {
    interests: ["城市漫步", "夜景", "博物馆"],
    food_preferences: ["特色小吃", "咖啡馆"],
    transport_preferences: ["地铁优先", "路线紧凑"],
    hotel_preferences: ["地铁方便", "核心商圈"],
    constraints: ["不赶行程"]
  },
  {
    interests: ["自然风光", "轻松慢游", "美食打卡"],
    food_preferences: ["本地老店", "清淡口味"],
    transport_preferences: ["打车优先", "少步行"],
    hotel_preferences: ["安静休息", "性价比优先"],
    constraints: ["午后休息", "少折返"]
  },
  {
    interests: ["亲子", "展览", "博物馆"],
    food_preferences: ["适合家庭", "特色小吃"],
    transport_preferences: ["适合长辈", "地铁优先"],
    hotel_preferences: ["亲子友好", "地铁方便"],
    constraints: ["避开排队", "雨天可替换"]
  }
];

const props = defineProps({
  modelValue: {
    type: Object,
    required: true
  },
  secondary: {
    type: Boolean,
    default: false
  },
  busy: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits(["update:modelValue", "submit", "reset", "close"]);

const errors = reactive({
  destination: "",
  start_date: "",
  end_date: ""
});
const flashedFields = reactive({});
let localMutationFields = new Set();
let highlightTimerMap = new Map();

const inferredDays = computed(() => (
  calculateTravelDays(props.modelValue.start_date, props.modelValue.end_date)
));

function markLocalFields(fields) {
  localMutationFields = new Set(fields);
}

function emitUpdatedForm(nextForm, localFields = []) {
  markLocalFields(localFields);
  emit("update:modelValue", nextForm);
}

function clearFieldError(field) {
  if (field in errors) {
    errors[field] = "";
  }
}

function updateField(field, value) {
  clearFieldError(field);
  emitUpdatedForm(
    {
      ...props.modelValue,
      [field]: value
    },
    [field]
  );
}

function updateDateField(field, value) {
  clearFieldError("start_date");
  clearFieldError("end_date");
  const nextForm = {
    ...props.modelValue,
    [field]: value
  };
  const nextDays = calculateTravelDays(nextForm.start_date, nextForm.end_date);
  emitUpdatedForm(
    {
      ...nextForm,
      days: nextDays || ""
    },
    [field, "days"]
  );
}

function parseTags(value) {
  if (!value) {
    return [];
  }
  return String(value)
    .split(/[，,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function serializeTags(items) {
  return [...new Set(items.map((item) => String(item).trim()).filter(Boolean))].join(", ");
}

function hasTag(field, tag) {
  return parseTags(props.modelValue[field]).includes(tag);
}

function toggleTag(field, tag) {
  const current = parseTags(props.modelValue[field]);
  const next = current.includes(tag)
    ? current.filter((item) => item !== tag)
    : [...current, tag];
  updateField(field, serializeTags(next));
}

function setTravelersCount(nextValue) {
  const normalized = Math.max(1, Math.min(20, Number(nextValue) || 1));
  updateField("travelers_count", normalized);
}

function applySurprisePack() {
  const pack = SURPRISE_PACKS[Math.floor(Math.random() * SURPRISE_PACKS.length)];
  emitUpdatedForm(
    {
      ...props.modelValue,
      interests: serializeTags(pack.interests),
      food_preferences: serializeTags(pack.food_preferences),
      transport_preferences: serializeTags(pack.transport_preferences),
      hotel_preferences: serializeTags(pack.hotel_preferences),
      constraints: serializeTags(pack.constraints)
    },
    [
      "interests",
      "food_preferences",
      "transport_preferences",
      "hotel_preferences",
      "constraints"
    ]
  );
}

function validateForm() {
  const nextErrors = {
    destination: "",
    start_date: "",
    end_date: ""
  };
  const destination = String(props.modelValue.destination || "").trim();
  if (!destination) {
    nextErrors.destination = "请先填写目的地。";
  }
  if (!props.modelValue.start_date) {
    nextErrors.start_date = "请选择出发日期。";
  }
  if (!props.modelValue.end_date) {
    nextErrors.end_date = "请选择返程日期。";
  }
  if (
    props.modelValue.start_date &&
    props.modelValue.end_date &&
    !calculateTravelDays(props.modelValue.start_date, props.modelValue.end_date)
  ) {
    nextErrors.end_date = "返程日期不能早于出发日期。";
  }
  Object.assign(errors, nextErrors);
  return !Object.values(nextErrors).some(Boolean);
}

function handleSubmit() {
  if (!validateForm()) {
    return;
  }
  emit("submit");
}

function flashField(field) {
  flashedFields[field] = true;
  if (highlightTimerMap.has(field)) {
    clearTimeout(highlightTimerMap.get(field));
  }
  highlightTimerMap.set(
    field,
    setTimeout(() => {
      flashedFields[field] = false;
      highlightTimerMap.delete(field);
    }, 1200)
  );
}

function fieldState(field) {
  if (errors[field]) {
    return "error";
  }
  if (flashedFields[field]) {
    return "synced";
  }
  return "default";
}

watch(
  () => props.modelValue,
  (nextValue, previousValue) => {
    if (!previousValue) {
      localMutationFields = new Set();
      return;
    }
    const changedFields = Object.keys(nextValue || {}).filter((field) => nextValue[field] !== previousValue[field]);
    for (const field of changedFields) {
      if (!localMutationFields.has(field)) {
        flashField(field);
      }
    }
    localMutationFields = new Set();
  },
  { deep: true }
);
</script>

<template>
  <section class="panel form-panel planner-form-panel" :data-secondary="secondary">
    <div class="panel-header planner-form-header">
      <div>
        <p class="eyebrow">{{ secondary ? "表单补充" : "流程工作台" }}</p>
        <h2>{{ secondary ? "补齐本轮条件" : "填写这次旅行条件" }}</h2>
        <p class="planner-form-subtitle">
          先定日期、人数和目的地，再通过标签快速补齐偏好，系统会自动推导天数并生成路线。
        </p>
      </div>
      <button
        v-if="secondary"
        class="ghost-button compact planner-form-close"
        type="button"
        @click="$emit('close')"
      >
        关闭
      </button>
    </div>

    <div class="planner-form-layout">
      <section class="planner-section">
        <div class="planner-section-header">
          <h3>出行基础</h3>
          <p>先把必要条件定下来，下面的路线节奏和资源筛选都会跟着联动。</p>
        </div>

        <div class="field-grid planner-field-grid planner-field-grid-primary">
          <label class="field field-span-4" :data-state="fieldState('destination')">
            <span>目的地 <em>*</em></span>
            <input
              list="planner-city-options"
              :value="modelValue.destination"
              @input="updateField('destination', $event.target.value)"
              placeholder="例如：北京、上海、杭州"
            />
            <small v-if="errors.destination" class="field-error">{{ errors.destination }}</small>
          </label>

          <label class="field field-span-4" :data-state="fieldState('departure_city')">
            <span>出发城市</span>
            <input
              list="planner-city-options"
              :value="modelValue.departure_city"
              @input="updateField('departure_city', $event.target.value)"
              placeholder="例如：杭州、上海虹桥"
            />
          </label>

          <label class="field field-span-2">
            <span>人数</span>
            <div class="planner-stepper">
              <button type="button" class="stepper-button" :disabled="busy || Number(modelValue.travelers_count) <= 1" @click="setTravelersCount(Number(modelValue.travelers_count || 1) - 1)">
                -
              </button>
              <input
                type="number"
                min="1"
                max="20"
                :value="modelValue.travelers_count"
                @input="setTravelersCount($event.target.value)"
              />
              <button type="button" class="stepper-button" :disabled="busy || Number(modelValue.travelers_count) >= 20" @click="setTravelersCount(Number(modelValue.travelers_count || 1) + 1)">
                +
              </button>
            </div>
          </label>

          <label class="field field-span-2">
            <span>预算</span>
            <input
              type="number"
              min="0"
              :value="modelValue.budget"
              @input="updateField('budget', $event.target.value === '' ? '' : Number($event.target.value))"
              placeholder="总预算"
            />
          </label>

          <div class="field field-span-8" :data-state="errors.start_date || errors.end_date ? 'error' : 'default'">
            <span>出行日期 <em>*</em></span>
            <div class="planner-date-range">
              <div class="planner-date-range-slot">
                <label>出发</label>
                <input
                  type="date"
                  :value="modelValue.start_date"
                  @input="updateDateField('start_date', $event.target.value)"
                />
              </div>
              <span class="planner-date-range-separator">至</span>
              <div class="planner-date-range-slot">
                <label>返程</label>
                <input
                  type="date"
                  :min="modelValue.start_date || undefined"
                  :value="modelValue.end_date"
                  @input="updateDateField('end_date', $event.target.value)"
                />
              </div>
            </div>
            <small v-if="errors.start_date || errors.end_date" class="field-error">
              {{ errors.start_date || errors.end_date }}
            </small>
          </div>

          <div class="field field-span-4">
            <span>天数</span>
            <div class="planner-readonly-value">
              <strong>{{ inferredDays ? `${inferredDays} 天` : "待自动计算" }}</strong>
              <small>{{ inferredDays ? "已随日期同步" : "选择日期后自动生成" }}</small>
            </div>
          </div>
        </div>
      </section>

      <section class="planner-section">
        <div class="planner-section-header planner-section-header-inline">
          <div>
            <h3>偏好与限制</h3>
            <p>优先点选标签，输入框只留给你补充细节，不必每次都从头打字。</p>
          </div>
          <button class="ghost-button compact planner-surprise-button" type="button" @click="applySurprisePack">
            给我灵感
          </button>
        </div>

        <div class="field-grid planner-field-grid planner-field-grid-secondary">
          <label class="field field-span-6" :data-state="fieldState('interests')">
            <span>兴趣偏好</span>
            <div class="planner-tag-group">
              <button
                v-for="tag in TAG_GROUPS.interests"
                :key="tag"
                class="planner-tag"
                type="button"
                :data-active="hasTag('interests', tag)"
                @click="toggleTag('interests', tag)"
              >
                {{ tag }}
              </button>
            </div>
            <input
              :value="modelValue.interests"
              @input="updateField('interests', $event.target.value)"
              placeholder="支持补充自定义兴趣，多个偏好用逗号分隔"
            />
          </label>

          <label class="field field-span-6" :data-state="fieldState('transport_preferences')">
            <span>交通偏好</span>
            <div class="planner-tag-group">
              <button
                v-for="tag in TAG_GROUPS.transport_preferences"
                :key="tag"
                class="planner-tag"
                type="button"
                :data-active="hasTag('transport_preferences', tag)"
                @click="toggleTag('transport_preferences', tag)"
              >
                {{ tag }}
              </button>
            </div>
            <input
              :value="modelValue.transport_preferences"
              @input="updateField('transport_preferences', $event.target.value)"
              placeholder="例如：高铁去、返程打车、减少换乘"
            />
          </label>

          <label class="field field-span-4" :data-state="fieldState('food_preferences')">
            <span>美食偏好</span>
            <div class="planner-tag-group">
              <button
                v-for="tag in TAG_GROUPS.food_preferences"
                :key="tag"
                class="planner-tag"
                type="button"
                :data-active="hasTag('food_preferences', tag)"
                @click="toggleTag('food_preferences', tag)"
              >
                {{ tag }}
              </button>
            </div>
            <input
              :value="modelValue.food_preferences"
              @input="updateField('food_preferences', $event.target.value)"
              placeholder="例如：本帮菜、深夜食堂、无辣"
            />
          </label>

          <label class="field field-span-4" :data-state="fieldState('hotel_preferences')">
            <span>酒店偏好</span>
            <div class="planner-tag-group">
              <button
                v-for="tag in TAG_GROUPS.hotel_preferences"
                :key="tag"
                class="planner-tag"
                type="button"
                :data-active="hasTag('hotel_preferences', tag)"
                @click="toggleTag('hotel_preferences', tag)"
              >
                {{ tag }}
              </button>
            </div>
            <input
              :value="modelValue.hotel_preferences"
              @input="updateField('hotel_preferences', $event.target.value)"
              placeholder="例如：离景点近、适合家庭房"
            />
          </label>

          <label class="field field-span-4" :data-state="fieldState('constraints')">
            <span>约束条件</span>
            <div class="planner-tag-group">
              <button
                v-for="tag in TAG_GROUPS.constraints"
                :key="tag"
                class="planner-tag"
                type="button"
                :data-active="hasTag('constraints', tag)"
                @click="toggleTag('constraints', tag)"
              >
                {{ tag }}
              </button>
            </div>
            <input
              :value="modelValue.constraints"
              @input="updateField('constraints', $event.target.value)"
              placeholder="例如：每天晚上八点前回酒店"
            />
          </label>
        </div>
      </section>

      <section class="planner-section">
        <div class="planner-section-header">
          <h3>补充说明</h3>
          <p>把同行人特点、必须保留的安排，或不想踩雷的体验补在这里。</p>
        </div>

        <div class="field-grid planner-field-grid">
          <label class="field field-full" :data-state="fieldState('notes')">
            <span>补充说明</span>
            <textarea
              rows="5"
              :value="modelValue.notes"
              @input="updateField('notes', $event.target.value)"
              placeholder="例如：带父母同行，希望每天午后留休息时间；想保留一顿有特色的本地晚餐。"
            />
          </label>
        </div>
      </section>
    </div>

    <div class="form-actions planner-form-footer-sticky">
      <div class="planner-form-footer-note">
        <strong>先填必填项，AI 会自动推导天数并补全路线节奏。</strong>
      </div>
      <div class="planner-form-footer-buttons">
        <button class="secondary-button" :disabled="busy" type="button" @click="$emit('reset')">
          重置
        </button>
        <button class="primary-button planner-submit-button" :disabled="busy" type="button" @click="handleSubmit">
          <span class="planner-submit-icon" aria-hidden="true">
            <svg viewBox="0 0 20 20" fill="none">
              <path d="M10 1.5 11.8 6l4.7 1.7-4.7 1.7L10 14l-1.8-4.6L3.5 7.7 8.2 6 10 1.5Z" fill="currentColor" />
            </svg>
          </span>
          {{ busy ? "正在规划..." : secondary ? "提交到当前会话" : "生成旅行方案" }}
        </button>
      </div>
    </div>

    <datalist id="planner-city-options">
      <option v-for="item in CITY_SUGGESTIONS" :key="item" :value="item" />
    </datalist>
  </section>
</template>
