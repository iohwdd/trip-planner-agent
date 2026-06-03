import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/lib/api", () => ({
  deleteChatSession: vi.fn(),
  listChatSessions: vi.fn(),
  renameChatSession: vi.fn()
}));

import {
  resetSessionLibraryForTests,
  useSessionLibrary
} from "../src/composables/useSessionLibrary";
import {
  deleteChatSession,
  listChatSessions,
  renameChatSession
} from "../src/lib/api";

describe("useSessionLibrary", () => {
  beforeEach(() => {
    resetSessionLibraryForTests();
    listChatSessions.mockReset();
    renameChatSession.mockReset();
    deleteChatSession.mockReset();
  });

  it("loads the session list for the workspace", async () => {
    listChatSessions.mockResolvedValue({
      items: [
        { session_id: "s1", title: "上海会话", status: "ready" },
        { session_id: "s2", title: "杭州会话", status: "running" }
      ],
      count: 2,
      status_counts: {
        ready: 1,
        running: 1
      },
      recent_session_id: "s2"
    });

    const library = useSessionLibrary();
    const items = await library.refreshSessions();

    expect(items).toHaveLength(2);
    expect(library.state.items[0].title).toBe("上海会话");
    expect(library.state.count).toBe(2);
    expect(library.state.statusCounts.running).toBe(1);
    expect(library.state.recentSessionId).toBe("s2");
  });

  it("renames and deletes sessions through the api layer", async () => {
    listChatSessions.mockResolvedValue({ items: [] });

    const library = useSessionLibrary();
    await library.renameSession("s1", "新的标题");
    await library.removeSession("s1");

    expect(renameChatSession).toHaveBeenCalledWith("s1", "新的标题");
    expect(deleteChatSession).toHaveBeenCalledWith("s1");
  });
});
