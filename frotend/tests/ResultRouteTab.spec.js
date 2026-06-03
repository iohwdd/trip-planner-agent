import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ResultRouteTab from "../src/components/ResultRouteTab.vue";

describe("ResultRouteTab", () => {
  it("fills empty itinerary slots from route stops", () => {
    const wrapper = mount(ResultRouteTab, {
      props: {
        result: {
          route_stops: [
            {
              stop_id: "poi-1",
              day: 1,
              order: 1,
              name: "故宫",
              kind: "poi",
              time_slot: "morning"
            },
            {
              stop_id: "poi-2",
              day: 1,
              order: 2,
              name: "景山公园",
              kind: "poi",
              time_slot: "afternoon"
            },
            {
              stop_id: "food-1",
              day: 1,
              order: 3,
              name: "四季民福",
              kind: "food",
              time_slot: "dining"
            }
          ],
          route_legs: [],
          daily_itinerary: [
            {
              day: 1,
              theme: "北京经典线",
              morning: [],
              afternoon: ["待补充"],
              evening: [],
              dining: ["四季民福"]
            }
          ]
        },
        routeDays: [
          {
            day: 1,
            theme: "北京经典线",
            stops: [
              { stop_id: "poi-1", day: 1, order: 1, name: "故宫", kind: "poi", time_slot: "morning" }
            ],
            legs: [],
            totalMinutes: 0,
            totalDistance: null
          }
        ],
        activeRouteDay: 1,
        activeRouteDayData: {
          day: 1,
          theme: "北京经典线",
          stops: [
            { stop_id: "poi-1", day: 1, order: 1, name: "故宫", kind: "poi", time_slot: "morning" }
          ],
          legs: [],
          totalMinutes: 0,
          totalDistance: null
        },
        formatTimeSlot: (value) => value,
        formatStopKind: (value) => value,
        formatDuration: (value) => `${value} 分钟`,
        formatDistance: (value) => value || "距离待确认"
      }
    });

    expect(wrapper.text()).toContain("上午：故宫");
    expect(wrapper.text()).toContain("下午：景山公园");
    expect(wrapper.text()).toContain("餐饮：四季民福");
  });
});
