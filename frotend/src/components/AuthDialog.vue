<script setup>
import { useAuth } from "../composables/useAuth";

const auth = useAuth();
</script>

<template>
  <transition name="fade-dialog">
    <div v-if="auth.state.dialogOpen" class="dialog-backdrop" @click.self="auth.closeDialog()">
      <section class="dialog-card modern-auth-dialog">
        <!-- Travel themed side cover -->
        <div class="auth-cover">
          <div class="auth-cover-content">
            <h3>探索世界，由此开始</h3>
            <p>登录后即可解锁智能旅游规划，保存您的私人行程库与旅行灵感。</p>
          </div>
        </div>

        <div class="auth-form-container">
          <div class="dialog-header">
            <div>
              <p class="eyebrow">账号登录</p>
              <h2>欢迎回来</h2>
            </div>
            <button class="ghost-button compact-button" type="button" @click="auth.closeDialog()">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
          </div>

          <p class="dialog-copy">
            {{ auth.state.reason || "登录后可以保存草案、管理历史会话，并把当前游客会话迁移到你的账号下。" }}
          </p>

          <div class="auth-tabs">
            <button
              class="auth-tab"
              type="button"
              :class="{ 'is-active': auth.state.loginMode === 'code' }"
              @click="auth.switchLoginMode('code')"
            >
              验证码登录
            </button>
            <button
              class="auth-tab"
              type="button"
              :class="{ 'is-active': auth.state.loginMode === 'password' }"
              @click="auth.switchLoginMode('password')"
            >
              密码登录
            </button>
          </div>

          <label class="field auth-field">
            <span>邮箱地址</span>
            <div class="input-wrapper">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="input-icon"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>
              <input
                v-model="auth.state.email"
                type="email"
                autocomplete="email"
                placeholder="you@example.com"
              />
            </div>
          </label>

          <label class="field auth-field" v-if="auth.state.loginMode === 'code'">
            <span>验证码</span>
            <div class="input-with-button">
              <div class="input-wrapper">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="input-icon"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
                <input
                  v-model="auth.state.code"
                  type="text"
                  inputmode="numeric"
                  maxlength="6"
                  placeholder="请输入 6 位验证码"
                  v-if="auth.state.step === 'code' || auth.state.step === 'email'"
                />
              </div>
              <button
                class="secondary-button send-code-btn"
                type="button"
                :disabled="auth.state.loading"
                @click="auth.sendCode()"
              >
                {{ auth.state.loading && auth.state.step === "email" ? "发送中..." : "获取验证码" }}
              </button>
            </div>
          </label>

          <label class="field auth-field" v-if="auth.state.loginMode === 'password'">
            <span>密码</span>
            <div class="input-wrapper">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="input-icon"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
              <input
                v-model="auth.state.password"
                type="password"
                autocomplete="current-password"
                placeholder="请输入密码"
              />
            </div>
          </label>

          <transition name="fade">
            <p v-if="auth.state.info" class="info-message auth-message">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
              {{ auth.state.info }}
            </p>
          </transition>
          <transition name="fade">
            <p v-if="auth.state.error" class="error-message auth-message">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>
              {{ auth.state.error }}
            </p>
          </transition>

          <div class="dialog-actions auth-actions">
            <button
              class="primary-button auth-submit-btn"
              type="button"
              :disabled="
                auth.state.loading
                  || (auth.state.loginMode === 'code' && auth.state.step !== 'code')
                  || (auth.state.loginMode === 'password' && !auth.state.password)
              "
              @click="auth.state.loginMode === 'code' ? auth.submitCode() : auth.submitPassword()"
            >
              {{
                auth.state.loading
                  ? "登录中..."
                  : auth.state.loginMode === "code"
                    ? "验证并登录"
                    : "密码登录"
              }}
            </button>
          </div>
        </div>
      </section>
    </div>
  </transition>
</template>

<style scoped>
.modern-auth-dialog {
  display: flex;
  padding: 0;
  overflow: hidden;
  max-width: 800px;
  width: 90vw;
  border-radius: 16px;
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.12), 0 8px 16px rgba(0, 0, 0, 0.08);
}

.auth-cover {
  flex: 0 0 40%;
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.9), rgba(124, 58, 237, 0.8)), url('https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80') center/cover;
  position: relative;
  display: none;
  color: white;
  padding: 2.5rem;
}

@media (min-width: 768px) {
  .auth-cover {
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
  }
}

.auth-cover-content h3 {
  font-size: 1.75rem;
  margin-bottom: 1rem;
  font-weight: 700;
  line-height: 1.2;
}

.auth-cover-content p {
  font-size: 1rem;
  line-height: 1.5;
  opacity: 0.9;
}

.auth-form-container {
  flex: 1;
  padding: 2.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  background: var(--surface);
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 0.5rem;
}

.dialog-header h2 {
  font-size: 1.5rem;
  font-weight: 600;
  margin-top: 0.25rem;
}

.dialog-copy {
  color: var(--text-muted);
  font-size: 0.9375rem;
  line-height: 1.5;
  margin-bottom: 1rem;
}

.auth-tabs {
  display: flex;
  background: var(--surface-hover);
  border-radius: 8px;
  padding: 0.25rem;
  margin-bottom: 1rem;
}

.auth-tab {
  flex: 1;
  padding: 0.625rem 1rem;
  border: none;
  background: transparent;
  border-radius: 6px;
  font-size: 0.9375rem;
  font-weight: 500;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s;
}

.auth-tab.is-active {
  background: var(--surface);
  color: var(--text);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.auth-field span {
  font-size: 0.875rem;
  font-weight: 500;
  margin-bottom: 0.5rem;
  color: var(--text);
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.input-icon {
  position: absolute;
  left: 0.875rem;
  color: var(--text-muted);
  opacity: 0.7;
}

.auth-field input {
  width: 100%;
  padding: 0.75rem 0.75rem 0.75rem 2.5rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 0.9375rem;
  transition: border-color 0.2s, box-shadow 0.2s;
  background-color: var(--surface);
}

.auth-field input:focus {
  border-color: var(--brand-primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
  outline: none;
}

.input-with-button {
  display: flex;
  gap: 0.75rem;
}

.input-with-button .input-wrapper {
  flex: 1;
}

.send-code-btn {
  white-space: nowrap;
  padding: 0 1rem;
  border-radius: 8px;
}

.auth-actions {
  margin-top: 1rem;
}

.auth-submit-btn {
  width: 100%;
  padding: 0.875rem;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 600;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 0.5rem;
}

.auth-message {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  border-radius: 8px;
  font-size: 0.875rem;
  margin-top: -0.5rem;
}

.info-message {
  background: rgba(37, 99, 235, 0.1);
  color: var(--brand-primary);
}

.error-message {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
