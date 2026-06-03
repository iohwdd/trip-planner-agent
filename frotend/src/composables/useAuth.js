import { computed, reactive } from "vue";
import {
  clearAuthTokens,
  clearGuestToken,
  fetchCurrentUser,
  getAccessToken,
  getGuestToken,
  loginWithPassword,
  logout as logoutRequest,
  requestAuthCode,
  updatePassword,
  verifyAuthCode
} from "../lib/api";

const defaultGuestState = () => ({
  active: false,
  token_present: false
});

const defaultAssetSummary = () => ({
  session_count: 0,
  session_status_counts: {},
  recent_session_id: null,
  plan_count: 0,
  plan_status_counts: {}
});

const defaultCapabilities = () => ({
  can_manage_sessions: true,
  can_save_plan: false,
  can_manage_plans: false,
  can_set_password: false,
  can_manage_knowledge_base: false
});

const defaultState = () => ({
  initialized: false,
  loading: false,
  authenticated: false,
  user: null,
  guest: defaultGuestState(),
  assetSummary: defaultAssetSummary(),
  capabilities: defaultCapabilities(),
  dialogOpen: false,
  reason: "",
  loginMode: "code",
  email: "",
  code: "",
  password: "",
  step: "email",
  info: "",
  error: "",
  passwordForm: {
    currentPassword: "",
    newPassword: "",
    info: "",
    error: "",
    saving: false
  }
});

const state = reactive(defaultState());

function applyIdentityPayload(payload = {}) {
  state.authenticated = Boolean(payload.authenticated);
  state.user = payload.user || null;
  state.guest = {
    ...defaultGuestState(),
    ...(payload.guest || {})
  };
  state.assetSummary = {
    ...defaultAssetSummary(),
    ...(payload.asset_summary || {})
  };
  state.capabilities = {
    ...defaultCapabilities(),
    ...(payload.capabilities || {})
  };
  if (!payload.capabilities && payload.user?.is_staff) {
    state.capabilities.can_manage_knowledge_base = true;
  }
  state.initialized = true;
}

function resetDialog(reason = "") {
  state.dialogOpen = false;
  state.reason = reason;
  state.email = "";
  state.code = "";
  state.password = "";
  state.step = "email";
  state.loginMode = "code";
  state.info = "";
  state.error = "";
}

export function useAuth() {
  const isAuthenticated = computed(() => state.authenticated);
  const userLabel = computed(() => state.user?.display_name || state.user?.email || "登录用户");

  async function restore() {
    state.loading = true;
    state.error = "";
    try {
      if (!getAccessToken() && !getGuestToken()) {
        applyIdentityPayload({ authenticated: false });
        return false;
      }
      const payload = await fetchCurrentUser();
      applyIdentityPayload(payload);
      if (!payload.authenticated) {
        clearAuthTokens();
      }
      return state.authenticated;
    } catch (error) {
      clearAuthTokens();
      applyIdentityPayload({ authenticated: false });
      state.error = error.message || "登录状态恢复失败";
      return false;
    } finally {
      state.loading = false;
    }
  }

  function openDialog(reason = "登录后可保存并管理你的旅行资产。") {
    state.dialogOpen = true;
    state.reason = reason;
    state.error = "";
    state.info = "";
    if (state.loginMode === "code" && !state.step) {
      state.step = "email";
    }
  }

  function closeDialog() {
    resetDialog();
  }

  function switchLoginMode(mode) {
    state.loginMode = mode;
    state.error = "";
    state.info = "";
    state.code = "";
    state.password = "";
    state.step = mode === "code" ? "email" : "password";
  }

  async function sendCode() {
    state.loading = true;
    state.error = "";
    try {
      const payload = await requestAuthCode(state.email.trim());
      state.info = payload.message || "验证码已发送。";
      if (payload.debug_code) {
        state.info = `${state.info} 调试验证码：${payload.debug_code}`;
      }
      state.step = "code";
      return payload;
    } catch (error) {
      state.error = error.message || "验证码发送失败";
      throw error;
    } finally {
      state.loading = false;
    }
  }

  async function submitCode() {
    state.loading = true;
    state.error = "";
    try {
      const payload = await verifyAuthCode(state.email.trim(), state.code.trim());
      applyIdentityPayload({
        ...payload,
        authenticated: true
      });
      closeDialog();
      return payload;
    } catch (error) {
      state.error = error.message || "登录失败";
      throw error;
    } finally {
      state.loading = false;
    }
  }

  async function submitPassword() {
    state.loading = true;
    state.error = "";
    try {
      const payload = await loginWithPassword(
        state.email.trim(),
        state.password
      );
      applyIdentityPayload({
        ...payload,
        authenticated: true
      });
      closeDialog();
      return payload;
    } catch (error) {
      state.error = error.message || "密码登录失败";
      throw error;
    } finally {
      state.loading = false;
    }
  }

  async function savePassword() {
    state.passwordForm.saving = true;
    state.passwordForm.error = "";
    state.passwordForm.info = "";
    try {
      const payload = await updatePassword({
        currentPassword: state.passwordForm.currentPassword,
        newPassword: state.passwordForm.newPassword
      });
      state.passwordForm.info = payload.message || "密码已设置。";
      state.passwordForm.currentPassword = "";
      state.passwordForm.newPassword = "";
      if (state.user) {
        state.user = {
          ...state.user,
          has_password: true
        };
      }
      return payload;
    } catch (error) {
      state.passwordForm.error = error.message || "密码设置失败";
      throw error;
    } finally {
      state.passwordForm.saving = false;
    }
  }

  async function logout() {
    state.loading = true;
    try {
      await logoutRequest();
    } finally {
      state.loading = false;
      clearGuestToken();
      applyIdentityPayload({ authenticated: false });
      resetDialog();
    }
  }

  function requireLogin(reason) {
    if (state.authenticated) {
      return true;
    }
    openDialog(reason);
    return false;
  }

  return {
    state,
    isAuthenticated,
    userLabel,
    restore,
    openDialog,
    closeDialog,
    switchLoginMode,
    sendCode,
    submitCode,
    submitPassword,
    savePassword,
    logout,
    requireLogin
  };
}

export function resetAuthStateForTests() {
  Object.assign(state, defaultState());
}
