import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  route: {
    path: "/"
  },
  auth: {
    state: {
      authenticated: true,
      capabilities: {
        can_manage_knowledge_base: false
      }
    },
    userLabel: "admin",
    restore: vi.fn(),
    logout: vi.fn(),
    openDialog: vi.fn()
  }
}));

vi.mock("vue-router", () => ({
  RouterLink: {
    props: ["to"],
    template: "<a :href=\"to\"><slot /></a>"
  },
  RouterView: {
    template: "<div />"
  },
  useRoute: () => mocks.route
}));

vi.mock("../src/composables/useAuth", () => ({
  useAuth: () => mocks.auth
}));

import App from "../src/App.vue";

describe("App shell navigation", () => {
  beforeEach(() => {
    mocks.auth.restore.mockReset().mockResolvedValue(true);
    mocks.auth.logout.mockReset().mockResolvedValue(true);
    mocks.auth.state.authenticated = true;
    mocks.auth.state.capabilities.can_manage_knowledge_base = false;
  });

  it("hides knowledge navigation when the user lacks permission", () => {
    const wrapper = mount(App);
    expect(wrapper.text()).not.toContain("知识库");
  });

  it("shows knowledge navigation for staff capability", () => {
    mocks.auth.state.capabilities.can_manage_knowledge_base = true;
    const wrapper = mount(App);
    expect(wrapper.text()).toContain("知识库");
  });
});
