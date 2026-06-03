<script setup>
import { computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAssistantLibrary } from "../composables/useAssistantLibrary";
import { useAuth } from "../composables/useAuth";
import { usePlanLibrary } from "../composables/usePlanLibrary";

const router = useRouter();
const auth = useAuth();
const plans = usePlanLibrary();
const assistants = useAssistantLibrary();

const assetSummary = computed(() => auth.state.assetSummary || {});
const sessionCount = computed(() => assetSummary.value.assistant_conversation_count || assistants.state.count || assistants.state.items.length);
const planCount = computed(() => assetSummary.value.plan_count || plans.state.count || plans.state.items.length);

onMounted(async () => {
  await assistants.refreshConversations();
  if (auth.state.authenticated) {
    await plans.refreshPlans();
  }
});
</script>

<template>
  <section class="page-shell profile-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">个人中心</p>
        <h1>{{ auth.state.authenticated ? "身份与旅行资产概览" : "游客模式与资产连续性说明" }}</h1>
      </div>
      <p class="page-copy">
        这里的重点不是账户管理本身，而是帮助你理解当前身份下可以怎样继续推进旅行决策、保存结果并回到过去的上下文。
      </p>
    </header>

    <div class="collection-grid profile-grid">
      <article class="collection-card">
        <p class="eyebrow">登录状态</p>
        <h2>{{ auth.state.authenticated ? auth.userLabel : "未登录 / 游客" }}</h2>
        <p class="collection-copy">
          {{
            auth.state.authenticated
              ? "你当前已进入资产连续性模式：可以继续修订会话、保存方案版本，并从历史路线重新开始。"
              : "你可以先以游客身份体验主工作台；登录后，当前浏览器里的临时会话会迁移到账号下并长期保留。"
          }}
        </p>
        <button
          v-if="!auth.state.authenticated"
          class="primary-button"
          type="button"
          @click="auth.openDialog('登录后可以把当前会话和草案沉淀到账号下。')"
        >
          登录 / 注册
        </button>
      </article>

      <article class="collection-card">
        <p class="eyebrow">资产概览</p>
        <h2>{{ auth.state.authenticated ? "当前账号的旅行资产状态" : "游客模式下的连续性边界" }}</h2>
        <p class="collection-copy">
          {{
            auth.state.authenticated
              ? "这些不是后台统计，而是你接下来最值得继续的旅行上下文。"
              : "游客模式下也会保留当前浏览器里的临时会话，但方案不会长期沉淀。"
          }}
        </p>
        <div class="summary-pills">
          <span class="constraint-pill">助手会话数 · {{ sessionCount }}</span>
          <span class="constraint-pill">方案数 · {{ auth.state.authenticated ? planCount : "登录后可见" }}</span>
          <span class="constraint-pill" v-if="assetSummary.recent_session_id">最近会话可恢复</span>
        </div>
        <div class="card-actions">
          <button class="primary-button" type="button" @click="router.push('/')">回到工作台</button>
          <button class="ghost-button" type="button" @click="router.push('/sessions')">查看会话</button>
          <button v-if="auth.state.authenticated" class="ghost-button" type="button" @click="router.push('/plans')">查看方案</button>
        </div>
      </article>

      <article v-if="auth.state.authenticated" class="collection-card">
        <p class="eyebrow">账户设置</p>
        <h2>{{ auth.state.user?.has_password ? "更新登录密码" : "为当前账号设置密码" }}</h2>
        <p class="collection-copy">
          {{ auth.state.user?.has_password ? "密码设置是支撑能力，目的是帮助你更稳定地回到自己的旅行资产。" : "当前账号还没有密码，设置后可直接使用密码登录并继续管理你的旅行资产。" }}
        </p>
        <label class="field">
          <span>{{ auth.state.user?.has_password ? "当前密码" : "当前密码（首次设置可留空）" }}</span>
          <input
            v-model="auth.state.passwordForm.currentPassword"
            type="password"
            autocomplete="current-password"
            :placeholder="auth.state.user?.has_password ? '请输入当前密码' : '首次设置密码时可留空'"
          />
        </label>
        <label class="field">
          <span>新密码</span>
          <input
            v-model="auth.state.passwordForm.newPassword"
            type="password"
            autocomplete="new-password"
            placeholder="至少 8 位"
          />
        </label>
        <p v-if="auth.state.passwordForm.info" class="info-message">{{ auth.state.passwordForm.info }}</p>
        <p v-if="auth.state.passwordForm.error" class="error-message">{{ auth.state.passwordForm.error }}</p>
        <button
          class="primary-button"
          type="button"
          :disabled="auth.state.passwordForm.saving || !auth.state.passwordForm.newPassword"
          @click="auth.savePassword()"
        >
          {{ auth.state.passwordForm.saving ? "保存中..." : auth.state.user?.has_password ? "更新密码" : "设置密码" }}
        </button>
      </article>
    </div>
  </section>
</template>
