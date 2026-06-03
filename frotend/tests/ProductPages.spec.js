import { mount, flushPromises } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  auth: {
    state: {
      authenticated: false,
      assetSummary: {
        assistant_conversation_count: 0,
        plan_count: 0
      },
      capabilities: {
        can_manage_knowledge_base: false
      }
    },
    userLabel: "traveler",
    openDialog: vi.fn()
  },
  assistant: {
    state: {
      conversationId: "conversation-1",
      messages: [],
      composer: "",
      flash: "",
      error: ""
    },
    busy: false,
    initialize: vi.fn(),
    reconnectForIdentity: vi.fn(),
    createConversation: vi.fn(),
    sendMessage: vi.fn(),
    resetConversation: vi.fn(),
    openConversation: vi.fn()
  },
  assistantLibrary: {
    state: {
      loading: false,
      error: "",
      items: [],
      recentConversationId: null
    },
    refreshConversations: vi.fn(),
    renameConversation: vi.fn(),
    removeConversation: vi.fn()
  },
  workbench: {
    state: {
      form: {},
      view: "run",
      runId: "run-1",
      runStatus: "completed",
      steps: [],
      result: {
        trip_summary: "上海两日游草案"
      },
      error: "",
      flash: ""
    },
    isRunning: { value: false },
    isRunView: { value: true },
    hasResult: { value: true },
    submitForm: vi.fn(),
    resetForm: vi.fn(),
    returnToForm: vi.fn(),
    clearRun: vi.fn(),
    setFlash: vi.fn()
  },
  planner: {
    openSession: vi.fn()
  },
  sessions: {
    refreshSessions: vi.fn()
  },
  plans: {
    state: {
      loading: false,
      error: "",
      info: "",
      items: [],
      activePlan: null,
      count: 0,
      statusCounts: {}
    },
    refreshPlans: vi.fn(),
    saveRunPlan: vi.fn(),
    continueEditing: vi.fn(),
    removePlan: vi.fn(),
    loadPlan: vi.fn()
  },
  knowledge: {
    state: {
      loading: false,
      uploading: false,
      reindexing: false,
      error: "",
      info: "",
      knowledgeBase: {
        knowledge_base_id: "kb-1",
        name: "智能助手知识库"
      },
      documents: [],
      summary: {
        document_count: 0,
        ready_count: 0,
        processing_count: 0,
        failed_count: 0
      }
    },
    clearFeedback: vi.fn(),
    dispose: vi.fn(),
    refresh: vi.fn(),
    upload: vi.fn(),
    retry: vi.fn(),
    remove: vi.fn(),
    reindex: vi.fn()
  }
}));

vi.mock("vue-router", () => ({
  useRouter: () => ({
    push: mocks.push
  })
}));

vi.mock("../src/composables/useAuth", () => ({
  useAuth: () => mocks.auth
}));

vi.mock("../src/composables/useAssistant", () => ({
  useAssistant: () => mocks.assistant
}));

vi.mock("../src/composables/useAssistantLibrary", () => ({
  useAssistantLibrary: () => mocks.assistantLibrary
}));

vi.mock("../src/composables/useWorkbench", () => ({
  useWorkbench: () => mocks.workbench
}));

vi.mock("../src/composables/usePlanner", () => ({
  usePlanner: () => mocks.planner
}));

vi.mock("../src/composables/useSessionLibrary", () => ({
  useSessionLibrary: () => mocks.sessions
}));

vi.mock("../src/composables/usePlanLibrary", () => ({
  usePlanLibrary: () => mocks.plans
}));

vi.mock("../src/composables/useKnowledgeBase", () => ({
  useKnowledgeBase: () => mocks.knowledge
}));

import AssistantPage from "../src/pages/AssistantPage.vue";
import KnowledgePage from "../src/pages/KnowledgePage.vue";
import SessionsPage from "../src/pages/SessionsPage.vue";
import PlansPage from "../src/pages/PlansPage.vue";
import PlanDetailPage from "../src/pages/PlanDetailPage.vue";
import WorkbenchPage from "../src/pages/WorkbenchPage.vue";

