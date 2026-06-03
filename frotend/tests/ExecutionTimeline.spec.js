import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ExecutionTimeline from "../src/components/ExecutionTimeline.vue";

describe("ExecutionTimeline", () => {
  it("renders execution steps and provider statuses", () => {
    const wrapper = mount(ExecutionTimeline, {
      props: {
        status: "running",
        steps: [
          {
            key: "fetch_live_data",
            title: "查询实时数据",
            status: "completed",
            detail: "已完成实时检索，但部分数据仍建议复核。",
            provider_statuses: [{ provider: "amap", status: "success" }]
          }
        ]
      }
    });

    expect(wrapper.text()).toContain("生成进度");
    expect(wrapper.text()).toContain("查询实时数据");
    expect(wrapper.text()).toContain("高德地图");
  });
});
