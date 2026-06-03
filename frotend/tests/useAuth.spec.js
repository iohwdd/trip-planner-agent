import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockedApi = vi.hoisted(() => ({
  token: "",
  guestToken: "",
  fetchCurrentUser: vi.fn(),
  requestAuthCode: vi.fn(),
  verifyAuthCode: vi.fn(),
  loginWithPassword: vi.fn(),
  updatePassword: vi.fn(),
  logout: vi.fn()
}));

vi.mock("../src/lib/api", () => ({
  clearAuthTokens: vi.fn(),
  clearGuestToken: vi.fn(),
  getAccessToken: () => mockedApi.token,
  getGuestToken: () => mockedApi.guestToken,
  fetchCurrentUser: mockedApi.fetchCurrentUser,
  loginWithPassword: mockedApi.loginWithPassword,
  requestAuthCode: mockedApi.requestAuthCode,
  updatePassword: mockedApi.updatePassword,
  verifyAuthCode: mockedApi.verifyAuthCode,
  logout: mockedApi.logout
}));

import { resetAuthStateForTests, useAuth } from "../src/composables/useAuth";

describe("useAuth", () => {
  beforeEach(() => {
    mockedApi.token = "";
    mockedApi.guestToken = "";
    mockedApi.fetchCurrentUser.mockReset();
    mockedApi.requestAuthCode.mockReset();
    mockedApi.verifyAuthCode.mockReset();
    mockedApi.loginWithPassword.mockReset();
    mockedApi.updatePassword.mockReset();
    mockedApi.logout.mockReset();
    resetAuthStateForTests();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("restores authenticated state from the current token", async () => {
    mockedApi.token = "access-token";
    mockedApi.fetchCurrentUser.mockResolvedValue({
      authenticated: true,
      user: {
        id: "u1",
        email: "traveler@example.com",
        display_name: "traveler"
      },
      asset_summary: {
        session_count: 3,
        plan_count: 1,
        recent_session_id: "session-9"
      },
      capabilities: {
        can_save_plan: true,
        can_manage_plans: true
      }
    });

    const auth = useAuth();
    const restored = await auth.restore();

    expect(restored).toBe(true);
    expect(auth.state.authenticated).toBe(true);
    expect(auth.state.user.email).toBe("traveler@example.com");
    expect(auth.state.assetSummary.session_count).toBe(3);
    expect(auth.state.capabilities.can_save_plan).toBe(true);
  });

  it("opens the dialog and verifies the code", async () => {
    mockedApi.requestAuthCode.mockResolvedValue({ message: "验证码已发送。" });
    mockedApi.verifyAuthCode.mockResolvedValue({
      user: {
        id: "u1",
        email: "traveler@example.com",
        display_name: "traveler"
      },
      asset_summary: {
        session_count: 1,
        plan_count: 1
      }
    });

    const auth = useAuth();
    auth.openDialog("登录后可保存方案。");
    auth.state.email = "traveler@example.com";
    await auth.sendCode();
    auth.state.code = "123456";
    await auth.submitCode();

    expect(auth.state.authenticated).toBe(true);
    expect(auth.state.dialogOpen).toBe(false);
    expect(auth.state.assetSummary.plan_count).toBe(1);
  });

  it("allows first-time password setup without current password", async () => {
    mockedApi.updatePassword.mockResolvedValue({ message: "密码已设置。" });

    const auth = useAuth();
    auth.state.authenticated = true;
    auth.state.user = {
      id: "u1",
      email: "traveler@example.com",
      display_name: "traveler",
      has_password: false
    };
    auth.state.passwordForm.newPassword = "secret123";

    await auth.savePassword();

    expect(mockedApi.updatePassword).toHaveBeenCalledWith({
      currentPassword: "",
      newPassword: "secret123"
    });
    expect(auth.state.user.has_password).toBe(true);
    expect(auth.state.passwordForm.info).toBe("密码已设置。");
  });
});