describe("Product pages", () => {
  beforeEach(() => {
    mocks.push.mockReset();
    mocks.auth.state.authenticated = false;
    mocks.auth.state.user = null;
    mocks.auth.state.capabilities = {
      can_manage_knowledge_base: false
    };
    mocks.auth.openDialog.mockReset();
    mocks.assistant.initialize.mockReset().mockResolvedValue("conversation-1");
    mocks.assistant.reconnectForIdentity.mockReset().mockResolvedValue("conversation-1");
    mocks.assistant.createConversation.mockReset().mockResolvedValue("conversation-2");
    mocks.assistant.sendMessage.mockReset().mockResolvedValue(null);
    mocks.assistant.resetConversation.mockReset().mockResolvedValue(null);
    mocks.assistant.openConversation.mockReset().mockResolvedValue("conversation-1");
    mocks.assistant.state.conversationId = "conversation-1";
    mocks.assistant.state.messages = [];
    mocks.assistant.state.composer = "";
    mocks.assistant.state.flash = "";
    mocks.assistant.state.error = "";
    mocks.assistant.busy = false;
    mocks.assistantLibrary.refreshConversations.mockReset().mockResolvedValue([]);
    mocks.assistantLibrary.renameConversation.mockReset().mockResolvedValue([]);
    mocks.assistantLibrary.removeConversation.mockReset().mockResolvedValue([]);
    mocks.assistantLibrary.state.loading = false;
    mocks.assistantLibrary.state.error = "";
    mocks.assistantLibrary.state.items = [
      {
        conversation_id: "conversation-1",
        title: "最近会话",
        latest_summary: "继续之前的讨论",
        message_count: 6
      }
    ];
    mocks.assistantLibrary.state.recentConversationId = "conversation-1";
    mocks.workbench.submitForm.mockReset().mockResolvedValue("run-1");
    mocks.workbench.resetForm.mockReset();
    mocks.workbench.setFlash.mockReset();
    mocks.workbench.state.runId = "run-1";
    mocks.workbench.state.view = "run";
    mocks.workbench.state.runStatus = "completed";
    mocks.workbench.state.steps = [];
    mocks.workbench.state.result = {
      trip_summary: "上海两日游草案"
    };
    mocks.workbench.state.error = "";
    mocks.workbench.state.flash = "";
    mocks.workbench.isRunning = { value: false };
    mocks.workbench.isRunView = { value: true };
    mocks.workbench.returnToForm.mockReset();
    mocks.planner.openSession.mockReset().mockResolvedValue("session-2");
    mocks.sessions.refreshSessions.mockReset().mockResolvedValue([]);
    mocks.plans.refreshPlans.mockReset().mockResolvedValue([]);
    mocks.plans.saveRunPlan.mockReset().mockResolvedValue({ plan_id: "plan-1" });
    mocks.plans.continueEditing.mockReset().mockResolvedValue({ session_id: "session-2" });
    mocks.plans.removePlan.mockReset().mockResolvedValue(true);
    mocks.plans.loadPlan.mockReset().mockResolvedValue(null);
    mocks.plans.state.loading = false;
    mocks.plans.state.error = "";
    mocks.plans.state.info = "已保存为草案。";
    mocks.plans.state.items = [];
    mocks.plans.state.activePlan = null;
    mocks.plans.state.count = 0;
    mocks.plans.state.statusCounts = {};
    mocks.knowledge.refresh.mockReset().mockResolvedValue({});
    mocks.knowledge.upload.mockReset().mockResolvedValue({});
    mocks.knowledge.retry.mockReset().mockResolvedValue({});
    mocks.knowledge.remove.mockReset().mockResolvedValue(true);
    mocks.knowledge.reindex.mockReset().mockResolvedValue({ queued: 1 });
    mocks.knowledge.clearFeedback.mockReset();
    mocks.knowledge.dispose.mockReset();
    mocks.knowledge.state.loading = false;
    mocks.knowledge.state.uploading = false;
    mocks.knowledge.state.reindexing = false;
    mocks.knowledge.state.retryingDocumentId = "";
    mocks.knowledge.state.error = "";
    mocks.knowledge.state.info = "";
    mocks.knowledge.state.knowledgeBase = {
      knowledge_base_id: "kb-1",
      name: "智能助手知识库"
    };
    mocks.knowledge.state.documents = [];
    mocks.knowledge.state.summary = {
      document_count: 0,
      ready_count: 0,
      processing_count: 0,
      failed_count: 0
    };
  });

  it("initializes the standalone assistant page", async () => {
    const wrapper = mount(AssistantPage, {
      global: {
        stubs: {
          ChatWorkspace: true
        }
      }
    });

    await flushPromises();

    expect(mocks.assistant.initialize).toHaveBeenCalledTimes(1);
    expect(mocks.assistantLibrary.refreshConversations).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain("最近会话");
    expect(wrapper.text()).toContain("新建会话");
    expect(wrapper.text()).not.toContain("独立对话入口");
  });

  it("creates a new assistant conversation from the assistant page", async () => {
    const wrapper = mount(AssistantPage, {
      global: {
        stubs: {
          ChatWorkspace: true
        }
      }
    });

    await flushPromises();
    await wrapper.findAll("button").find((button) => button.text() === "新建会话").trigger("click");

    expect(mocks.assistant.createConversation).toHaveBeenCalledTimes(1);
    expect(mocks.assistantLibrary.refreshConversations).toHaveBeenCalledTimes(2);
  });

  it("does not render success feedback when switching conversations", async () => {
    mocks.assistant.state.flash = "已切换到选中的助手会话。";
    mocks.assistant.state.conversationId = "conversation-1";
    mocks.assistantLibrary.state.items = [
      {
        conversation_id: "conversation-1",
        title: "最近会话",
        latest_summary: "继续之前的讨论",
        message_count: 6
      },
      {
        conversation_id: "conversation-2",
        title: "新的讨论",
        latest_summary: "切换到另一个上下文",
        message_count: 2
      }
    ];
    mocks.assistant.openConversation.mockReset().mockImplementation(async () => {
      await Promise.resolve();
      mocks.assistant.state.conversationId = "conversation-2";
      return "conversation-2";
    });

    const wrapper = mount(AssistantPage, {
      global: {
        stubs: {
          ChatWorkspace: true
        }
      }
    });

    await flushPromises();
    await wrapper.findAll(".assistant-conversation-card")[1].trigger("click");
    await flushPromises();

    expect(mocks.assistant.openConversation).toHaveBeenCalledWith("conversation-2");
    expect(wrapper.text()).not.toContain("已切换到选中的助手会话。");
  });

  it("opens a historical assistant conversation", async () => {
    mocks.assistantLibrary.state.recentConversationId = "conversation-42";
    mocks.assistantLibrary.state.items = [
      {
        conversation_id: "conversation-42",
        title: "重构讨论",
        latest_summary: "先拆分前后端职责"
      }
    ];

    const wrapper = mount(SessionsPage);
    await flushPromises();

    expect(wrapper.text()).toContain("最近会话");
    await wrapper.get("button.primary-button").trigger("click");

    expect(mocks.assistantLibrary.refreshConversations).toHaveBeenCalledTimes(1);
    expect(mocks.assistant.openConversation).toHaveBeenCalledWith("conversation-42");
    expect(mocks.push).toHaveBeenCalledWith("/");
  });

  it("loads the knowledge page for staff users", async () => {
    mocks.auth.state.capabilities.can_manage_knowledge_base = true;
    mocks.knowledge.state.documents = [
      {
        document_id: "doc-1",
        title: "北京资料",
        file_name: "beijing.md",
        status: "ready",
        chunk_count: 8,
        updated_at: "2026-03-24T10:00:00Z"
      }
    ];

    const wrapper = mount(KnowledgePage);
    await flushPromises();

    expect(mocks.knowledge.refresh).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain("beijing");
    expect(wrapper.text()).toContain("文档检索及管理");
    expect(wrapper.text()).toContain("MD");
    expect(wrapper.text()).not.toContain("beijing.md");
    expect(wrapper.text()).not.toContain("智能助手知识源");
  });

  it("uploads a knowledge document from the knowledge page", async () => {
    mocks.auth.state.capabilities.can_manage_knowledge_base = true;

    const wrapper = mount(KnowledgePage);
    await flushPromises();

    const file = new File(["# title"], "guide.md", { type: "text/markdown" });
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", {
      value: [file],
      configurable: true
    });
    await input.trigger("change");
    await wrapper.findAll("button").find((button) => button.text() === "确认上传").trigger("click");

    expect(mocks.knowledge.upload).toHaveBeenCalledTimes(1);
    expect(mocks.knowledge.upload).toHaveBeenCalledWith(file);
  });

  it("reindexes documents from the knowledge page", async () => {
    mocks.auth.state.capabilities.can_manage_knowledge_base = true;

    const wrapper = mount(KnowledgePage);
    await flushPromises();
    await wrapper.findAll(".stat-card")[3].trigger("click");
    expect(document.body.textContent).toContain("刷新知识库索引");
    await [...document.body.querySelectorAll("button")]
      .find((button) => button.textContent === "确认刷新")
      .click();
    await flushPromises();

    expect(mocks.knowledge.reindex).toHaveBeenCalledTimes(1);
  });

  it("retries a failed knowledge document from the knowledge page", async () => {
    mocks.auth.state.capabilities.can_manage_knowledge_base = true;
    mocks.knowledge.state.documents = [
      {
        document_id: "doc-failed",
        title: ".md",
        file_name: "杭州资料.md",
        status: "failed",
        chunk_count: 0,
        error_message: "当前仅支持带文本层的 pdf",
        updated_at: "2026-03-24T10:00:00Z"
      }
    ];

    const wrapper = mount(KnowledgePage);
    await flushPromises();
    await wrapper.get('button[title="重试"]').trigger("click");

    expect(mocks.knowledge.retry).toHaveBeenCalledTimes(1);
    expect(mocks.knowledge.retry).toHaveBeenCalledWith("doc-failed");
  });

  it("shows the permission prompt for plans when logged out", async () => {
    const wrapper = mount(PlansPage);
    await flushPromises();

    expect(wrapper.text()).toContain("登录后才能查看和管理历史方案");
    await wrapper.get("button.primary-button").trigger("click");
    expect(mocks.auth.openDialog).toHaveBeenCalledTimes(1);
  });

  it("continues editing from plan detail when authenticated", async () => {
    mocks.auth.state.authenticated = true;
    mocks.plans.state.activePlan = {
      plan_id: "plan-9",
      title: "大阪草案",
      version: 2,
      status: "draft",
      source_type: "chat_session",
      constraints_snapshot: { destination: "大阪", days: 4 },
      result_snapshot: { trip_summary: "大阪四日游" }
    };
    mocks.plans.loadPlan.mockImplementation(async () => mocks.plans.state.activePlan);

    const wrapper = mount(PlanDetailPage, {
      props: {
        planId: "plan-9"
      },
      global: {
        stubs: {
          ResultPanel: true
        }
      }
    });

    await flushPromises();
    await wrapper.get("button.primary-button").trigger("click");

    expect(mocks.plans.loadPlan).toHaveBeenCalledWith("plan-9");
    expect(mocks.plans.continueEditing).toHaveBeenCalledWith("plan-9");
    expect(mocks.push).toHaveBeenCalledWith("/");
  });

  it("saves the current workbench result as a draft", async () => {
    mocks.auth.state.authenticated = true;

    const wrapper = mount(WorkbenchPage, {
      global: {
        stubs: {
          PlannerForm: true,
          ResultPanel: true,
          ExecutionTimeline: true
        }
      }
    });

    await flushPromises();
    expect(wrapper.text()).toContain("保存草案");
    await wrapper.findAll("button").find((button) => button.text() === "保存草案").trigger("click");
    expect(mocks.workbench.setFlash).toHaveBeenCalledWith("正在保存草案...");
    await flushPromises();

    expect(mocks.plans.saveRunPlan).toHaveBeenCalledWith("run-1", "draft");
    expect(mocks.workbench.setFlash).toHaveBeenCalledWith("已保存为草案。");
  });

  it("shows only the planner form before a run starts", async () => {
    mocks.workbench.state.runId = "";
    mocks.workbench.state.view = "form";
    mocks.workbench.state.runStatus = "idle";
    mocks.workbench.state.result = null;
    mocks.workbench.isRunView = { value: false };

    const wrapper = mount(WorkbenchPage, {
      global: {
        stubs: {
          ResultPanel: true,
          ExecutionTimeline: true
        }
      }
    });

    await flushPromises();

    expect(wrapper.find("execution-timeline-stub").exists()).toBe(false);
    expect(wrapper.find("result-panel-stub").exists()).toBe(false);
  });

  it("submits the workbench form", async () => {
    mocks.workbench.state.view = "form";
    mocks.workbench.state.runId = "";
    mocks.workbench.state.result = null;
    mocks.workbench.isRunView = { value: false };

    const wrapper = mount(WorkbenchPage, {
      global: {
        stubs: {
          ResultPanel: true,
          ExecutionTimeline: true
        }
      }
    });

    await flushPromises();
    await wrapper.getComponent({ name: "PlannerForm" }).vm.$emit("submit");

    expect(mocks.workbench.submitForm).toHaveBeenCalledTimes(1);
  });

  it("returns from run view back to form editing", async () => {
    const wrapper = mount(WorkbenchPage, {
      global: {
        stubs: {
          PlannerForm: true,
          ResultPanel: true,
          ExecutionTimeline: true
        }
      }
    });

    await flushPromises();
    await wrapper.findAll("button").find((button) => button.text() === "返回表单").trigger("click");

    expect(mocks.workbench.returnToForm).toHaveBeenCalledTimes(1);
  });

  it("does not show save actions for workbench clarification results", async () => {
    mocks.workbench.state.result = {
      trip_summary: "还需要补充信息后才能继续生成。",
      status: "clarification"
    };

    const wrapper = mount(WorkbenchPage, {
      global: {
        stubs: {
          PlannerForm: true,
          ResultPanel: true,
          ExecutionTimeline: true
        }
      }
    });

    await flushPromises();

    expect(wrapper.text()).not.toContain("保存草案");
    expect(wrapper.text()).toContain("等待补充信息");
  });
});
