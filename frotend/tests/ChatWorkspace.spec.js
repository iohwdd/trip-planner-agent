import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import ChatWorkspace from "../src/components/ChatWorkspace.vue";

describe("ChatWorkspace", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders messages and emits composer actions", async () => {
    const wrapper = mount(ChatWorkspace, {
      props: {
        messages: [
          {
            message_id: "m1",
            role: "user",
            content: "想在上海边走边逛一天，不要太赶"
          },
          {
            message_id: "m2",
            role: "assistant",
            content: "先从预算开始。"
          }
        ],
        composer: "预算 3000，两天"
      }
    });

    expect(wrapper.text()).toContain("先从预算开始。");
    expect(wrapper.get("textarea.composer-textarea").attributes("style")).toBeUndefined();
    expect(wrapper.find(".composer-actions-left").exists()).toBe(true);

    await wrapper.find("textarea").setValue("不要外滩，换成苏州河沿线");
    expect(wrapper.emitted("update:composer")).toBeTruthy();

    await wrapper.find(".primary-button").trigger("click");

    expect(wrapper.emitted("send")).toBeTruthy();
  });

  it("renders assistant markdown content as structured HTML", () => {
    const wrapper = mount(ChatWorkspace, {
      props: {
        messages: [
          {
            message_id: "m1",
            role: "assistant",
            content: "### 核心城区\n\n北京房价差异极大，**没有统一价格**。\n\n* 东城\n* 西城"
          }
        ]
      }
    });

    expect(wrapper.find(".message-content h3").text()).toBe("核心城区");
    expect(wrapper.find(".message-content strong").text()).toBe("没有统一价格");
    expect(wrapper.findAll(".message-content li")).toHaveLength(2);
  });

  it("scrolls to the latest message when the chat loads", async () => {
    vi.useFakeTimers();
    const rafSpy = vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => (
      window.setTimeout(() => callback(performance.now()), 0)
    ));
    const cancelRafSpy = vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => {
      window.clearTimeout(id);
    });

    const wrapper = mount(ChatWorkspace, {
      props: {
        messages: Array.from({ length: 6 }, (_, index) => ({
          message_id: `m${index + 1}`,
          role: index % 2 === 0 ? "user" : "assistant",
          content: `message ${index + 1}`
        })),
        composer: ""
      }
    });

    const scrollRegion = wrapper.get(".chat-scroll-region").element;
    Object.defineProperty(scrollRegion, "scrollHeight", {
      configurable: true,
      value: 640
    });
    scrollRegion.scrollTop = 0;

    await vi.runAllTimersAsync();

    expect(scrollRegion.scrollTop).toBe(640);

    cancelRafSpy.mockRestore();
    rafSpy.mockRestore();
  });

  it("keeps following the bottom while streaming content updates", async () => {
    vi.useFakeTimers();
    const rafSpy = vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => (
      window.setTimeout(() => callback(performance.now()), 0)
    ));
    const cancelRafSpy = vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => {
      window.clearTimeout(id);
    });

    const wrapper = mount(ChatWorkspace, {
      props: {
        busy: true,
        messages: [
          {
            message_id: "u1",
            role: "user",
            content: "帮我规划上海两天",
            message_type: "text"
          },
          {
            message_id: "a1",
            role: "assistant",
            content: "正在整理路线",
            message_type: "result"
          }
        ]
      }
    });

    const scrollRegion = wrapper.get(".chat-scroll-region").element;
    Object.defineProperty(scrollRegion, "clientHeight", {
      configurable: true,
      value: 320
    });
    Object.defineProperty(scrollRegion, "scrollHeight", {
      configurable: true,
      value: 680
    });
    scrollRegion.scrollTop = 0;

    await vi.runAllTimersAsync();
    expect(scrollRegion.scrollTop).toBe(360);

    Object.defineProperty(scrollRegion, "scrollHeight", {
      configurable: true,
      value: 880
    });

    await wrapper.setProps({
      messages: [
        {
          message_id: "u1",
          role: "user",
          content: "帮我规划上海两天",
          message_type: "text"
        },
        {
          message_id: "a1",
          role: "assistant",
          content: "正在整理路线，已经拿到第一批点位和预算信息",
          message_type: "result"
        }
      ]
    });

    await vi.runAllTimersAsync();
    expect(scrollRegion.scrollTop).toBe(560);

    cancelRafSpy.mockRestore();
    rafSpy.mockRestore();
  });

  it("pins to the bottom when history messages arrive after mount", async () => {
    vi.useFakeTimers();
    const rafSpy = vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => (
      window.setTimeout(() => callback(performance.now()), 0)
    ));
    const cancelRafSpy = vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => {
      window.clearTimeout(id);
    });

    const wrapper = mount(ChatWorkspace, {
      props: {
        messages: []
      }
    });

    const scrollRegion = wrapper.get(".chat-scroll-region").element;
    Object.defineProperty(scrollRegion, "clientHeight", {
      configurable: true,
      value: 320
    });
    Object.defineProperty(scrollRegion, "scrollHeight", {
      configurable: true,
      value: 1200
    });
    scrollRegion.scrollTop = 0;

    await wrapper.setProps({
      messages: [
        {
          message_id: "u1",
          role: "user",
          content: "历史消息 1"
        },
        {
          message_id: "a1",
          role: "assistant",
          content: "历史消息 2"
        }
      ]
    });

    await vi.runAllTimersAsync();

    expect(scrollRegion.scrollTop).toBe(880);

    cancelRafSpy.mockRestore();
    rafSpy.mockRestore();
  });
});
