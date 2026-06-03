from __future__ import annotations

from datetime import datetime, timezone
import logging

from planner.domain.schemas import (
    AccommodationRecommendation,
    BudgetBreakdown,
    ConfirmedConstraints,
    ExecutionStep,
    RecommendationItem,
    SourceReference,
    TransportOption,
    TripPlanOutput,
    WarningItem,
    WorkflowState,
)
from planner.integrations.qwen import QwenPlannerClient
from planner.services.live_data import LiveDataService
from planner.services.planning_context import build_clarification_questions
from planner.services.route_directions import RouteDirectionsService

logger = logging.getLogger(__name__)


class PlanningNodes:
    def __init__(
        self,
        live_data_service: LiveDataService,
        model_client: QwenPlannerClient,
        route_directions_service: RouteDirectionsService,
    ) -> None:
        self.live_data_service = live_data_service
        self.model_client = model_client
        self.route_directions_service = route_directions_service

    def normalize_input(self, state: WorkflowState) -> tuple[WorkflowState, ExecutionStep]:
        request = state.request.model_copy(deep=True)
        context = state.planning_context
        if context is not None:
            state.assistant_mode = context.assistant_mode
            state.confirmed_constraints = context.confirmed_constraints.model_copy(
                deep=True
            )
            state.conversation_summary = self._build_conversation_summary(context)
            state.revision_notes = context.revision_notes
            state.plan_state = "draft" if context.mode == "chat" else "final"
            if context.previous_result is not None:
                state.assumptions.append(
                    "已基于上一轮草案和已确认条件继续更新回复。"
                )
        else:
            state.assistant_mode = "travel"
            state.confirmed_constraints = ConfirmedConstraints.from_request(request)

        if not request.city:
            request.city = request.destination
            state.assumptions.append("已根据目的地自动补全城市信息。")

        if state.confirmed_constraints.must_visit_pois and not request.interests:
            request.interests = state.confirmed_constraints.must_visit_pois

        if not request.interests and state.assistant_mode == "travel":
            request.interests = ["landmarks", "culture"]
            state.assumptions.append("未提供主题偏好，已默认补充地标与文化体验。")

        if state.confirmed_constraints.pace_preference:
            state.assumptions.append(
                f"已记录节奏偏好：{state.confirmed_constraints.pace_preference}。"
            )

        if state.confirmed_constraints.avoid_pois:
            state.assumptions.append(
                "已记录排除点位："
                + ", ".join(state.confirmed_constraints.avoid_pois)
                + "。"
            )

        state.normalized_request = request
        step = ExecutionStep(
            key="normalize_input",
            title="规范化用户输入",
            status="completed",
            detail="已整理当前回合输入、历史上下文和默认值。",
            finished_at=datetime.now(timezone.utc),
        )
        return state, step

    def assess_requirements(self, state: WorkflowState) -> tuple[WorkflowState, ExecutionStep]:
        chat_mode = bool(
            state.planning_context is not None and state.planning_context.mode == "chat"
        )
        state.clarification_questions = build_clarification_questions(
            state.confirmed_constraints,
            chat_mode=chat_mode,
            assistant_mode=state.assistant_mode,
        )
        status = "completed"
        detail = "当前信息足以继续生成回复。"
        if state.assistant_mode == "general":
            detail = "检测到泛问题模式，将由模型直接以中文回复并适度引导到旅行规划。"
        elif state.clarification_questions:
            detail = "旅行规划信息暂不完整，本轮将由模型输出澄清问题。"
        step = ExecutionStep(
            key="assess_requirements",
            title="判断回复模式",
            status=status,
            detail=detail,
            finished_at=datetime.now(timezone.utc),
        )
        return state, step

    def fetch_live_data(self, state: WorkflowState) -> tuple[WorkflowState, ExecutionStep]:
        if state.assistant_mode == "general":
            step = ExecutionStep(
                key="fetch_live_data",
                title="查询实时数据",
                status="completed",
                detail="当前为泛问题回复，跳过旅游实时数据检索。",
                finished_at=datetime.now(timezone.utc),
            )
            return state, step

        if state.clarification_questions:
            step = ExecutionStep(
                key="fetch_live_data",
                title="查询实时数据",
                status="completed",
                detail="关键信息尚未齐全，本轮先由模型澄清，暂不触发实时检索。",
                finished_at=datetime.now(timezone.utc),
            )
            return state, step

        request = state.normalized_request or state.request
        bundle = self.live_data_service.fetch_all(request)
        state.live_data = bundle

        degraded = any(item.status != "success" for item in bundle.provider_statuses)
        detail = "Fetched attractions, food, and hotel candidates."
        if degraded:
            detail = "已完成实时检索，但部分数据源未返回完整结果，建议结合提示继续复核。"
        else:
            detail = "已获取景点、美食和住宿候选数据。"
        if degraded:
            logger.warning(
                "Workflow step degraded: step=fetch_live_data destination=%s assistant_mode=%s provider_issues=%s",
                request.destination,
                state.assistant_mode,
                self._provider_issue_messages(bundle.provider_statuses),
            )

        step = ExecutionStep(
            key="fetch_live_data",
            title="查询实时数据",
            status="completed",
            detail=detail,
            provider_statuses=bundle.provider_statuses,
            finished_at=datetime.now(timezone.utc),
        )
        return state, step

    def validate_live_data(self, state: WorkflowState) -> tuple[WorkflowState, ExecutionStep]:
        if state.assistant_mode == "general":
            step = ExecutionStep(
                key="validate_live_data",
                title="校验数据完备度",
                status="completed",
                detail="当前为泛问题回复，跳过旅游数据完备度校验。",
                finished_at=datetime.now(timezone.utc),
            )
            return state, step

        if state.clarification_questions:
            step = ExecutionStep(
                key="validate_live_data",
                title="校验数据完备度",
                status="completed",
                detail="等待用户补充旅行条件，本轮不执行数据完备度判定。",
                finished_at=datetime.now(timezone.utc),
            )
            return state, step

        bundle = state.live_data
        if not bundle.pois:
            state.assumptions.append(
                "未检索到合适的实时景点候选，相关建议可能偏宽泛。"
            )
        if not bundle.foods:
            state.assumptions.append(
                "未检索到合适的实时餐饮候选，餐饮建议需要人工再确认。"
            )
        if not bundle.hotels:
            state.assumptions.append(
                "未检索到合适的实时住宿候选，住宿建议会附带复核提示。"
            )
        elif any(item.source.provider == "baidu" for item in bundle.hotels):
            state.assumptions.append(
                "住宿候选来自地图地点检索，房态、价格和预算适配度仍需人工确认。"
            )

        if not bundle.pois and not bundle.foods and not bundle.hotels:
            state.warnings.append(
                WarningItem(
                    severity="warning",
                    message="实时数据源未返回可用候选，本轮会先给出说明或澄清建议。",
                )
            )

        status = "completed"
        if not bundle.pois and not bundle.foods and not bundle.hotels:
            logger.warning(
                "Workflow step completed with review warnings: step=validate_live_data destination=%s assistant_mode=%s provider_issues=%s assumptions=%s warnings=%s",
                (state.normalized_request or state.request).destination,
                state.assistant_mode,
                self._provider_issue_messages(bundle.provider_statuses),
                state.assumptions,
                [item.message for item in state.warnings],
            )
        step = ExecutionStep(
            key="validate_live_data",
            title="校验数据完备度",
            status=status,
            detail="已根据实时数据返回情况补充复核说明和风险提示。",
            provider_statuses=bundle.provider_statuses,
            finished_at=datetime.now(timezone.utc),
        )
        return state, step

    def plan_trip(self, state: WorkflowState) -> tuple[WorkflowState, ExecutionStep]:
        output = self.model_client.generate_trip_plan(
            request=state.normalized_request or state.request,
            attractions=state.live_data.pois,
            foods=state.live_data.foods,
            hotels=state.live_data.hotels,
            assumptions=state.assumptions,
            source_references=self._collect_sources(state),
            degraded=any(
                provider.status != "success"
                for provider in state.live_data.provider_statuses
            ),
            confirmed_constraints=state.confirmed_constraints,
            conversation_summary=state.conversation_summary,
            previous_result=state.planning_context.previous_result
            if state.planning_context is not None
            else None,
            latest_user_message=state.planning_context.latest_user_message
            if state.planning_context is not None
            else None,
            assistant_mode=state.assistant_mode,
            suggested_clarification_questions=state.clarification_questions,
        )

        state.summary = output.trip_summary
        state.assistant_mode = output.assistant_mode
        state.conversation_summary = (
            output.conversation_summary or state.conversation_summary
        )
        state.itinerary = output.daily_itinerary
        state.budget_breakdown = output.budget_breakdown
        state.transportation = output.transportation
        state.accommodation = output.accommodation
        state.recommendations = output.recommendations
        state.alternatives = output.alternatives or state.alternatives
        state.clarification_questions = (
            output.clarification_questions or state.clarification_questions
        )
        for assumption in output.assumptions:
            if assumption not in state.assumptions:
                state.assumptions.append(assumption)
        state.warnings.extend(output.warnings)
        state.status = output.status
        if output.status == "clarification":
            state.plan_state = "clarification"
        elif state.assistant_mode == "general":
            state.plan_state = "final"
        if output.status == "clarification":
            logger.warning(
                "Workflow model step returned clarification output: step=plan_trip output_status=%s destination=%s assistant_mode=%s provider_issues=%s warnings=%s assumptions=%s clarification_count=%s",
                output.status,
                (state.normalized_request or state.request).destination,
                state.assistant_mode,
                self._provider_issue_messages(state.live_data.provider_statuses),
                [item.message for item in output.warnings],
                output.assumptions,
                len(output.clarification_questions),
            )

        step = ExecutionStep(
            key="plan_trip",
            title="生成模型回复",
            status="completed",
            detail=(
                "已由模型生成中文澄清回复。"
                if output.status == "clarification"
                else "已由模型生成中文回复与结构化结果。"
            ),
            finished_at=datetime.now(timezone.utc),
        )
        return state, step

    def build_route_plan(self, state: WorkflowState) -> tuple[WorkflowState, ExecutionStep]:
        if state.assistant_mode == "general":
            step = ExecutionStep(
                key="build_route_plan",
                title="构建路段衔接",
                status="completed",
                detail="当前为泛问题回复，不生成路线衔接信息。",
                finished_at=datetime.now(timezone.utc),
            )
            return state, step

        if state.status == "clarification":
            step = ExecutionStep(
                key="build_route_plan",
                title="构建路段衔接",
                status="completed",
                detail="当前处于澄清阶段，暂不生成路段衔接信息。",
                finished_at=datetime.now(timezone.utc),
            )
            return state, step

        overview, itinerary, stops, legs, alternatives, warnings = (
            self.route_directions_service.build_route_plan(
                request=state.normalized_request or state.request,
                confirmed_constraints=state.confirmed_constraints,
                itinerary=state.itinerary,
                live_data=state.live_data,
            )
        )
        state.itinerary = itinerary
        state.route_overview = overview
        state.route_stops = stops
        state.route_legs = legs
        state.alternatives = alternatives or state.alternatives
        state.warnings.extend(warnings)

        degraded = any(leg.status != "live" for leg in legs)
        if degraded:
            degraded_legs = [
                f"{leg.from_stop_name}->{leg.to_stop_name}:{leg.status}:{leg.source.note if leg.source else ''}"
                for leg in legs
                if leg.status != "live"
            ]
            logger.warning(
                "Workflow step degraded: step=build_route_plan destination=%s degraded_legs=%s",
                (state.normalized_request or state.request).destination,
                degraded_legs,
            )
        step = ExecutionStep(
            key="build_route_plan",
            title="构建路段衔接",
            status="completed",
            detail=(
                "已生成路段衔接，但部分结果来自启发式估算。"
                if degraded
                else "已基于实时地图能力生成停靠点之间的衔接建议。"
            ),
            finished_at=datetime.now(timezone.utc),
        )
        return state, step

    def verify_plan_consistency(self, state: WorkflowState) -> tuple[WorkflowState, ExecutionStep]:
        budget = (
            state.normalized_request.budget if state.normalized_request else state.request.budget
        )
        if (
            budget
            and state.budget_breakdown.estimated_total
            and state.budget_breakdown.estimated_total > budget
        ):
            state.warnings.append(
                WarningItem(
                    severity="warning",
                    message="预算测算超过用户预算，建议手动调整路线或住宿标准。",
                )
            )

        if len(state.route_stops) >= 2 and len(state.route_legs) < len(state.route_stops) - 1:
            state.warnings.append(
                WarningItem(
                    severity="warning",
                    message="部分相邻路段未能成功估算，请人工检查换乘与转场方式。",
                )
            )

        for stop in state.route_stops:
            if any(
                phrase in stop.name or stop.name in phrase
                for phrase in state.confirmed_constraints.avoid_pois
            ):
                state.warnings.append(
                    WarningItem(
                        severity="warning",
                        message=f"当前方案中的 {stop.name} 与用户排除点位条件冲突。",
                    )
                )

        step = ExecutionStep(
            key="verify_plan_consistency",
            title="校验结果一致性",
            status="completed",
            detail="已检查预算、路段衔接和约束一致性。",
            finished_at=datetime.now(timezone.utc),
        )
        return state, step

    def assemble_output(self, state: WorkflowState) -> tuple[WorkflowState, TripPlanOutput, ExecutionStep]:
        output = TripPlanOutput(
            status=state.status if state.status != "running" else "success",
            plan_state=state.plan_state,
            assistant_mode=state.assistant_mode,
            trip_summary=state.summary or "当前回复已准备好。",
            conversation_summary=state.conversation_summary,
            assumptions=state.assumptions,
            execution_summary=[],
            confirmed_constraints=state.confirmed_constraints,
            route_overview=state.route_overview,
            route_stops=state.route_stops,
            route_legs=state.route_legs,
            alternatives=state.alternatives,
            daily_itinerary=state.itinerary,
            budget_breakdown=state.budget_breakdown or BudgetBreakdown(),
            transportation=state.transportation
            or [
                TransportOption(
                    mode="城市交通",
                    recommendation="建议优先地铁与步行结合，兼顾效率和稳定性。",
                )
            ],
            accommodation=state.accommodation
            or AccommodationRecommendation(
                summary="建议优先住在主要活动片区附近，减少来回折返。"
            ),
            attractions=state.live_data.pois[:6],
            food_recommendations=state.live_data.foods[:6],
            recommendations=state.recommendations
            or [
                RecommendationItem(
                    title="每天预留一个机动时段",
                    description="核心城区的排队、天气和换乘节奏波动较大，留白会更稳妥。",
                )
            ],
            warnings=state.warnings,
            source_references=self._collect_sources(state),
            clarification_questions=state.clarification_questions,
            revision_notes=state.revision_notes,
        )
        step = ExecutionStep(
            key="assemble_output",
            title="组装最终输出",
            status="completed",
            detail="",
            finished_at=datetime.now(timezone.utc),
        )
        return state, output, step

    def fallback_or_clarify(self, state: WorkflowState) -> tuple[WorkflowState, TripPlanOutput, ExecutionStep]:
        clarification = bool(state.clarification_questions)
        output = TripPlanOutput(
            status="clarification" if clarification else "failed",
            plan_state="clarification" if clarification else state.plan_state,
            assistant_mode=state.assistant_mode,
            trip_summary="当前需要进一步澄清，或稍后重试。",
            conversation_summary=state.conversation_summary,
            assumptions=state.assumptions,
            execution_summary=[],
            confirmed_constraints=state.confirmed_constraints,
            route_overview=state.route_overview,
            route_stops=[],
            route_legs=[],
            alternatives=state.alternatives,
            daily_itinerary=state.itinerary,
            budget_breakdown=state.budget_breakdown,
            transportation=state.transportation,
            accommodation=state.accommodation,
            attractions=state.live_data.pois,
            food_recommendations=state.live_data.foods,
            recommendations=state.recommendations,
            warnings=state.warnings
            + [
                WarningItem(
                    severity="warning" if clarification else "critical",
                    message=state.failure_reason
                    or (
                        "还需要一点关键信息，我才能继续细化路线。"
                        if clarification
                        else "系统暂时无法生成可验证的回复，请稍后重试。"
                    ),
                )
            ],
            source_references=self._collect_sources(state),
            clarification_questions=state.clarification_questions,
            revision_notes=state.revision_notes,
        )
        step = ExecutionStep(
            key="fallback_or_clarify",
            title="返回澄清或失败说明",
            status="completed" if clarification else "failed",
            detail="已返回结构化澄清问题或失败说明。",
            finished_at=datetime.now(timezone.utc),
        )
        logger.warning(
            "Workflow finalized with fallback_or_clarify: destination=%s status=%s failure_reason=%s clarification_count=%s",
            (state.normalized_request or state.request).destination,
            output.status,
            state.failure_reason,
            len(output.clarification_questions),
        )
        return state, output, step

    @staticmethod
    def _collect_sources(state: WorkflowState) -> list[SourceReference]:
        refs: list[SourceReference] = []
        refs.extend(item.source for item in state.live_data.pois)
        refs.extend(item.source for item in state.live_data.foods)
        refs.extend(item.source for item in state.live_data.hotels)
        refs.extend(
            item.source for item in state.route_legs if item.source is not None
        )
        unique: dict[tuple[str, str], SourceReference] = {}
        for ref in refs:
            unique[(ref.provider, ref.label)] = ref
        return list(unique.values())

    @staticmethod
    def _build_conversation_summary(context) -> str:
        messages = [message.content for message in context.conversation_messages[-4:]]
        if context.latest_user_message:
            messages.append(context.latest_user_message)
        summary = " | ".join(item for item in messages if item)
        return summary[:500]

    @staticmethod
    def _provider_issue_messages(provider_statuses) -> list[str]:
        return [
            f"{item.provider}:{item.status}:{item.message}"
            for item in provider_statuses
            if item.status != "success"
        ]
