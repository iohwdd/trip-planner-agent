import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/lib/api", () => ({
  clearAuthTokens: vi.fn(),
  clearGuestToken: vi.fn(),
  fetchCurrentUser: vi.fn(),
  getAccessToken: vi.fn(() => ""),
  getGuestToken: vi.fn(() => ""),
  deleteTripPlan: vi.fn(),
  getTripPlan: vi.fn(),
  listTripPlans: vi.fn(),
  loginWithPassword: vi.fn(),
  logout: vi.fn(),
  requestAuthCode: vi.fn(),
  resumeTripPlan: vi.fn(),
  saveRunTripPlan: vi.fn(),
  saveTripPlan: vi.fn(),
  updatePassword: vi.fn(),
  verifyAuthCode: vi.fn()
}));

import { resetAuthStateForTests, useAuth } from "../src/composables/useAuth";
import { resetPlanLibraryForTests, usePlanLibrary } from "../src/composables/usePlanLibrary";
import {
  deleteTripPlan,
  getTripPlan,
  listTripPlans,
  resumeTripPlan,
  saveRunTripPlan,
  saveTripPlan
} from "../src/lib/api";

describe("usePlanLibrary", () => {
  beforeEach(() => {
    resetAuthStateForTests();
    resetPlanLibraryForTests();
    saveTripPlan.mockReset();
    saveRunTripPlan.mockReset();
    listTripPlans.mockReset();
    getTripPlan.mockReset();
    deleteTripPlan.mockReset();
    resumeTripPlan.mockReset();
  });

  it("prompts for login when saving a plan while unauthenticated", async () => {
    const auth = useAuth();
    const library = usePlanLibrary();
    const result = await library.saveCurrentPlan("session-1", "draft");

    expect(result).toBeNull();
    expect(auth.state.dialogOpen).toBe(true);
    expect(library.state.error).toContain("请先登录");
  });

  it("saves, loads, and resumes plans when authenticated", async () => {
    const auth = useAuth();
    auth.state.authenticated = true;
    auth.state.user = { id: "u1", email: "traveler@example.com", display_name: "traveler" };

    saveTripPlan.mockResolvedValue({ plan_id: "p1", version: 1, status: "draft" });
    listTripPlans.mockResolvedValue({
      items: [{ plan_id: "p1", title: "上海草案", version: 1, status: "draft" }],
      count: 1,
      status_counts: {
        draft: 1
      }
    });
    getTripPlan.mockResolvedValue({
      plan_id: "p1",
      title: "上海草案",
      result_snapshot: { trip_summary: "上海路线" }
    });
    resumeTripPlan.mockResolvedValue({ session_id: "session-resume" });

    const library = usePlanLibrary();
    const saved = await library.saveCurrentPlan("session-1", "draft", "上海草案");
    const detail = await library.loadPlan("p1");
    const resumed = await library.continueEditing("p1");

    expect(saved.plan_id).toBe("p1");
    expect(library.state.items).toHaveLength(1);
    expect(library.state.count).toBe(1);
    expect(library.state.statusCounts.draft).toBe(1);
    expect(detail.plan_id).toBe("p1");
    expect(resumed.session_id).toBe("session-resume");
  });

  it("saves plans from a workbench run when authenticated", async () => {
    const auth = useAuth();
    auth.state.authenticated = true;
    auth.state.user = { id: "u1", email: "traveler@example.com", display_name: "traveler" };

    saveRunTripPlan.mockResolvedValue({ plan_id: "p2", version: 1, status: "final" });
    listTripPlans.mockResolvedValue({
      items: [{ plan_id: "p2", title: "杭州终版", version: 1, status: "final" }],
      count: 1,
      status_counts: {
        final: 1
      }
    });

    const library = usePlanLibrary();
    const saved = await library.saveRunPlan("run-1", "final", "杭州终版");

    expect(saveRunTripPlan).toHaveBeenCalledWith("run-1", {
      status: "final",
      title: "杭州终版"
    });
    expect(saved.plan_id).toBe("p2");
    expect(library.state.statusCounts.final).toBe(1);
  });
});
