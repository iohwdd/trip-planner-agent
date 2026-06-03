import { describe, expect, it } from "vitest";
import {
  buildPlannerRequestPayload,
  calculateTravelDays,
  defaultPlannerForm,
  seedPlannerFormFromConstraints
} from "../src/lib/plannerForm";

describe("plannerForm helpers", () => {
  it("starts with a blank workbench form by default", () => {
    const form = defaultPlannerForm();

    expect(form.destination).toBe("");
    expect(form.departure_city).toBe("");
    expect(form.days).toBe("");
    expect(form.budget).toBe("");
    expect(form.travelers_count).toBe(1);
  });

  it("calculates inclusive travel days from date range", () => {
    expect(calculateTravelDays("2026-04-10", "2026-04-12")).toBe(3);
    expect(calculateTravelDays("2026-04-12", "2026-04-10")).toBeNull();
  });

  it("builds request payload with new planning fields", () => {
    const payload = buildPlannerRequestPayload({
      ...defaultPlannerForm(),
      destination: "北京",
      departure_city: "杭州",
      travelers_count: 3,
      start_date: "2026-04-10",
      end_date: "2026-04-13",
      days: 1
    });

    expect(payload.destination).toBe("北京");
    expect(payload.departure_city).toBe("杭州");
    expect(payload.travelers_count).toBe(3);
    expect(payload.start_date).toBe("2026-04-10");
    expect(payload.end_date).toBe("2026-04-13");
    expect(payload.days).toBe(4);
  });

  it("hydrates form fields from constraints snapshot", () => {
    const form = seedPlannerFormFromConstraints({
      destination: "东京",
      departure_city: "上海",
      travelers_count: 4,
      start_date: "2026-05-01",
      end_date: "2026-05-04",
      budget: 12000
    });

    expect(form.destination).toBe("东京");
    expect(form.departure_city).toBe("上海");
    expect(form.travelers_count).toBe(4);
    expect(form.days).toBe(4);
    expect(form.budget).toBe(12000);
  });
});
