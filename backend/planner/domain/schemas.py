from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SourceReference(BaseModel):
    provider: str
    label: str
    url: str | None = None
    fetched_at: datetime | None = None
    status: Literal["live", "cached", "degraded", "unavailable"] = "live"
    note: str | None = None


class ProviderStatus(BaseModel):
    provider: str
    status: Literal["success", "degraded", "failed", "skipped"]
    message: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class POICandidate(BaseModel):
    id: str
    name: str
    city: str | None = None
    district: str | None = None
    address: str | None = None
    category: str | None = None
    location: str | None = None
    rating: float | None = None
    source: SourceReference


class FoodCandidate(BaseModel):
    id: str
    name: str
    city: str | None = None
    address: str | None = None
    location: str | None = None
    cuisine: str | None = None
    average_cost: float | None = None
    rating: float | None = None
    source: SourceReference


class HotelCandidate(BaseModel):
    id: str
    name: str
    city: str | None = None
    address: str | None = None
    location: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    rating: float | None = None
    source: SourceReference


class TravelDataBundle(BaseModel):
    pois: list[POICandidate] = Field(default_factory=list)
    foods: list[FoodCandidate] = Field(default_factory=list)
    hotels: list[HotelCandidate] = Field(default_factory=list)
    provider_statuses: list[ProviderStatus] = Field(default_factory=list)


class TripPlanningRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    destination: str
    days: int = Field(ge=1, le=30)
    budget: float | None = Field(default=None, ge=0)
    city: str | None = None
    departure_city: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    travelers_count: int = Field(default=1, ge=1, le=20)
    interests: list[str] = Field(default_factory=list)
    food_preferences: list[str] = Field(default_factory=list)
    hotel_preferences: list[str] = Field(default_factory=list)
    transport_preferences: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator(
        "interests",
        "food_preferences",
        "hotel_preferences",
        "transport_preferences",
        "constraints",
        mode="before",
    )
    @classmethod
    def normalize_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return [str(item).strip() for item in value if str(item).strip()]

    @model_validator(mode="after")
    def validate_dates(self) -> "TripPlanningRequest":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("返程日期不能早于出发日期")
        if self.start_date and self.end_date:
            inferred_days = (self.end_date - self.start_date).days + 1
            if inferred_days <= 0:
                raise ValueError("日期范围无效")
            self.days = inferred_days
        return self


