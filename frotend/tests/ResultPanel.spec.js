import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ResultPanel from "../src/components/ResultPanel.vue";

describe("ResultPanel", () => {
  it("renders route-specific result sections", async () => {
    const wrapper = mount(ResultPanel, {
      props: {
        result: {
          assistant_mode: "travel",
          status: "success",
          plan_state: "draft",
          trip_summary: "Shanghai 3-day route",
          conversation_summary: "预算 3500，两天半，喜欢博物馆和夜景",
          assumptions: ["Live POI data available"],
          confirmed_constraints: {
            destination: "上海",
            days: 3,
            budget: 3500,
            must_visit_pois: ["上海博物馆", "外滩"],
            transport_preferences: ["地铁", "打车"]
          },
          route_overview: {
            headline: "上海 3 天路线草案",
            strategy: "优先围绕同片区站点组织顺路动线。",
            total_stops: 4
          },
          route_stops: [
            {
              stop_id: "poi-1",
              day: 1,
              order: 1,
              name: "上海博物馆",
              kind: "poi",
              time_slot: "morning",
              address: "人民大道 201 号"
            }
          ],
          route_legs: [
            {
              leg_id: "leg-1",
              from_stop_name: "上海博物馆",
              to_stop_name: "外滩",
              recommended_mode: "地铁 / 公交",
              estimated_duration_minutes: 28,
              suggestion: "优先公共交通"
            }
          ],
          alternatives: [
            {
              title: "低折返替代路线",
              summary: "减少跨区移动"
            }
          ],
          revision_notes: [
            {
              summary: "已根据你的反馈压缩跨区移动。",
              changes: ["减少跨区转场", "保留外滩和上海博物馆"]
            }
          ],
          daily_itinerary: [
            {
              day: 1,
              theme: "Bund and museums",
              morning: ["The Bund"],
              afternoon: ["Museum"],
              evening: ["Riverside walk"],
              dining: ["Local restaurant"]
            }
          ],
          budget_breakdown: {
            estimated_total: 3200,
            currency: "CNY"
          },
          accommodation: {
            summary: "Stay near People's Square.",
            suggested_hotels: []
          },
          food_recommendations: [],
          attractions: [],
          recommendations: [],
          warnings: [],
          source_references: []
        }
      }
    });

    expect(wrapper.text()).toContain("Shanghai 3-day route");
    expect(wrapper.text()).toContain("路线预览");
    expect(wrapper.text()).toContain("替代路线");
    expect(wrapper.text()).toContain("草案态");
    expect(wrapper.text()).not.toContain("快速改一版");
    expect(wrapper.findAll(".result-confidence-band")).toHaveLength(1);
    expect(wrapper.find(".route-map-preview-card").exists()).toBe(true);
    expect(wrapper.find(".result-stage-grid").exists()).toBe(false);

    const html = wrapper.html();
    expect(html.indexOf("route-map-preview-card")).toBeGreaterThan(-1);
    expect(html.indexOf("result-confidence-band")).toBeGreaterThan(html.indexOf("route-map-preview-card"));

    await wrapper.get("button.result-tab:nth-child(2)").trigger("click");

    expect(wrapper.text()).toContain("停靠点顺序");
    expect(wrapper.text()).toContain("路段衔接");
  });

  it("renders actionable clarification flow instead of a dead-end warning card", async () => {
    const wrapper = mount(ResultPanel, {
      props: {
        result: {
          assistant_mode: "travel",
          status: "clarification",
          plan_state: "clarification",
          trip_summary: "还需要补几项关键信息后才能继续收敛路线。",
          clarification_questions: [
            {
              id: "q-1",
              field: "departure_date",
              prompt: "请问您计划哪天出发？",
              reason: "具体日期有助于判断排期与拥堵。"
            },
            {
              id: "q-2",
              field: "budget",
              prompt: "3500 元总预算中，您期望住宿每晚预算是多少？"
            }
          ],
          confirmed_constraints: {
            destination: "北京",
            days: 2,
            budget: 3500
          },
          source_references: []
        }
      }
    });

    expect(wrapper.text()).toContain("继续完成此方案");
    expect(wrapper.text()).toContain("还差 2 项关键信息");
    expect(wrapper.text()).toContain("只补这项");
    expect(wrapper.text()).not.toContain("仍需澄清");

    await wrapper.findAll("button").find((button) => button.text() === "填入补充模板").trigger("click");

    const [payload] = wrapper.emitted()["quick-prompt"][0];
    expect(payload).toContain("请按下面补充后继续生成旅行方案");
    expect(payload).toContain("出发日期");
  });
});
