from __future__ import annotations

import re
from typing import Iterable
from uuid import uuid4

from planner.domain.schemas import (
    ChatMessage,
    ChatSession,
    ChatTurnCreateRequest,
    ClarificationQuestion,
    ConfirmedConstraints,
    PlanningContext,
    RevisionNote,
    TripPlanningRequest,
)


TRANSPORT_KEYWORDS = {
    "地铁": "地铁",
    "公交": "公交",
    "打车": "打车",
    "出租": "打车",
    "步行": "步行",
    "walk": "步行",
    "骑行": "骑行",
    "自驾": "自驾",
    "driving": "自驾",
}

PACE_KEYWORDS = {
    "不要太赶": "relaxed",
    "轻松": "relaxed",
    "慢慢": "relaxed",
    "松弛": "relaxed",
    "citywalk": "walkable",
    "city walk": "walkable",
    "暴走": "packed",
    "紧凑": "packed",
}

INTEREST_KEYWORDS = {
    "博物馆": "博物馆",
    "美术馆": "美术馆",
    "展览": "展览",
    "地标": "地标",
    "江景": "江景",
    "夜景": "夜景",
    "咖啡": "咖啡馆",
    "本帮菜": "本帮菜",
    "公园": "公园",
    "步行街": "步行街",
    "滨江": "滨江",
    "古镇": "古镇",
    "历史街区": "历史街区",
}

POI_KEYWORDS = [
    "外滩",
    "苏州河",
    "上海博物馆",
    "博物馆",
    "南京东路",
    "南京路",
    "豫园",
    "武康路",
    "新天地",
    "陆家嘴",
    "城隍庙",
    "徐汇滨江",
    "迪士尼",
    "咖啡馆",
    "本帮菜",
    "公园",
    "美术馆",
    "展览",
]

SOFT_INTEREST_POI_KEYWORDS = {
    "博物馆",
    "美术馆",
    "展览",
    "咖啡馆",
    "本帮菜",
    "公园",
}

STOP_SUFFIXES = (
    "路",
    "街",
    "巷",
    "园",
    "馆",
    "塔",
    "寺",
    "桥",
    "湖",
    "山",
    "滩",
    "河",
    "江",
    "站",
    "湾",
    "里",
    "镇",
    "村",
    "广场",
    "中心",
    "码头",
)

FINALIZE_TOKENS = ("就按这个", "就这样", "确认方案", "最终方案", "定下来")
TRAVEL_KEYWORDS = {
    "旅游",
    "旅行",
    "路线",
    "路由",
    "行程",
    "攻略",
    "酒店",
    "民宿",
    "景点",
    "目的地",
    "citywalk",
    "city walk",
    "外滩",
    "博物馆",
    "高铁",
    "机票",
    "地铁",
    "打车",
    "美食",
    "餐厅",
    "航班",
    "签证",
    "出行",
    "自驾",
    "住宿",
    "周末去哪",
}


def build_form_context(request: TripPlanningRequest) -> PlanningContext:
    return PlanningContext(
        mode="form",
        assistant_mode="travel",
        request=request,
        confirmed_constraints=ConfirmedConstraints.from_request(request),
        latest_user_message=render_request_summary(request),
    )


def build_chat_context(
    session: ChatSession,
    turn_input: ChatTurnCreateRequest,
) -> PlanningContext:
    base_constraints = session.confirmed_constraints.model_copy(deep=True)
    revision_notes: list[RevisionNote] = []
    message = turn_input.message or render_request_summary(turn_input.request)

    if turn_input.request is not None:
        merged_constraints, revision = merge_request_into_constraints(
            base_constraints, turn_input.request
        )
        if revision is not None:
            revision_notes.append(revision)
    else:
        merged_constraints, revision_notes = merge_message_into_constraints(
            base_constraints,
            message,
        )

    assistant_mode = infer_assistant_mode(
        message=message,
        constraints=merged_constraints,
        has_previous_result=session.latest_result is not None,
    )
    request = merged_constraints.to_trip_request() or build_partial_request(
        merged_constraints
    )
    return PlanningContext(
        mode="chat",
        assistant_mode=assistant_mode,
        request=request,
        confirmed_constraints=merged_constraints,
        conversation_messages=session.messages,
        latest_user_message=message,
        previous_result=session.latest_result,
        revision_notes=revision_notes,
    )


