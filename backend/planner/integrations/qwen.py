from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

try:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover - deterministic fallback remains available
    ChatPromptTemplate = None
    ChatOpenAI = None

from planner.domain.schemas import (
    AccommodationRecommendation,
    AlternativeRoute,
    BudgetBreakdown,
    ClarificationQuestion,
    ConfirmedConstraints,
    DailyPlan,
    FoodCandidate,
    HotelCandidate,
    POICandidate,
    RecommendationItem,
    RouteOverview,
    SourceReference,
    TransportOption,
    TripPlanOutput,
    TripPlanningRequest,
    WarningItem,
)
from planner.services.runtime_config import QwenConfig

logger = logging.getLogger(__name__)


class QwenPlannerClient:
    ASSISTANT_SYSTEM_PROMPT = (
        "你是一个中文智能助手。"
        "你需要直接、清晰地回答用户问题。"
        "除非用户主动要求，否则不要擅自切换成结构化旅行规划输出。"
        "如果问题不明确，优先给出简短澄清。"
    )
    SYSTEM_PROMPT = (
        "你是一位中文旅行规划智能助理，同时也能回答用户的泛问题。"
        "你的主要专长是旅游路线规划、目的地建议、出行方式、住宿、美食和景点串联。"
        "无论用户问什么，都必须先用中文直接回应用户，不要拒答。"
        "如果问题与旅行强相关，就优先给出结构化旅行规划；如果是泛问题，也要正常回答，"
        "并在合适时轻量引导用户继续使用你的旅行规划能力。"
        "你只能返回 JSON，不能返回 Markdown。"
        "顶层字段必须包含：status, plan_state, trip_summary, clarification_questions, "
        "daily_itinerary, budget_breakdown, transportation, recommendations, warnings, "
        "route_overview, alternatives。"
        "status 只能是 success、clarification。"
        "plan_state 只能是 clarification、draft、final。"
        "trip_summary 必须是中文字符串，直接作为面向用户的主要回复。"
        "当用户是泛问题或闲聊时：status=success，plan_state=final，"
        "daily_itinerary/route_overview/alternatives 可以为空，trip_summary 直接给答案。"
        "当用户在做旅行规划但信息缺失时：status=clarification，plan_state=clarification，"
        "trip_summary 用中文说明目前已知条件和下一步需要补充什么，clarification_questions 返回结构化问题数组。"
        "当用户已提供足够旅行信息时：status=success，plan_state=draft 或 final，"
        "尽量返回中文的路线摘要、逐日安排、预算、交通和替代路线。"
        "daily_itinerary 必须是数组，元素包含 day、theme、activities 或 morning/afternoon/evening/dining。"
        "budget_breakdown 中的金额字段必须是数字，货币默认 CNY。"
        "transportation 必须是数组，每项包含 mode 和 recommendation。"
        "recommendations 必须是数组，每项包含 title 和 description。"
        "warnings 必须是数组，每项包含 severity 和 message。"
        "clarification_questions 必须是数组，每项包含 id、field、prompt，必要时可加 reason。"
    )

    def __init__(self, config: QwenConfig) -> None:
        self.config = config

    def _build_chat_llm(self, *, streaming: bool = False):
        return ChatOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            model=self.config.model,
            temperature=self.config.temperature,
            timeout=self.config.timeout_seconds,
            streaming=streaming,
            extra_body={"enable_thinking": self.config.enable_thinking},
        )

    def generate_assistant_reply(
        self,
        *,
        conversation_messages: list[dict[str, Any]],
        latest_user_message: str,
        knowledge_context: list[dict[str, str]] | None = None,
    ) -> str:
        if not self.config.api_key or ChatOpenAI is None:
            return self._fallback_assistant_reply(latest_user_message)

        messages = [{"role": "system", "content": self.ASSISTANT_SYSTEM_PROMPT}]
        if knowledge_context:
            messages.append(
                {
                    "role": "system",
                    "content": self._build_knowledge_context_prompt(knowledge_context),
                }
            )
        for item in conversation_messages[-8:]:
            role = item.get("role")
            content = item.get("content", "")
            if role in {"user", "assistant", "system"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": latest_user_message})

        llm = self._build_chat_llm(streaming=False)
        try:
            response = llm.invoke(messages)
            content = getattr(response, "content", "")
            if isinstance(content, list):
                content = "".join(
                    item.get("text", "") for item in content if isinstance(item, dict)
                )
            return str(content).strip() or self._fallback_assistant_reply(
                latest_user_message
            )
        except Exception:
            return self._fallback_assistant_reply(latest_user_message)

    def stream_assistant_reply(
        self,
        *,
        conversation_messages: list[dict[str, Any]],
        latest_user_message: str,
        knowledge_context: list[dict[str, str]] | None = None,
    ):
        if not self.config.api_key or ChatOpenAI is None:
            yield from self._stream_fallback_text(
                self._fallback_assistant_reply(latest_user_message)
            )
            return

        messages = [{"role": "system", "content": self.ASSISTANT_SYSTEM_PROMPT}]
        if knowledge_context:
            messages.append(
                {
                    "role": "system",
                    "content": self._build_knowledge_context_prompt(knowledge_context),
                }
            )
        for item in conversation_messages[-8:]:
            role = item.get("role")
            content = item.get("content", "")
            if role in {"user", "assistant", "system"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": latest_user_message})

        llm = self._build_chat_llm(streaming=True)
        emitted = False
        try:
            for chunk in llm.stream(messages):
                content = getattr(chunk, "content", "")
                if isinstance(content, list):
                    content = "".join(
                        item.get("text", "") for item in content if isinstance(item, dict)
                    )
                text = str(content or "")
                if not text:
                    continue
                emitted = True
                for segment in self._split_stream_segments(text):
                    yield segment
            if not emitted:
                yield from self._stream_fallback_text(
                    self._fallback_assistant_reply(latest_user_message)
                )
        except Exception:
            yield from self._stream_fallback_text(
                self._fallback_assistant_reply(latest_user_message)
            )

    def chat_completions_url(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/chat/completions"

    def _stream_fallback_text(self, text: str):
        for chunk in self._split_text(text):
            yield chunk
            time.sleep(0.04)

    @classmethod
    def _split_stream_segments(cls, text: str):
        if len(text) <= 18:
            yield text
            return
        for chunk in cls._split_text(text):
            yield chunk

    @staticmethod
    def _split_text(text: str) -> list[str]:
        if not text:
            return []
        chunks: list[str] = []
        current = ""
        delimiters = "。！？!?；;\n"
        for char in text:
            current += char
            if char in delimiters or len(current) >= 22:
                chunks.append(current)
                current = ""
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _build_knowledge_context_prompt(knowledge_context: list[dict[str, str]]) -> str:
        if not knowledge_context:
            return ""
        blocks = []
        for index, item in enumerate(knowledge_context, start=1):
            title = item.get("title") or f"文档 {index}"
            heading = item.get("heading_path") or "正文"
            content = item.get("content") or ""
            blocks.append(f"[{index}] {title} / {heading}\n{content}")
        return (
            "以下是与当前问题相关的知识库上下文。"
            "如果这些内容足以回答问题，请优先依据它们作答；"
            "如果不足，可以结合通用知识补充，但不要声明引用来源。\n\n"
            + "\n\n".join(blocks)
        )

    def build_planning_payload(
        self,
        *,
        request: TripPlanningRequest,
        attractions: list[POICandidate],
        foods: list[FoodCandidate],
        hotels: list[HotelCandidate],
        assumptions: list[str],
        degraded: bool,
        confirmed_constraints: ConfirmedConstraints | None = None,
        conversation_summary: str | None = None,
        previous_result: TripPlanOutput | None = None,
        latest_user_message: str | None = None,
        assistant_mode: str = "travel",
        suggested_clarification_questions: list[ClarificationQuestion] | None = None,
    ) -> dict[str, Any]:
        return {
            "request": request.model_dump(mode="json"),
            "attractions": [
                self._serialize_attraction(item) for item in attractions[:6]
            ],
            "foods": [self._serialize_food(item) for item in foods[:6]],
            "hotels": [self._serialize_hotel(item) for item in hotels[:4]],
            "assumptions": assumptions,
            "degraded": degraded,
            "confirmed_constraints": confirmed_constraints.model_dump(mode="json")
            if confirmed_constraints is not None
            else {},
            "conversation_summary": conversation_summary or "",
            "latest_user_message": latest_user_message or "",
            "assistant_mode": assistant_mode,
            "suggested_clarification_questions": [
                item.model_dump(mode="json")
                for item in (suggested_clarification_questions or [])
            ],
            "previous_result": {
                "trip_summary": previous_result.trip_summary,
                "route_stops": [item.name for item in previous_result.route_stops[:8]],
                "plan_state": previous_result.plan_state,
            }
            if previous_result is not None
            else None,
        }

    def build_chat_messages(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"规划上下文如下：\n{json.dumps(payload, ensure_ascii=False)}",
            },
        ]

    def build_chat_request_body(
        self,
        *,
        request: TripPlanningRequest,
        attractions: list[POICandidate],
        foods: list[FoodCandidate],
        hotels: list[HotelCandidate],
        assumptions: list[str],
        degraded: bool,
        confirmed_constraints: ConfirmedConstraints | None = None,
        conversation_summary: str | None = None,
        previous_result: TripPlanOutput | None = None,
        latest_user_message: str | None = None,
        assistant_mode: str = "travel",
        suggested_clarification_questions: list[ClarificationQuestion] | None = None,
    ) -> dict[str, Any]:
        payload = self.build_planning_payload(
            request=request,
            attractions=attractions,
            foods=foods,
            hotels=hotels,
            assumptions=assumptions,
            degraded=degraded,
            confirmed_constraints=confirmed_constraints,
            conversation_summary=conversation_summary,
            previous_result=previous_result,
            latest_user_message=latest_user_message,
            assistant_mode=assistant_mode,
            suggested_clarification_questions=suggested_clarification_questions,
        )
        return {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "messages": self.build_chat_messages(payload),
        }

    def generate_trip_plan(
        self,
        *,
        request: TripPlanningRequest,
        attractions: list[POICandidate],
        foods: list[FoodCandidate],
        hotels: list[HotelCandidate],
        assumptions: list[str],
        source_references: list[SourceReference],
        degraded: bool,
        confirmed_constraints: ConfirmedConstraints | None = None,
        conversation_summary: str | None = None,
        previous_result: TripPlanOutput | None = None,
        latest_user_message: str | None = None,
        assistant_mode: str = "travel",
        suggested_clarification_questions: list[ClarificationQuestion] | None = None,
    ) -> TripPlanOutput:
        payload = self.build_planning_payload(
            request=request,
            attractions=attractions,
            foods=foods,
            hotels=hotels,
            assumptions=assumptions,
            degraded=degraded,
            confirmed_constraints=confirmed_constraints,
            conversation_summary=conversation_summary,
            previous_result=previous_result,
            latest_user_message=latest_user_message,
            assistant_mode=assistant_mode,
            suggested_clarification_questions=suggested_clarification_questions,
        )

        if not self.config.api_key:
            logger.warning(
                "Qwen planning degraded: reason=missing_api_key destination=%s days=%s assistant_mode=%s",
                request.destination,
                request.days,
                assistant_mode,
            )
            return self._fallback_plan(
                request=request,
                attractions=attractions,
                foods=foods,
                hotels=hotels,
                assumptions=assumptions
                + ["未配置 DASHSCOPE_API_KEY，当前使用本地回退回复逻辑。"],
                source_references=source_references,
                degraded=True,
                confirmed_constraints=confirmed_constraints,
                conversation_summary=conversation_summary,
                latest_user_message=latest_user_message,
                assistant_mode=assistant_mode,
                suggested_clarification_questions=suggested_clarification_questions,
            )

        if ChatPromptTemplate is None or ChatOpenAI is None:
            logger.warning(
                "Qwen planning degraded: reason=langchain_dependency_unavailable destination=%s days=%s assistant_mode=%s",
                request.destination,
                request.days,
                assistant_mode,
            )
            return self._fallback_plan(
                request=request,
                attractions=attractions,
                foods=foods,
                hotels=hotels,
                assumptions=assumptions
                + ["LangChain 依赖不可用，当前使用本地回退回复逻辑。"],
                source_references=source_references,
                degraded=True,
                confirmed_constraints=confirmed_constraints,
                conversation_summary=conversation_summary,
                latest_user_message=latest_user_message,
                assistant_mode=assistant_mode,
                suggested_clarification_questions=suggested_clarification_questions,
            )

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self.SYSTEM_PROMPT),
                ("human", "规划上下文如下：\n{payload}"),
            ]
        )
        llm = ChatOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            model=self.config.model,
            temperature=self.config.temperature,
            timeout=self.config.timeout_seconds,
            extra_body={"enable_thinking": self.config.enable_thinking},
        )
        try:
            message = (prompt | llm).invoke(
                {"payload": json.dumps(payload, ensure_ascii=False)}
            )
            content = getattr(message, "content", "")
            parsed = self._safe_load_json(content)
            if not parsed:
                preview = str(content).replace("\n", " ")[:300]
                logger.warning(
                    "Qwen planning response parse returned empty JSON: destination=%s assistant_mode=%s content_preview=%s",
                    request.destination,
                    assistant_mode,
                    preview,
                )
            return self._from_llm_json(
                request=request,
                raw=parsed,
                attractions=attractions,
                foods=foods,
                hotels=hotels,
                assumptions=assumptions,
                source_references=source_references,
                degraded=degraded,
                confirmed_constraints=confirmed_constraints,
                conversation_summary=conversation_summary,
                assistant_mode=assistant_mode,
                suggested_clarification_questions=suggested_clarification_questions,
            )
        except Exception as exc:
            logger.warning(
                "Qwen planning degraded: reason=model_request_failed error_type=%s destination=%s days=%s assistant_mode=%s",
                type(exc).__name__,
                request.destination,
                request.days,
                assistant_mode,
            )
            return self._fallback_plan(
                request=request,
                attractions=attractions,
                foods=foods,
                hotels=hotels,
                assumptions=assumptions
                + [
                    f"模型请求失败（{type(exc).__name__}），当前使用本地回退回复逻辑。"
                ],
                source_references=source_references,
                degraded=True,
                confirmed_constraints=confirmed_constraints,
                conversation_summary=conversation_summary,
                latest_user_message=latest_user_message,
                assistant_mode=assistant_mode,
                suggested_clarification_questions=suggested_clarification_questions,
            )

    def _from_llm_json(
        self,
        *,
        request: TripPlanningRequest,
        raw: dict[str, Any],
        attractions: list[POICandidate],
        foods: list[FoodCandidate],
        hotels: list[HotelCandidate],
        assumptions: list[str],
        source_references: list[SourceReference],
        degraded: bool,
        confirmed_constraints: ConfirmedConstraints | None = None,
        conversation_summary: str | None = None,
        assistant_mode: str = "travel",
        suggested_clarification_questions: list[ClarificationQuestion] | None = None,
    ) -> TripPlanOutput:
        itinerary = self._normalize_itinerary(raw.get("daily_itinerary", []))
        raw_status = str(raw.get("status") or "").strip().lower()
        status = self._normalize_status(raw.get("status"), degraded)
        plan_state = self._normalize_plan_state(raw.get("plan_state"), status, assistant_mode)
        if raw_status in {"degraded", "partial"} or (degraded and status == "success"):
            if raw_status in {"degraded", "partial"}:
                degradation_reason = "llm_marked_degraded"
            elif degraded:
                degradation_reason = "upstream_provider_degraded"
            else:
                degradation_reason = "status_normalization_defaulted_to_degraded"
            logger.warning(
                "Qwen planning output succeeded with fallback context: reason=%s raw_status=%s destination=%s assistant_mode=%s warnings=%s assumptions=%s",
                degradation_reason,
                raw_status or "<empty>",
                request.destination,
                assistant_mode,
                len(raw.get("warnings", []) or []),
                len(assumptions),
            )
        return TripPlanOutput(
            status=status,
            plan_state=plan_state,
            assistant_mode=assistant_mode,
            trip_summary=self._normalize_trip_summary(
                raw.get("trip_summary"),
                fallback=(
                    f"{request.destination} {request.days} 天旅行建议已生成。"
                    if assistant_mode == "travel"
                    else "我已经根据你的问题给出中文回复，如果你愿意，我也可以继续帮你规划旅行。"
                ),
            ),
            conversation_summary=conversation_summary or "",
            confirmed_constraints=confirmed_constraints or ConfirmedConstraints.from_request(request),
            route_overview=self._normalize_route_overview(raw.get("route_overview")),
            alternatives=self._normalize_alternatives(raw.get("alternatives")),
            assumptions=assumptions,
            daily_itinerary=itinerary
            or (
                self._build_itinerary(request, attractions, foods)
                if assistant_mode == "travel" and status != "clarification"
                else []
            ),
            budget_breakdown=self._normalize_budget_breakdown(
                raw.get("budget_breakdown"), request
            )
            if assistant_mode == "travel"
            else BudgetBreakdown(),
            transportation=self._normalize_transportation(raw.get("transportation"))
            if assistant_mode == "travel"
            else [],
            accommodation=AccommodationRecommendation(
                summary=raw.get(
                    "accommodation_summary",
                    "建议优先住在主要活动片区附近，减少来回折返。",
                ),
                suggested_hotels=hotels[:3] if assistant_mode == "travel" else [],
            ),
            attractions=attractions[:6] if assistant_mode == "travel" else [],
            food_recommendations=foods[:6] if assistant_mode == "travel" else [],
            recommendations=self._normalize_recommendations(raw.get("recommendations")),
            warnings=self._normalize_warnings(raw.get("warnings")),
            source_references=source_references,
            clarification_questions=self._normalize_clarification_questions(
                raw.get("clarification_questions"),
                fallback=suggested_clarification_questions or [],
            ),
        )

    @staticmethod
    def _safe_load_json(content: str) -> dict[str, Any]:
        if not content:
            return {}
        if isinstance(content, list):
            text_chunks = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("text")
            ]
            content = "\n".join(text_chunks)
        if not isinstance(content, str):
            content = str(content)

        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped, count=1)
            stripped = re.sub(r"\s*```$", "", stripped, count=1)
        try:
            loaded = json.loads(stripped)
            return loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            candidate = QwenPlannerClient._extract_json_object(stripped)
            if not candidate:
                return {}
            try:
                loaded = json.loads(candidate)
                return loaded if isinstance(loaded, dict) else {}
            except json.JSONDecodeError:
                return {}

    def _fallback_plan(
        self,
        *,
        request: TripPlanningRequest,
        attractions: list[POICandidate],
        foods: list[FoodCandidate],
        hotels: list[HotelCandidate],
        assumptions: list[str],
        source_references: list[SourceReference],
        degraded: bool,
        confirmed_constraints: ConfirmedConstraints | None = None,
        conversation_summary: str | None = None,
        latest_user_message: str | None = None,
        assistant_mode: str = "travel",
        suggested_clarification_questions: list[ClarificationQuestion] | None = None,
    ) -> TripPlanOutput:
        if assistant_mode == "general":
            answer = (
                f"我已经收到你的问题：{latest_user_message or '本轮输入'}。"
                " 当前无法调用在线模型时，我会先给出简要中文回复。"
                " 如果你想继续，我也可以马上切换到旅行规划模式，帮你设计目的地、预算和路线。"
            )
            return TripPlanOutput(
                status="success",
                plan_state="final",
                assistant_mode="general",
                trip_summary=answer,
                conversation_summary=conversation_summary or "",
                confirmed_constraints=confirmed_constraints
                or ConfirmedConstraints.from_request(request),
                assumptions=assumptions,
                recommendations=[
                    RecommendationItem(
                        title="可以继续问任何问题",
                        description="无论是泛问题还是旅行问题，我都会先用中文直接回复你。",
                    ),
                    RecommendationItem(
                        title="也可以切回旅行规划",
                        description="例如告诉我目的地、天数、预算和偏好，我会继续生成路线方案。",
                    ),
                ],
                warnings=[
                    WarningItem(
                        severity="warning" if degraded else "info",
                        message="当前模型链路不可用，已使用本地回退回复。",
                    )
                ],
                source_references=source_references,
            )

        clarification_questions = suggested_clarification_questions or []
        if clarification_questions:
            clarification_text = "；".join(
                question.prompt for question in clarification_questions[:3]
            )
            return TripPlanOutput(
                status="clarification",
                plan_state="clarification",
                assistant_mode="travel",
                trip_summary=(
                    "我已经理解了你当前的出行意图，但还缺少几个关键信息。"
                    f" 请继续补充：{clarification_text}"
                ),
                conversation_summary=conversation_summary or "",
                confirmed_constraints=confirmed_constraints
                or ConfirmedConstraints.from_request(request),
                assumptions=assumptions,
                clarification_questions=clarification_questions,
                recommendations=[
                    RecommendationItem(
                        title="补充关键信息",
                        description="补上目的地、天数、预算或必去点位后，我就能继续细化路线。",
                    )
                ],
                warnings=[
                    WarningItem(
                        severity="info",
                        message="当前模型链路不可用，已使用本地澄清策略继续对话。",
                    )
                ],
                source_references=source_references,
            )

        return TripPlanOutput(
            status="success",
            plan_state="draft",
            assistant_mode="travel",
            trip_summary=(
                f"已根据当前条件生成 {request.destination} {request.days} 天旅行建议，"
                "本轮结果来自实时候选数据与本地回退规划逻辑。"
            ),
            conversation_summary=conversation_summary or "",
            confirmed_constraints=confirmed_constraints or ConfirmedConstraints.from_request(request),
            route_overview=RouteOverview(
                headline=f"{request.destination} {request.days} 天路线草案",
                strategy="优先围绕同片区候选点位组织顺路路线，减少来回折返。",
                pace=confirmed_constraints.pace_preference if confirmed_constraints else None,
                total_stops=min(6, len(attractions) + len(foods)),
            ),
            assumptions=assumptions,
            daily_itinerary=self._build_itinerary(request, attractions, foods),
            budget_breakdown=self._default_budget(request),
            transportation=[
                TransportOption(
                    mode="metro + ride-hailing",
                    recommendation=(
                        "建议每一天尽量围绕一个片区展开，优先地铁，夜间或跨区回程再补充打车。"
                    ),
                )
            ],
            accommodation=AccommodationRecommendation(
                summary=(
                    "优先选择靠近核心景点聚集区的住宿，以减少换乘与折返时间。"
                ),
                suggested_hotels=hotels[:3],
            ),
            attractions=attractions[:6],
            food_recommendations=foods[:6],
            recommendations=[
                RecommendationItem(
                    title="关键门票尽早锁定",
                    description="确认日期后尽量优先预订热门博物馆、展览或观景点。",
                ),
                RecommendationItem(
                    title="预留一个机动夜晚",
                    description="把最后一个晚上留给天气变化、补漏或临时加点位更稳妥。",
                ),
            ],
            alternatives=[
                AlternativeRoute(
                    title="低折返替代路线",
                    summary="减少跨区移动，更适合偏松弛的节奏。",
                    stop_names=[item.name for item in attractions[3:6]],
                    differences=["减少热门景点密度", "优先保留步行友好的片区"],
                )
            ]
            if attractions
            else [],
            warnings=[
                WarningItem(
                    severity="warning" if degraded else "info",
                    message="部分模块在实时数据不可用时会回退到本地规划结果，关键数据建议二次确认。",
                )
            ],
            source_references=source_references,
            clarification_questions=clarification_questions,
        )

    def _fallback_assistant_reply(self, latest_user_message: str) -> str:
        question = latest_user_message.strip()
        if not question:
            return "可以直接告诉我你想讨论的问题，我会先给你一个清晰的中文回答。"
        return (
            "我先按智能助手的方式回答你："
            f"{question}"
            "。如果你想把它转成正式的旅行方案，请去流程工作台填写结构化条件。"
        )

    @staticmethod
    def _build_itinerary(
        request: TripPlanningRequest,
        attractions: list[POICandidate],
        foods: list[FoodCandidate],
    ) -> list[DailyPlan]:
        itinerary: list[DailyPlan] = []
        for day in range(1, request.days + 1):
            attraction = attractions[(day - 1) % len(attractions)] if attractions else None
            food = foods[(day - 1) % len(foods)] if foods else None
            itinerary.append(
                DailyPlan(
                    day=day,
                    theme=f"Day {day} exploration",
                    morning=[attraction.name] if attraction else ["Flexible sightseeing"],
                    afternoon=["Neighborhood walk", attraction.address] if attraction and attraction.address else ["Explore the destination core"],
                    evening=[food.name] if food else ["Flexible dining block"],
                    dining=[food.name] if food else ["Review live dining options on the day"],
                )
            )
        return itinerary

    @staticmethod
    def _default_budget(request: TripPlanningRequest) -> BudgetBreakdown:
        total = request.budget or max(request.days * 800, 1500)
        accommodation = round(total * 0.4, 2)
        transportation = round(total * 0.15, 2)
        food = round(total * 0.25, 2)
        activities = round(total - accommodation - transportation - food, 2)
        return BudgetBreakdown(
            estimated_total=total,
            accommodation=accommodation,
            transportation=transportation,
            food=food,
            activities=activities,
            note="预算拆分来自请求级启发式估算，请在预订前再次核算。",
        )

    @staticmethod
    def _serialize_attraction(item: POICandidate) -> dict[str, Any]:
        return {
            "name": item.name,
            "district": item.district,
            "address": item.address,
            "category": item.category,
            "location": item.location,
        }

    @staticmethod
    def _serialize_food(item: FoodCandidate) -> dict[str, Any]:
        return {
            "name": item.name,
            "address": item.address,
            "location": item.location,
            "cuisine": item.cuisine,
            "average_cost": item.average_cost,
            "rating": item.rating,
        }

    @staticmethod
    def _serialize_hotel(item: HotelCandidate) -> dict[str, Any]:
        return {
            "name": item.name,
            "address": item.address,
            "location": item.location,
            "price_min": item.price_min,
            "price_max": item.price_max,
            "rating": item.rating,
        }

    @staticmethod
    def _normalize_itinerary(items: Any) -> list[DailyPlan]:
        if not isinstance(items, list):
            return []

        normalized: list[DailyPlan] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            if any(key in item for key in ("morning", "afternoon", "evening", "dining")):
                normalized.append(
                    DailyPlan(
                        day=QwenPlannerClient._normalize_day_number(
                            item.get("day"), index + 1
                        ),
                        theme=item.get("theme")
                        or item.get("focus")
                        or f"Day {index + 1}",
                        morning=QwenPlannerClient._normalize_plan_entries(
                            item.get("morning")
                        ),
                        afternoon=QwenPlannerClient._normalize_plan_entries(
                            item.get("afternoon")
                        ),
                        evening=QwenPlannerClient._normalize_plan_entries(
                            item.get("evening")
                        ),
                        dining=QwenPlannerClient._normalize_plan_entries(
                            item.get("dining")
                        ),
                    )
                )
                continue

            activities = item.get("activities")
            if isinstance(activities, list):
                morning: list[str] = []
                afternoon: list[str] = []
                evening: list[str] = []
                dining: list[str] = []
                ordered_labels: list[str] = []
                for activity in activities:
                    if not isinstance(activity, dict):
                        continue
                    label = QwenPlannerClient._format_activity_label(activity)
                    if not label:
                        continue
                    ordered_labels.append(label)
                    time_range = str(activity.get("time", ""))
                    bucket = QwenPlannerClient._bucket_activity(time_range, label)
                    if bucket == "morning":
                        morning.append(label)
                    elif bucket == "afternoon":
                        afternoon.append(label)
                    elif bucket == "evening":
                        evening.append(label)
                    elif bucket == "dining":
                        dining.append(label)
                if not any((morning, afternoon, evening, dining)) and ordered_labels:
                    afternoon = ordered_labels
                normalized.append(
                    DailyPlan(
                        day=QwenPlannerClient._normalize_day_number(
                            item.get("day"), index + 1
                        ),
                        theme=item.get("theme")
                        or item.get("focus")
                        or f"Day {index + 1}",
                        morning=morning,
                        afternoon=afternoon,
                        evening=evening,
                        dining=dining,
                    )
                )
        return normalized

    @staticmethod
    def _normalize_budget_breakdown(raw_budget: Any, request: TripPlanningRequest) -> BudgetBreakdown:
        default = QwenPlannerClient._default_budget(request)
        if not isinstance(raw_budget, dict):
            return default

        def amount(value: Any, *keys: str) -> float | None:
            direct = QwenPlannerClient._extract_number(value)
            if direct is not None:
                return direct
            if isinstance(value, dict):
                for key in (*keys, "amount", "cost", "price", "estimated", "value"):
                    nested = value.get(key)
                    parsed = QwenPlannerClient._extract_number(nested)
                    if parsed is not None:
                        return parsed
            return None

        accommodation = amount(
            raw_budget.get("accommodation"), "estimated_cost", "total_cost"
        )
        transportation = amount(
            raw_budget.get("transportation"), "estimated_cost", "total_cost"
        ) or amount(
            raw_budget.get("transport"), "estimated_cost", "total_cost"
        )
        food = amount(raw_budget.get("food"), "estimated_cost", "total_cost") or amount(
            raw_budget.get("food_and_dining"), "estimated_cost", "total_cost"
        ) or amount(
            raw_budget.get("dining"), "estimated_cost", "total_cost"
        )
        activities = amount(raw_budget.get("attractions"), "estimated_cost", "total_cost") or amount(
            raw_budget.get("activities"), "estimated_cost", "total_cost"
        ) or amount(
            raw_budget.get("tickets_and_entertainment"), "estimated_cost", "total_cost"
        )
        contingency = amount(raw_budget.get("contingency"), "estimated_cost", "total_cost")
        estimated_total = amount(
            raw_budget.get("estimated_total"),
            "estimated_total",
            "total_estimated_cost",
        ) or amount(
            raw_budget.get("total"), "estimated_total", "total_estimated_cost"
        ) or amount(
            raw_budget, "estimated_total", "total_estimated_cost", "total_estimated", "total"
        )
        if estimated_total is None:
            known_amounts = [
                value
                for value in (
                    accommodation,
                    transportation,
                    food,
                    activities,
                    contingency,
                )
                if value is not None
            ]
            if known_amounts:
                estimated_total = round(sum(known_amounts), 2)

        notes: list[str] = []
        for section in (
            raw_budget,
            raw_budget.get("accommodation"),
            raw_budget.get("transportation"),
            raw_budget.get("transport"),
            raw_budget.get("food"),
            raw_budget.get("food_and_dining"),
            raw_budget.get("dining"),
            raw_budget.get("attractions"),
            raw_budget.get("activities"),
            raw_budget.get("tickets_and_entertainment"),
            raw_budget.get("miscellaneous"),
            raw_budget.get("contingency"),
        ):
            if isinstance(section, dict):
                for key in ("note", "notes", "details", "description"):
                    text = QwenPlannerClient._coerce_text(section.get(key))
                    if text:
                        notes.append(text)
        if contingency is not None:
            notes.append(f"Contingency reserve included: {contingency:.0f} CNY.")

        return BudgetBreakdown(
            currency=raw_budget.get("currency", default.currency),
            estimated_total=estimated_total or default.estimated_total,
            accommodation=accommodation or default.accommodation,
            transportation=transportation or default.transportation,
            food=food or default.food,
            activities=activities or default.activities,
            note=" ".join(notes) or raw_budget.get("note") or default.note,
        )

    @staticmethod
    def _normalize_transportation(raw_transportation: Any) -> list[TransportOption]:
        if isinstance(raw_transportation, list):
            options = [
                QwenPlannerClient._build_transport_option(item)
                for item in raw_transportation
                if isinstance(item, dict)
            ]
            options = [item for item in options if item is not None]
            if options:
                return options
        elif isinstance(raw_transportation, dict):
            option = QwenPlannerClient._build_transport_option(raw_transportation)
            if option is not None:
                return [option]
        elif isinstance(raw_transportation, str) and raw_transportation.strip():
            return [
                TransportOption(
                    mode="城市交通",
                    recommendation=raw_transportation.strip(),
                )
            ]

        return [
            TransportOption(
                mode="城市交通",
                recommendation="建议优先地铁与打车结合，以便灵活覆盖核心片区。",
            )
        ]

    @staticmethod
    def _normalize_recommendations(raw_recommendations: Any) -> list[RecommendationItem]:
        if not isinstance(raw_recommendations, list):
            return []
        items: list[RecommendationItem] = []
        for item in raw_recommendations:
            if isinstance(item, dict):
                title = QwenPlannerClient._coerce_text(
                    item.get("title") or item.get("item") or item.get("category")
                )
                description = QwenPlannerClient._coerce_text(
                    item.get("description") or item.get("reason") or item.get("details")
                )
                items.append(
                    RecommendationItem(
                        title=title or "建议",
                        description=description or "",
                    )
                )
            elif isinstance(item, str):
                items.append(
                    RecommendationItem(title="建议", description=item)
                )
        return items

    @staticmethod
    def _normalize_trip_summary(raw_summary: Any, fallback: str) -> str:
        if isinstance(raw_summary, str):
            return raw_summary
        if isinstance(raw_summary, dict):
            overview = QwenPlannerClient._coerce_text(raw_summary.get("overview"))
            theme = QwenPlannerClient._coerce_text(raw_summary.get("theme"))
            destination = QwenPlannerClient._coerce_text(raw_summary.get("destination"))
            duration = QwenPlannerClient._coerce_text(
                raw_summary.get("duration_days") or raw_summary.get("days")
            )
            parts = [
                part
                for part in (
                    f"{destination} {duration} 天行程" if destination and duration else None,
                    theme,
                    overview,
                )
                if part
            ]
            if parts:
                return "｜".join(str(part) for part in parts)
        return fallback

    @staticmethod
    def _normalize_warnings(raw_warnings: Any) -> list[WarningItem]:
        if not isinstance(raw_warnings, list):
            return []
        items: list[WarningItem] = []
        for item in raw_warnings:
            if isinstance(item, dict):
                message = QwenPlannerClient._coerce_text(
                    item.get("message") or item.get("reason") or item.get("details")
                )
                items.append(
                    WarningItem(
                        severity=QwenPlannerClient._normalize_warning_severity(
                            item.get("severity")
                        ),
                        message=message or "",
                    )
                )
            elif isinstance(item, str):
                items.append(WarningItem(severity="warning", message=item))
        return items

    @staticmethod
    def _to_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        return [str(value)] if str(value).strip() else []

    @staticmethod
    def _normalize_plan_entries(value: Any) -> list[str]:
        if isinstance(value, list):
            entries: list[str] = []
            for item in value:
                if isinstance(item, dict):
                    text = QwenPlannerClient._format_activity_label(item)
                else:
                    text = QwenPlannerClient._coerce_text(item)
                if text:
                    entries.append(text)
            return entries
        text = QwenPlannerClient._coerce_text(value)
        return [text] if text else []

    @staticmethod
    def _normalize_route_overview(raw_route_overview: Any) -> RouteOverview | None:
        if isinstance(raw_route_overview, dict):
            headline = QwenPlannerClient._coerce_text(
                raw_route_overview.get("headline")
                or raw_route_overview.get("summary")
                or raw_route_overview.get("title")
            )
            strategy = QwenPlannerClient._coerce_text(
                raw_route_overview.get("strategy")
                or raw_route_overview.get("routing_strategy")
                or raw_route_overview.get("description")
            )
            if headline or strategy:
                return RouteOverview(
                    headline=headline or "路线摘要",
                    strategy=strategy or "建议围绕主要活动片区组织路线。",
                    pace=QwenPlannerClient._coerce_text(raw_route_overview.get("pace")),
                    total_stops=int(raw_route_overview.get("total_stops") or 0),
                )
        elif isinstance(raw_route_overview, str) and raw_route_overview.strip():
            return RouteOverview(
                headline="路线摘要",
                strategy=raw_route_overview.strip(),
                total_stops=0,
            )
        return None

    @staticmethod
    def _normalize_alternatives(raw_alternatives: Any) -> list[AlternativeRoute]:
        if not isinstance(raw_alternatives, list):
            return []
        alternatives: list[AlternativeRoute] = []
        for item in raw_alternatives:
            if isinstance(item, dict):
                title = QwenPlannerClient._coerce_text(
                    item.get("title") or item.get("name")
                )
                summary = QwenPlannerClient._coerce_text(
                    item.get("summary")
                    or item.get("description")
                    or item.get("difference")
                )
                stop_names = QwenPlannerClient._normalize_routes(
                    item.get("stop_names") or item.get("stops")
                )
                differences = QwenPlannerClient._normalize_routes(
                    item.get("differences") or item.get("highlights")
                )
                if title or summary:
                    alternatives.append(
                        AlternativeRoute(
                            title=title or "替代路线",
                            summary=summary or "",
                            stop_names=stop_names,
                            differences=differences,
                        )
                    )
            elif isinstance(item, str):
                alternatives.append(
                    AlternativeRoute(title="替代路线", summary=item)
                )
        return alternatives

    @staticmethod
    def _normalize_status(raw_status: Any, degraded: bool) -> str:
        normalized = str(raw_status or "").strip().lower()
        if normalized in {"clarification", "clarify", "need_info"}:
            return "clarification"
        return "success"

    @staticmethod
    def _normalize_plan_state(raw_plan_state: Any, status: str, assistant_mode: str) -> str:
        normalized = str(raw_plan_state or "").strip().lower()
        if normalized in {"clarification", "clarify"} or status == "clarification":
            return "clarification"
        if assistant_mode == "general":
            return "final"
        if normalized in {"final", "done"}:
            return "final"
        return "draft"

    @staticmethod
    def _normalize_clarification_questions(
        raw_questions: Any,
        *,
        fallback: list[ClarificationQuestion],
    ) -> list[ClarificationQuestion]:
        if isinstance(raw_questions, list):
            questions: list[ClarificationQuestion] = []
            for index, item in enumerate(raw_questions):
                if isinstance(item, dict):
                    prompt = QwenPlannerClient._coerce_text(
                        item.get("prompt") or item.get("question") or item.get("content")
                    )
                    field = QwenPlannerClient._coerce_text(item.get("field")) or "unknown"
                    if prompt:
                        questions.append(
                            ClarificationQuestion(
                                id=QwenPlannerClient._coerce_text(item.get("id"))
                                or f"question-{index + 1}",
                                field=field,
                                prompt=prompt,
                                reason=QwenPlannerClient._coerce_text(item.get("reason")),
                                required=bool(item.get("required", True)),
                            )
                        )
                elif isinstance(item, str) and item.strip():
                    questions.append(
                        ClarificationQuestion(
                            id=f"question-{index + 1}",
                            field="unknown",
                            prompt=item.strip(),
                        )
                    )
            if questions:
                return questions
        return fallback

    @staticmethod
    def _bucket_activity(time_range: str, label: str) -> str:
        lower_label = label.lower()
        lower_time = time_range.lower()
        meal_tokens = (
            "lunch",
            "dinner",
            "breakfast",
            "brunch",
            "supper",
            "早餐",
            "早饭",
            "午餐",
            "午饭",
            "晚餐",
            "晚饭",
            "夜宵",
        )
        if any(token in lower_label or token in lower_time for token in meal_tokens):
            return "dining"
        if any(token in time_range for token in ("清晨", "早上", "上午")):
            return "morning"
        if any(token in time_range for token in ("中午", "午后", "下午")):
            return "afternoon"
        if any(token in time_range for token in ("傍晚", "晚上", "夜间")):
            return "evening"
        hour = QwenPlannerClient._extract_hour(time_range)
        if hour is None:
            return "afternoon"
        if hour < 12:
            return "morning"
        if hour < 18:
            return "afternoon"
        return "evening"

    @staticmethod
    def _extract_hour(time_range: str) -> int | None:
        match = re.match(r"^\s*(\d{1,2})", time_range)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _normalize_day_number(value: Any, default: int) -> int:
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str):
            match = re.search(r"(\d+)", value)
            if match:
                return int(match.group(1))
        return default

    @staticmethod
    def _format_activity_label(activity: dict[str, Any]) -> str | None:
        primary = QwenPlannerClient._coerce_text(
            activity.get("activity") or activity.get("title") or activity.get("name")
        )
        location = QwenPlannerClient._coerce_text(
            activity.get("location") or activity.get("place")
        )
        description = QwenPlannerClient._coerce_text(
            activity.get("description") or activity.get("details")
        )

        if primary and description and description not in primary:
            return f"{primary}: {description}"
        if primary:
            return primary
        if location and description:
            return f"{location}: {description}"
        return location or description

    @staticmethod
    def _coerce_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            parts = [QwenPlannerClient._coerce_text(item) for item in value]
            filtered = [part for part in parts if part]
            return "；".join(filtered) if filtered else None
        return None

    @staticmethod
    def _extract_number(value: Any) -> float | None:
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if not isinstance(value, str):
            return None

        text = value.replace(",", "").strip()
        matches = re.findall(r"\d+(?:\.\d+)?", text)
        if not matches:
            return None
        numbers = [float(item) for item in matches]
        if len(numbers) >= 2 and any(token in text for token in ("-", "~", "至", "到")):
            return round((numbers[0] + numbers[1]) / 2, 2)
        return numbers[0]

    @staticmethod
    def _build_transport_option(item: dict[str, Any]) -> TransportOption | None:
        mode = QwenPlannerClient._coerce_text(
            item.get("primary_mode") or item.get("mode") or item.get("transport")
        )
        strategy = QwenPlannerClient._coerce_text(
            item.get("strategy")
            or item.get("details")
            or item.get("recommendation")
            or item.get("notes")
        )
        routes = QwenPlannerClient._normalize_routes(
            item.get("key_routes") or item.get("routes")
        )
        tips = QwenPlannerClient._coerce_text(item.get("tips"))

        recommendation_parts = [part for part in (strategy, tips) if part]
        if routes:
            recommendation_parts.append(f"关键路段：{'；'.join(routes)}")

        if not mode and not recommendation_parts:
            return None
        return TransportOption(
            mode=mode or "城市交通",
            recommendation=" ".join(recommendation_parts)
            or "建议优先地铁与打车结合，以便灵活覆盖核心片区。",
        )

    @staticmethod
    def _normalize_routes(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            routes: list[str] = []
            for item in value:
                if isinstance(item, dict):
                    start = QwenPlannerClient._coerce_text(
                        item.get("from") or item.get("start")
                    )
                    end = QwenPlannerClient._coerce_text(
                        item.get("to") or item.get("end")
                    )
                    text = (
                        f"{start} -> {end}" if start and end else QwenPlannerClient._coerce_text(item.get("route"))
                    )
                else:
                    text = QwenPlannerClient._coerce_text(item)
                if text:
                    routes.append(text)
            return routes
        text = QwenPlannerClient._coerce_text(value)
        return [text] if text else []

    @staticmethod
    def _extract_json_object(content: str) -> str | None:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return content[start : end + 1]

    @staticmethod
    def _normalize_warning_severity(value: Any) -> str:
        normalized = str(value or "info").strip().lower()
        if normalized in {"critical", "high", "severe", "error"}:
            return "critical"
        if normalized in {"warning", "warn", "medium", "moderate"}:
            return "warning"
        return "info"
