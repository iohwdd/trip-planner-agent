import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/lib/api", () => ({
  createAssistantConversation: vi.fn(),
  getAssistantConversation: vi.fn(),
  getRecentAssistantConversation: vi.fn(),
  sendAssistantMessage: vi.fn(),
  streamAssistantMessage: vi.fn()
}));

import { resetAuthStateForTests } from "../src/composables/useAuth";
import {
  resetAssistantStateForTests,
  useAssistant
} from "../src/composables/useAssistant";
import {
  createAssistantConversation,
  getAssistantConversation,
  getRecentAssistantConversation,
  streamAssistantMessage
} from "../src/lib/api";

describe("useAssistant", () => {
  beforeEach(() => {
    window.localStorage.clear();
    resetAuthStateForTests();
    resetAssistantStateForTests();
    getRecentAssistantConversation.mockReset().mockRejectedValue(new Error("missing"));
    createAssistantConversation.mockReset().mockResolvedValue({
      conversation_id: "conversation-1",
      title: "默认助手会话"
    });
    getAssistantConversation.mockReset().mockResolvedValue({
      conversation_id: "conversation-1",
      title: "默认助手会话",
      messages: []
    });
    streamAssistantMessage.mockReset();
  });

  it("updates assistant content progressively from SSE deltas", async () => {
    const assistant = useAssistant();
    await assistant.initialize();

    streamAssistantMessage.mockImplementation(async (_conversationId, _message, { onEvent }) => {
      await onEvent({
        event: "message.delta",
        data: {
          content: "第一段",
          delta: "第一段",
          message_type: "text"
        }
      });
      expect(assistant.state.messages.at(-1)?.content).toBe("第一段");

      await onEvent({
        event: "message.delta",
        data: {
          content: "第一段第二段",
          delta: "第二段",
          message_type: "text"
        }
      });
      expect(assistant.state.messages.at(-1)?.content).toBe("第一段第二段");

      await onEvent({
        event: "message.complete",
        data: {
          conversation: {
            conversation_id: "conversation-1",
            title: "默认助手会话",
            messages: [
              {
                message_id: "u1",
                role: "user",
                content: "你好",
                message_type: "text"
              },
              {
                message_id: "a1",
                role: "assistant",
                content: "第一段第二段",
                message_type: "text"
              }
            ]
          }
        }
      });
    });

    assistant.state.composer = "你好";
    await assistant.sendMessage();

    expect(streamAssistantMessage).toHaveBeenCalledTimes(1);
    expect(assistant.state.messages.at(-1)?.content).toBe("第一段第二段");
    expect(assistant.busy.value).toBe(false);
  });
});