def build_clarification_questions(
    constraints: ConfirmedConstraints,
    *,
    chat_mode: bool,
    assistant_mode: str = "travel",
) -> list[ClarificationQuestion]:
    if not chat_mode or assistant_mode != "travel":
        return []

    questions: list[ClarificationQuestion] = []
    if not constraints.destination:
        questions.append(
            ClarificationQuestion(
                id="destination",
                field="destination",
                prompt="这次想规划哪个城市或目的地？",
                reason="路线规划需要先确定目的地。",
            )
        )
    if not constraints.days:
        questions.append(
            ClarificationQuestion(
                id="days",
                field="days",
                prompt="预计出行几天？如果是一日路线，也可以直接说 1 天。",
                reason="需要天数来安排路线密度和停靠点数量。",
            )
        )
    if constraints.budget is None:
        questions.append(
            ClarificationQuestion(
                id="budget",
                field="budget",
                prompt="预算大概多少？给个区间也可以，例如 2000-3000 元。",
                reason="预算会影响住宿、餐饮和路线强度建议。",
            )
        )
    if not constraints.must_visit_pois and not constraints.interests:
        questions.append(
            ClarificationQuestion(
                id="anchors",
                field="must_visit_pois",
                prompt="有没有必去点位或偏好主题？例如博物馆、外滩、咖啡馆、亲子景点。",
                reason="需要至少一个路线锚点来组织可执行的动线。",
            )
        )
    return questions


def build_assistant_reply_text(result_status: str, summary: str) -> tuple[str, str]:
    if result_status == "clarification":
        return summary, "clarification"
    return summary, "result"


def build_assistant_message(message: str, turn_id: str, message_type: str) -> ChatMessage:
    return ChatMessage(
        message_id=uuid4().hex,
        role="assistant",
        content=message,
        message_type=message_type,  # type: ignore[arg-type]
        turn_id=turn_id,
    )


def build_user_message(
    *,
    message: str,
    turn_id: str,
) -> ChatMessage:
    return ChatMessage(
        message_id=uuid4().hex,
        role="user",
        content=message,
        message_type="text",
        turn_id=turn_id,
    )


def render_request_summary(request: TripPlanningRequest | None) -> str:
    if request is None:
        return ""
    parts = [
        f"目的地：{request.destination}",
        f"出发城市：{request.departure_city}" if request.departure_city else None,
        f"出发日期：{request.start_date.isoformat()}" if request.start_date else None,
        f"返程日期：{request.end_date.isoformat()}" if request.end_date else None,
        f"天数：{request.days} 天",
        f"人数：{request.travelers_count} 人" if request.travelers_count else None,
        f"预算：{request.budget:.0f} 元" if request.budget is not None else None,
        f"兴趣：{'、'.join(request.interests)}" if request.interests else None,
        f"美食：{'、'.join(request.food_preferences)}"
        if request.food_preferences
        else None,
        f"交通：{'、'.join(request.transport_preferences)}"
        if request.transport_preferences
        else None,
        f"约束：{'、'.join(request.constraints)}" if request.constraints else None,
        f"备注：{request.notes}" if request.notes else None,
    ]
    return "；".join(part for part in parts if part)


def merge_request_into_constraints(
    existing: ConfirmedConstraints,
    request: TripPlanningRequest,
) -> tuple[ConfirmedConstraints, RevisionNote | None]:
    merged = ConfirmedConstraints.from_request(request)
    changes = []
    for field in (
        "destination",
        "city",
        "departure_city",
        "days",
        "budget",
        "start_date",
        "end_date",
        "travelers_count",
        "interests",
        "food_preferences",
        "hotel_preferences",
        "transport_preferences",
        "constraints",
        "notes",
    ):
        value = getattr(merged, field)
        if value not in (None, [], ""):
            changes.append(f"更新 {field}")
    return merged, (
        RevisionNote(summary="已应用结构化表单条件。", changes=changes)
        if changes
        else None
    )


