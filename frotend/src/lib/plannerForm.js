function normalizeText(value, fallback = "") {
  if (typeof value !== "string") {
    return fallback;
  }
  return value;
}

function normalizeNumber(value, fallback = null) {
  if (value === "" || value === null || value === undefined) {
    return fallback;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function calculateTravelDays(startDate, endDate) {
  if (!startDate || !endDate) {
    return null;
  }

  const start = new Date(`${startDate}T00:00:00`);
  const end = new Date(`${endDate}T00:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) {
    return null;
  }

  const diffMs = end.getTime() - start.getTime();
  return Math.floor(diffMs / 86400000) + 1;
}

export function defaultPlannerForm() {
  return {
    destination: "",
    departure_city: "",
    travelers_count: 1,
    start_date: "",
    end_date: "",
    days: "",
    budget: "",
    interests: "",
    food_preferences: "",
    hotel_preferences: "",
    transport_preferences: "",
    constraints: "",
    notes: ""
  };
}

export function buildPlannerRequestPayload(form) {
  const inferredDays = calculateTravelDays(form.start_date, form.end_date);

  return {
    destination: normalizeText(form.destination),
    days: inferredDays || normalizeNumber(form.days, 1),
    budget: normalizeNumber(form.budget, null),
    start_date: form.start_date || null,
    end_date: form.end_date || null,
    departure_city: normalizeText(form.departure_city, "") || null,
    travelers_count: normalizeNumber(form.travelers_count, 1) || 1,
    interests: normalizeText(form.interests),
    food_preferences: normalizeText(form.food_preferences),
    hotel_preferences: normalizeText(form.hotel_preferences),
    transport_preferences: normalizeText(form.transport_preferences),
    constraints: normalizeText(form.constraints),
    notes: normalizeText(form.notes)
  };
}

export function seedPlannerFormFromConstraints(constraints = {}) {
  const defaults = defaultPlannerForm();
  const startDate = constraints.start_date || defaults.start_date;
  const endDate = constraints.end_date || defaults.end_date;
  const inferredDays = calculateTravelDays(startDate, endDate);

  return {
    ...defaults,
    destination: constraints.destination || defaults.destination,
    departure_city: constraints.departure_city || defaults.departure_city,
    travelers_count: constraints.travelers_count || defaults.travelers_count,
    start_date: startDate,
    end_date: endDate,
    days: constraints.days || inferredDays || defaults.days,
    budget: constraints.budget ?? defaults.budget,
    interests: (constraints.interests || []).join(", ") || defaults.interests,
    food_preferences: (constraints.food_preferences || []).join(", ") || defaults.food_preferences,
    hotel_preferences: (constraints.hotel_preferences || []).join(", ") || defaults.hotel_preferences,
    transport_preferences: (constraints.transport_preferences || []).join(", ") || defaults.transport_preferences,
    constraints: (constraints.constraints || []).join(", ") || defaults.constraints,
    notes: constraints.notes || defaults.notes
  };
}