class ConfirmedConstraints(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    destination: str | None = None
    city: str | None = None
    departure_city: str | None = None
    days: int | None = Field(default=None, ge=1, le=30)
    budget: float | None = Field(default=None, ge=0)
    start_date: date | None = None
    end_date: date | None = None
    travelers_count: int | None = Field(default=None, ge=1, le=20)
    interests: list[str] = Field(default_factory=list)
    must_visit_pois: list[str] = Field(default_factory=list)
    avoid_pois: list[str] = Field(default_factory=list)
    food_preferences: list[str] = Field(default_factory=list)
    hotel_preferences: list[str] = Field(default_factory=list)
    transport_preferences: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    notes: str | None = None
    pace_preference: str | None = None

    @field_validator(
        "interests",
        "must_visit_pois",
        "avoid_pois",
        "food_preferences",
        "hotel_preferences",
        "transport_preferences",
        "constraints",
        mode="before",
    )
    @classmethod
    def normalize_constraints_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return [str(item).strip() for item in value if str(item).strip()]

    @classmethod
    def from_request(cls, request: TripPlanningRequest) -> "ConfirmedConstraints":
        return cls(
            destination=request.destination,
            city=request.city,
            departure_city=request.departure_city,
            days=request.days,
            budget=request.budget,
            start_date=request.start_date,
            end_date=request.end_date,
            travelers_count=request.travelers_count,
            interests=request.interests,
            food_preferences=request.food_preferences,
            hotel_preferences=request.hotel_preferences,
            transport_preferences=request.transport_preferences,
            constraints=request.constraints,
            notes=request.notes,
        )

    def to_trip_request(self) -> TripPlanningRequest | None:
        if not self.destination or not self.days:
            return None
        interests = [*self.must_visit_pois, *self.interests]
        return TripPlanningRequest(
            destination=self.destination,
            city=self.city or self.destination,
            departure_city=self.departure_city,
            days=self.days,
            budget=self.budget,
            start_date=self.start_date,
            end_date=self.end_date,
            travelers_count=self.travelers_count or 1,
            interests=interests,
            food_preferences=self.food_preferences,
            hotel_preferences=self.hotel_preferences,
            transport_preferences=self.transport_preferences,
            constraints=self.constraints,
            notes=self.notes,
        )


class ClarificationQuestion(BaseModel):
    id: str
    field: str
    prompt: str
    reason: str | None = None
    required: bool = True


class ExecutionStep(BaseModel):
    key: str
    title: str
    status: Literal["queued", "running", "completed", "degraded", "failed"]
    detail: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    provider_statuses: list[ProviderStatus] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_step_status(cls, value: Any) -> Any:
        if str(value or "").strip().lower() == "degraded":
            return "completed"
        return value


class DailyPlan(BaseModel):
    day: int
    theme: str
    morning: list[str] = Field(default_factory=list)
    afternoon: list[str] = Field(default_factory=list)
    evening: list[str] = Field(default_factory=list)
    dining: list[str] = Field(default_factory=list)


class BudgetBreakdown(BaseModel):
    currency: str = "CNY"
    estimated_total: float | None = None
    accommodation: float | None = None
    transportation: float | None = None
    food: float | None = None
    activities: float | None = None
    note: str | None = None


class TransportOption(BaseModel):
    mode: str
    recommendation: str


class AccommodationRecommendation(BaseModel):
    summary: str = "优先选择靠近主要活动片区、步行或地铁接驳方便的住宿。"
    suggested_hotels: list[HotelCandidate] = Field(default_factory=list)


class RouteOverview(BaseModel):
    headline: str
    strategy: str
    pace: str | None = None
    total_stops: int = 0


class RouteStop(BaseModel):
    stop_id: str
    day: int
    order: int
    name: str
    kind: Literal["hotel", "poi", "food", "transfer", "flex"]
    time_slot: Literal[
        "checkin",
        "morning",
        "afternoon",
        "evening",
        "dining",
        "all_day",
    ] = "all_day"
    address: str | None = None
    district: str | None = None
    description: str | None = None
    location: str | None = None
    source: SourceReference | None = None


class RouteLeg(BaseModel):
    leg_id: str
    day: int
    from_stop_id: str
    from_stop_name: str
    to_stop_id: str
    to_stop_name: str
    recommended_mode: str
    estimated_duration_minutes: int | None = None
    estimated_distance_km: float | None = None
    suggestion: str
    source: SourceReference | None = None
    status: Literal["live", "estimated", "unavailable"] = "estimated"


class AlternativeRoute(BaseModel):
    title: str
    summary: str
    stop_names: list[str] = Field(default_factory=list)
    differences: list[str] = Field(default_factory=list)


class RevisionNote(BaseModel):
    summary: str
    changes: list[str] = Field(default_factory=list)


class RecommendationItem(BaseModel):
    title: str
    description: str


class WarningItem(BaseModel):
    severity: Literal["info", "warning", "critical"] = "info"
    message: str


class TripPlanOutput(BaseModel):
    status: Literal["success", "degraded", "clarification", "failed"]
    plan_state: Literal["clarification", "draft", "final"] = "final"
    assistant_mode: Literal["travel", "general"] = "travel"
    trip_summary: str
    conversation_summary: str = ""
    assumptions: list[str] = Field(default_factory=list)
    execution_summary: list[ExecutionStep] = Field(default_factory=list)
    confirmed_constraints: ConfirmedConstraints = Field(
        default_factory=ConfirmedConstraints
    )
    route_overview: RouteOverview | None = None
    route_stops: list[RouteStop] = Field(default_factory=list)
    route_legs: list[RouteLeg] = Field(default_factory=list)
    alternatives: list[AlternativeRoute] = Field(default_factory=list)
    daily_itinerary: list[DailyPlan] = Field(default_factory=list)
    budget_breakdown: BudgetBreakdown = Field(default_factory=BudgetBreakdown)
    transportation: list[TransportOption] = Field(default_factory=list)
    accommodation: AccommodationRecommendation = Field(
        default_factory=AccommodationRecommendation
    )
    attractions: list[POICandidate] = Field(default_factory=list)
    food_recommendations: list[FoodCandidate] = Field(default_factory=list)
    recommendations: list[RecommendationItem] = Field(default_factory=list)
    warnings: list[WarningItem] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    revision_notes: list[RevisionNote] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("status", mode="before")
    @classmethod
    def normalize_result_status(cls, value: Any) -> Any:
        if str(value or "").strip().lower() == "degraded":
            return "success"
        return value


class ChatMessage(BaseModel):
    message_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    message_type: Literal["text", "clarification", "result", "system"] = "text"
    turn_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PlanningContext(BaseModel):
    mode: Literal["form", "chat"] = "form"
    assistant_mode: Literal["travel", "general"] = "travel"
    request: TripPlanningRequest
    confirmed_constraints: ConfirmedConstraints = Field(
        default_factory=ConfirmedConstraints
    )
    conversation_messages: list[ChatMessage] = Field(default_factory=list)
    latest_user_message: str | None = None
    previous_result: TripPlanOutput | None = None
    revision_notes: list[RevisionNote] = Field(default_factory=list)


class ChatTurn(BaseModel):
    turn_id: str
    session_id: str
    status: Literal["queued", "running", "completed", "failed"]
    input_mode: Literal["chat", "form"] = "chat"
    user_message: ChatMessage
    request: TripPlanningRequest | None = None
    confirmed_constraints: ConfirmedConstraints = Field(
        default_factory=ConfirmedConstraints
    )
    steps: list[ExecutionStep] = Field(default_factory=list)
    result: TripPlanOutput | None = None
    assistant_message: ChatMessage | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatSession(BaseModel):
    session_id: str
    title: str = "未命名会话"
    status: Literal[
        "idle",
        "running",
        "waiting_for_clarification",
        "ready",
        "failed",
    ] = "idle"
    messages: list[ChatMessage] = Field(default_factory=list)
    turns: list[ChatTurn] = Field(default_factory=list)
    confirmed_constraints: ConfirmedConstraints = Field(
        default_factory=ConfirmedConstraints
    )
    latest_result: TripPlanOutput | None = None
    active_turn_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatTurnCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str | None = None
    request: TripPlanningRequest | None = None

    @model_validator(mode="after")
    def validate_turn_input(self) -> "ChatTurnCreateRequest":
        if not self.message and self.request is None:
            raise ValueError("Either message or request must be provided.")
        return self


class WorkflowState(BaseModel):
    request: TripPlanningRequest
    planning_context: PlanningContext | None = None
    assistant_mode: Literal["travel", "general"] = "travel"
    normalized_request: TripPlanningRequest | None = None
    confirmed_constraints: ConfirmedConstraints = Field(
        default_factory=ConfirmedConstraints
    )
    live_data: TravelDataBundle = Field(default_factory=TravelDataBundle)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[WarningItem] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    conversation_summary: str = ""
    route_overview: RouteOverview | None = None
    route_stops: list[RouteStop] = Field(default_factory=list)
    route_legs: list[RouteLeg] = Field(default_factory=list)
    alternatives: list[AlternativeRoute] = Field(default_factory=list)
    revision_notes: list[RevisionNote] = Field(default_factory=list)
    plan_state: Literal["clarification", "draft", "final"] = "final"
    itinerary: list[DailyPlan] = Field(default_factory=list)
    transportation: list[TransportOption] = Field(default_factory=list)
    accommodation: AccommodationRecommendation = Field(
        default_factory=AccommodationRecommendation
    )
    recommendations: list[RecommendationItem] = Field(default_factory=list)
    summary: str = ""
    budget_breakdown: BudgetBreakdown = Field(default_factory=BudgetBreakdown)
    status: Literal["running", "success", "degraded", "clarification", "failed"] = (
        "running"
    )
    failure_reason: str | None = None


class PlannerRun(BaseModel):
    run_id: str
    status: Literal["queued", "running", "completed", "failed"]
    request: TripPlanningRequest
    steps: list[ExecutionStep] = Field(default_factory=list)
    result: TripPlanOutput | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
