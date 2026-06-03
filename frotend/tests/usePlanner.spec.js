import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/lib/api", () => ({
  clearAuthTokens: vi.fn(),
  clearGuestToken: vi.fn(),
  fetchCurrentUser: vi.fn(),
  getAccessToken: vi.fn(() => ""),
  createChatSession: vi.fn(),
  getRecentChatSession: vi.fn(),
  getChatSession: vi.fn(),
  createChatTurn: vi.fn(),
  streamChatTurn: vi.fn(),
  getChatTurn: vi.fn(),
  logout: vi.fn(),
  requestAuthCode: vi.fn(),
  verifyAuthCode: vi.fn()
}));

import { resetAuthStateForTests } from "../src/composables/useAuth";
import { resetPlannerStateForTests, usePlanner } from "../src/composables/usePlanner";
import {
  createChatSession,
  createChatTurn,
  getChatSession,
  getChatTurn,
  getRecentChatSession,
  streamChatTurn
} from "../src/lib/api";

describe("usePlanner", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.localStorage.clear();
    resetAuthStateForTests();
    resetPlannerStateForTests();
    getRecentChatSession.mockRejectedValue(new Error("missing"));
    createChatSession.mockResolvedValue({
      session_id: "session-1",
      status: "idle",
      title: "默认会话"
    });
    getChatSession.mockResolvedValue({
      session_id: "session-1",
      title: "默认会话",
      status: "idle",
      messages: [],
      turns: [],
      confirmed_constraints: {},
      latest_result: null
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("restores the most recent session before creating a new one", async () => {
    getRecentChatSession.mockResolvedValue({
      session_id: "session-recent",
      title: "最近会话",
      status: "ready",
      messages: [{ message_id: "m1", role: "assistant", content: "最近草案" }],
      turns: [],
      confirmed_constraints: { destination: "上海", days: 2 },
      latest_result: { trip_summary: "最近草案", clarification_questions: [] }
    });

    const planner = usePlanner();
    await planner.initialize();

    expect(createChatSession).not.toHaveBeenCalled();
    expect(planner.state.sessionId).toBe("session-recent");
    expect(planner.state.sessionTitle).toBe("最近会话");
  });

  it("initializes a chat session with an empty workbench form", async () => {
    const planner = usePlanner();

    await planner.initialize();

    expect(planner.state.sessionId).toBe("session-1");
    expect(planner.state.form.destination).toBe("");
    expect(planner.state.form.days).toBe("");
    expect(planner.isRunning.value).toBe(false);
    expect(planner.hasResult.value).toBe(false);
  });

  it("submits a message and hydrates the result after polling", async () => {
    const planner = usePlanner();
    streamChatTurn.mockImplementation(async (_sessionId, _payload, { onEvent }) => {
      await onEvent({
        event: "turn.created",
        data: { turn_id: "turn-1", status: "queued", phase: "queued", session_status: "running" }
      });
      await onEvent({
        event: "turn.step",
        data: { step: { key: "plan_trip", title: "生成模型回复", status: "running", detail: "正在生成" } }
      });
      await onEvent({
        event: "turn.result",
        data: {
          phase: "completed",
          result: {
            status: "success",
            plan_state: "draft",
            trip_summary: "Shanghai 2-day route",
            clarification_questions: [],
            confirmed_constraints: { destination: "上海", days: 2 }
          }
        }
      });
      await onEvent({
        event: "message.delta",
        data: { turn_id: "turn-1", delta: "Shanghai 2-day route", content: "Shanghai 2-day route", message_type: "result" }
      });
      await onEvent({
        event: "turn.complete",
        data: {
          turn_id: "turn-1",
          status: "completed",
          phase: "completed",
          result: {
            status: "success",
            plan_state: "draft",
            trip_summary: "Shanghai 2-day route",
            clarification_questions: [],
            confirmed_constraints: { destination: "上海", days: 2 }
          }
        }
      });
    });
    getChatSession
      .mockResolvedValueOnce({
        session_id: "session-1",
        title: "默认会话",
        status: "idle",
        messages: [],
        turns: [],
        confirmed_constraints: {},
        latest_result: null
      })
      .mockResolvedValueOnce({
        session_id: "session-1",
        title: "默认会话",
        status: "ready",
        messages: [
          { message_id: "m1", role: "user", content: "规划上海两日游" },
          { message_id: "m2", role: "assistant", content: "Shanghai 2-day route" }
        ],
        turns: [
          {
            turn_id: "turn-1",
            status: "completed",
            steps: [{ key: "plan_trip", title: "生成模型回复", status: "completed" }],
            result: {
              status: "success",
              plan_state: "draft",
              trip_summary: "Shanghai 2-day route",
              clarification_questions: []
            }
          }
        ],
        confirmed_constraints: { destination: "上海", days: 2 },
        latest_result: {
          status: "success",
          plan_state: "draft",
          trip_summary: "Shanghai 2-day route",
          clarification_questions: []
        }
      });

    await planner.initialize();
    planner.state.composer = "规划上海两日游";
    await planner.sendMessage();

    expect(streamChatTurn).toHaveBeenCalledWith("session-1", {
      message: "规划上海两日游"
    }, expect.any(Object));
    expect(planner.state.result.trip_summary).toBe("Shanghai 2-day route");
    expect(planner.state.messages).toHaveLength(2);
  });

  it("submits the secondary form into the same session", async () => {
    const planner = usePlanner();
    streamChatTurn.mockImplementation(async (_sessionId, payload, { onEvent }) => {
      expect(payload).toEqual(
        expect.objectContaining({
          request: expect.objectContaining({ destination: "上海", days: 3 })
        })
      );
      await onEvent({
        event: "turn.created",
        data: { turn_id: "turn-2", status: "queued", phase: "queued", session_status: "running" }
      });
    });
    getChatSession.mockResolvedValue({
      session_id: "session-1",
      title: "默认会话",
      status: "running",
      messages: [],
      turns: [{ turn_id: "turn-2", status: "queued", steps: [] }],
      confirmed_constraints: { destination: "上海", days: 3 },
      latest_result: null,
      active_turn_id: "turn-2"
    });

    await planner.initialize();
    planner.toggleForm(true);
    planner.state.form = {
      ...planner.state.form,
      destination: "上海",
      departure_city: "杭州",
      start_date: "2026-04-10",
      end_date: "2026-04-12",
      days: 3,
      travelers_count: 2
    };
    await planner.submitForm();

    expect(streamChatTurn).toHaveBeenCalledTimes(1);
    expect(planner.state.formOpen).toBe(false);
  });
});