def merge_message_into_constraints(
    existing: ConfirmedConstraints,
    message: str,
) -> tuple[ConfirmedConstraints, list[RevisionNote]]:
    merged = existing.model_copy(deep=True)
    revisions: list[RevisionNote] = []
    changes: list[str] = []

    destination = extract_destination(message)
    if destination and destination != merged.destination:
        merged.destination = destination
        if not merged.city:
            merged.city = destination
        changes.append(f"目的地调整为 {destination}")

    days = extract_days(message)
    if days and days != merged.days:
        merged.days = days
        changes.append(f"天数调整为 {days} 天")

    budget = extract_budget(message)
    if budget is not None and budget != merged.budget:
        merged.budget = budget
        changes.append(f"预算调整为 {int(budget)} 元")

    pace = extract_pace(message)
    if pace and pace != merged.pace_preference:
        merged.pace_preference = pace
        changes.append(f"节奏偏好更新为 {pace}")

    transport_preferences = extract_transport_preferences(message)
    if transport_preferences:
        merged.transport_preferences = dedupe(
            [*transport_preferences, *merged.transport_preferences]
        )
        changes.append(f"交通偏好补充为 {'、'.join(transport_preferences)}")

    interests = extract_interests(message)
    if interests:
        merged.interests = dedupe([*merged.interests, *interests])
        changes.append(f"兴趣主题补充为 {'、'.join(interests)}")

    required_stops = extract_required_stops(message)
    if required_stops:
        merged.must_visit_pois = dedupe([*merged.must_visit_pois, *required_stops])
        changes.append(f"新增点位 {'、'.join(required_stops)}")

    removed_stops = extract_removed_stops(message)
    if removed_stops:
        merged.avoid_pois = dedupe([*merged.avoid_pois, *removed_stops])
        merged.must_visit_pois = [
            item
            for item in merged.must_visit_pois
            if not any(removed in item or item in removed for removed in removed_stops)
        ]
        changes.append(f"移除点位 {'、'.join(removed_stops)}")

    if not merged.notes and message:
        merged.notes = message.strip()

    if changes:
        summary = (
            "检测到用户确认当前方案。"
            if any(token in message for token in FINALIZE_TOKENS)
            else "已合并本轮对话中的已确认条件。"
        )
        revisions.append(RevisionNote(summary=summary, changes=changes))
    return merged, revisions


def infer_assistant_mode(
    *,
    message: str | None,
    constraints: ConfirmedConstraints,
    has_previous_result: bool,
) -> str:
    if has_previous_result:
        return "travel"
    if constraints.destination or constraints.days or constraints.must_visit_pois:
        return "travel"
    text = (message or "").strip().lower()
    if not text:
        return "travel"
    if any(keyword in text or keyword in (message or "") for keyword in TRAVEL_KEYWORDS):
        return "travel"
    return "general"


def build_partial_request(constraints: ConfirmedConstraints) -> TripPlanningRequest:
    destination = constraints.destination or constraints.city or "待确认目的地"
    interests = [*constraints.must_visit_pois, *constraints.interests]
    return TripPlanningRequest(
        destination=destination,
        city=constraints.city or constraints.destination or destination,
        departure_city=constraints.departure_city,
        days=constraints.days or 1,
        budget=constraints.budget,
        start_date=constraints.start_date,
        end_date=constraints.end_date,
        travelers_count=constraints.travelers_count or 1,
        interests=interests,
        food_preferences=constraints.food_preferences,
        hotel_preferences=constraints.hotel_preferences,
        transport_preferences=constraints.transport_preferences,
        constraints=constraints.constraints,
        notes=constraints.notes,
    )


def extract_destination(message: str) -> str | None:
    for pattern in (
        r"(?:去|在|到)([\u4e00-\u9fffA-Za-z]{2,12}?)(?:旅行|旅游|玩|逛|待|边走边逛|$|[，。,\s])",
        r"([\u4e00-\u9fff]{2,8})(?:市)?(?:玩|逛|旅游|旅行)",
    ):
        match = re.search(pattern, message)
        if match:
            return clean_phrase(match.group(1))
    return None


def extract_days(message: str) -> int | None:
    numeric = re.search(r"(\d+)\s*天", message)
    if numeric:
        return int(numeric.group(1))

    chinese = re.search(r"([一二两三四五六七八九十]+)\s*天", message)
    if chinese:
        return parse_chinese_number(chinese.group(1))

    single_day = ("一天", "一日", "当天", "当日")
    if any(token in message for token in single_day):
        return 1
    return None


def extract_budget(message: str) -> float | None:
    direct = re.search(r"预算\s*[:：]?\s*(\d+(?:\.\d+)?)", message)
    if direct:
        return float(direct.group(1))

    ranged = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|到|至|~)\s*(\d+(?:\.\d+)?)\s*元?", message)
    if ranged:
        start = float(ranged.group(1))
        end = float(ranged.group(2))
        return round((start + end) / 2, 2)

    priced = re.search(r"(\d+(?:\.\d+)?)\s*元", message)
    if priced:
        return float(priced.group(1))
    return None


def extract_pace(message: str) -> str | None:
    lowered = message.lower()
    for token, pace in PACE_KEYWORDS.items():
        if token in lowered or token in message:
            return pace
    return None


def extract_transport_preferences(message: str) -> list[str]:
    lowered = message.lower()
    matches = []
    for token, normalized in TRANSPORT_KEYWORDS.items():
        if token in lowered or token in message:
            matches.append(normalized)
    return dedupe(matches)


def extract_interests(message: str) -> list[str]:
    lowered = message.lower()
    matches = []
    for token, normalized in INTEREST_KEYWORDS.items():
        if token in lowered or token in message:
            matches.append(normalized)
    return dedupe(matches)


def extract_required_stops(message: str) -> list[str]:
    stops = list(find_known_poi_tokens(message))
    for pattern in (
        r"(?:想去|想逛|想看|想吃|主要去|必去|换成|改成)([^。；;\n]+)",
        r"(?:路线|动线|安排)([^。；;\n]+)",
    ):
        match = re.search(pattern, message)
        if not match:
            continue
        stops.extend(split_phrases(match.group(1)))
    return dedupe(stop for stop in stops if is_potential_stop_phrase(stop))


def extract_removed_stops(message: str) -> list[str]:
    removed = []
    for pattern in (
        r"(?:不要|别去|不去|去掉)\s*(.+?)(?=(?:换成|改成|想去|想逛|想看|偏爱|喜欢|主要|尽量|希望|安排|路线|动线|，|,|。|；|;|\n|$))",
    ):
        match = re.search(pattern, message)
        if match:
            removed.extend(split_phrases(match.group(1)))
    return dedupe(stop for stop in removed if is_potential_stop_phrase(stop))


def find_known_poi_tokens(message: str) -> Iterable[str]:
    for keyword in POI_KEYWORDS:
        if keyword in SOFT_INTEREST_POI_KEYWORDS:
            continue
        if keyword in message:
            yield keyword


def is_potential_stop_phrase(value: str | None) -> bool:
    phrase = clean_phrase(value)
    if not phrase:
        return False
    if any(token in phrase for token in ("太赶", "轻松", "松弛", "预算", "工作日", "周末")):
        return False
    if any(token in phrase.lower() for token in ("citywalk", "city walk")):
        return False
    if any(keyword in phrase for keyword in POI_KEYWORDS):
        return True
    return any(phrase.endswith(suffix) for suffix in STOP_SUFFIXES)


def split_phrases(value: str) -> list[str]:
    cleaned = value
    for token in ("主要坐", "尽量", "希望", "安排", "路线", "动线", "改成", "换成"):
        cleaned = cleaned.replace(token, " ")
    parts = re.split(r"[、，,和及以及/ ]+", cleaned)
    normalized = [
        clean_phrase(item)
        for item in parts
        if item and clean_phrase(item) and len(clean_phrase(item)) <= 12
    ]
    return [item for item in normalized if item not in {"主要", "不要", "一个"}]


def clean_phrase(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"[：:；;。,.!！?？]", "", value).strip()
    for suffix in ("附近", "一下", "那边", "沿线"):
        if cleaned.endswith(suffix) and len(cleaned) > len(suffix):
            cleaned = cleaned[: -len(suffix)] + ("沿线" if suffix == "沿线" else "")
    return cleaned or None


def parse_chinese_number(text: str) -> int | None:
    mapping = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    if text == "十":
        return 10
    if "十" not in text:
        return mapping.get(text)
    parts = text.split("十")
    if len(parts) != 2:
        return None
    tens = mapping.get(parts[0], 1) if parts[0] else 1
    ones = mapping.get(parts[1], 0) if parts[1] else 0
    return tens * 10 + ones


def dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered
