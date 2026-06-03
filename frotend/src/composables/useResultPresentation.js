import { computed } from "vue";

const statusLabels = {
  success: "已完成",
  degraded: "已完成",
  clarification: "需要补充",
  failed: "失败"
};

const planStateLabels = {
  final: "最终态",
  draft: "草案态",
  clarification: "澄清态"
};

const stopKindLabels = {
  hotel: "住宿",
  poi: "景点",
  food: "餐饮",
  transfer: "转场",
  flex: "机动"
};

const timeSlotLabels = {
  checkin: "入住",
  morning: "上午",
  afternoon: "下午",
  evening: "晚上",
  dining: "用餐",
  all_day: "全天"
};

const severityLabels = {
  info: "提示",
  warning: "注意",
  critical: "关键"
};

const clarificationFieldLabels = {
  destination: "目的地",
  city: "检索城市",
  departure_city: "出发城市",
  start_date: "出发日期",
  end_date: "返程日期",
  departure_date: "出发日期",
  travelers_count: "出行人数",
  days: "出行天数",
  budget: "总预算",
  accommodation_budget: "每晚住宿预算",
  hotel_budget: "每晚住宿预算",
  hotel_preferences: "住宿偏好",
  interests: "兴趣偏好",
  water_view: "水景偏好",
  must_visit_pois: "核心行程",
  transport_preferences: "交通偏好",
  constraints: "附加约束",
  notes: "补充说明"
};

function readResult(resultRef) {
  return resultRef?.value || null;
}

function formatDuration(minutes) {
  if (!minutes) {
    return "待确认";
  }
  return `${minutes} 分钟`;
}

function formatDistance(distance) {
  if (!distance) {
    return "距离待确认";
  }
  return `${distance} km`;
}

function slotWeight(slot) {
  const weights = {
    checkin: 18,
    morning: 26,
    afternoon: 48,
    dining: 64,
    evening: 78,
    all_day: 54
  };
  return weights[slot] || 52;
}

function formatStopKind(kind) {
  return stopKindLabels[kind] || kind;
}

function formatTimeSlot(slot) {
  return timeSlotLabels[slot] || slot;
}

function formatSeverity(severity) {
  return severityLabels[severity] || severity;
}

function formatCurrency(value, currency = "CNY") {
  if (value === null || value === undefined || value === "") {
    return "待确认";
  }
  return `${value} ${currency}`;
}

function budgetWidth(value, total) {
  if (!value || !total) {
    return "0%";
  }
  return `${Math.max(8, Math.min(100, Math.round((value / total) * 100)))}%`;
}

function budgetFillStyle(value, total) {
  return {
    "--budget-progress": budgetWidth(value, total)
  };
}

function formatDateTime(value) {
  if (!value) {
    return "本轮生成";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "本轮生成";
  }
  return date.toLocaleString("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function formatClarificationField(field, prompt = "") {
  if (field && clarificationFieldLabels[field]) {
    return clarificationFieldLabels[field];
  }
  if (prompt.includes("哪天出发") || prompt.includes("具体日期")) {
    return "出发日期";
  }
  if (prompt.includes("住宿每晚") || prompt.includes("每晚")) {
    return "每晚住宿预算";
  }
  if (prompt.includes("核心行程") || prompt.includes("经典地标")) {
    return "核心行程";
  }
  if (prompt.includes("水景")) {
    return "水景偏好";
  }
  return "待补充信息";
}

function buildClarificationTemplateLine(question, index) {
  const label = formatClarificationField(question.field, question.prompt);
  return `- ${index + 1}. ${label}：`;
}

function normalizedResultStatus(result) {
  const status = result?.status;
  return status === "degraded" ? "success" : status;
}

function hasReviewRisks(result) {
  if (!result) {
    return false;
  }
  return Boolean(
    result.warnings?.length
    || result.route_legs?.some((leg) => leg.status !== "live")
    || result.source_references?.some((source) => ["degraded", "unavailable"].includes(source.status))
  );
}

export function useResultPresentation(resultRef) {
  const budgetRows = computed(() => {
    const result = readResult(resultRef);
    const budget = result?.budget_breakdown || {};
    return [
      { key: "accommodation", label: "住宿", value: budget.accommodation },
      { key: "transportation", label: "交通", value: budget.transportation },
      { key: "food", label: "餐饮", value: budget.food },
      { key: "activities", label: "活动", value: budget.activities }
    ];
  });

  const quickPrompts = computed(() => {
    const result = readResult(resultRef);
    if (!result) {
      return [];
    }
    if (result.assistant_mode === "general") {
      return ["继续帮我规划一个两天的旅行路线。"];
    }
    if (result.status === "clarification") {
      return [];
    }
    return [
      "把预算压低一点，但保留核心景点。",
      "减少步行和跨区移动，改成更顺路。",
      "给我一版更适合下雨天的备选路线。"
    ];
  });

  const summaryPills = computed(() => {
    const result = readResult(resultRef);
    if (!result || result.assistant_mode === "general") {
      return [];
    }
    const items = [];
    const constraints = result.confirmed_constraints || {};
    if (constraints.destination) {
      items.push(`目的地 · ${constraints.destination}`);
    }
    if (constraints.departure_city) {
      items.push(`出发 · ${constraints.departure_city}`);
    }
    if (constraints.start_date) {
      items.push(`出发日 ${constraints.start_date}`);
    }
    if (constraints.days) {
      items.push(`${constraints.days} 天`);
    }
    if (constraints.travelers_count) {
      items.push(`${constraints.travelers_count} 人`);
    }
    if (constraints.budget) {
      items.push(`预算 ${constraints.budget} 元`);
    }
    if (result.route_overview?.total_stops) {
      items.push(`${result.route_overview.total_stops} 个停靠点`);
    }
    return items.slice(0, 4);
  });

  const refinementActions = computed(() => {
    const result = readResult(resultRef);
    if (!result || result.assistant_mode === "general") {
      return [];
    }
    if (result.status === "clarification") {
      return [];
    }
    return [
      {
        label: "更顺路",
        prompt: "把路线改得更顺路一些，尽量减少跨区折返。"
      },
      {
        label: "更适合带父母",
        prompt: "把这版路线调整成更适合带父母，少走路、少换乘。"
      },
      {
        label: "预算更低",
        prompt: "保留主要体验，但把预算整体压低一些。"
      },
      {
        label: "雨天方案",
        prompt: "给我一版更适合下雨天的路线，优先室内和连贯动线。"
      }
    ];
  });

  const clarificationItems = computed(() => {
    const result = readResult(resultRef);
    const questions = result?.clarification_questions || [];
    return questions.map((question, index) => {
      const fieldLabel = formatClarificationField(question.field, question.prompt);
      return {
        ...question,
        fieldLabel,
        index: index + 1,
        replyTemplate: [
          "请按下面补充后继续生成旅行方案：",
          buildClarificationTemplateLine(question, 0)
        ].join("\n")
      };
    });
  });

  const clarificationReplyTemplate = computed(() => {
    if (!clarificationItems.value.length) {
      return "";
    }
    return [
      "请按下面补充后继续生成旅行方案：",
      ...clarificationItems.value.map((question, index) => buildClarificationTemplateLine(question, index))
    ].join("\n");
  });

  const resultConfidenceTone = computed(() => {
    const result = readResult(resultRef);
    if (!result) {
      return "neutral";
    }
    if (result.assistant_mode === "general") {
      return "general";
    }
    if (normalizedResultStatus(result) === "failed") {
      return "critical";
    }
    if (normalizedResultStatus(result) === "clarification") {
      return "warning";
    }
    if (hasReviewRisks(result)) {
      return "caution";
    }
    if (result.plan_state === "final") {
      return "final";
    }
    return "draft";
  });

  const confidenceHeadline = computed(() => {
    const result = readResult(resultRef);
    if (!result) {
      return "";
    }
    if (result.assistant_mode === "general") {
      return "当前还是通用问答，尚未进入可判断的旅行路线结果。";
    }
    if (normalizedResultStatus(result) === "failed") {
      return "这一轮结果暂时不可直接用于旅行决策。";
    }
    if (normalizedResultStatus(result) === "clarification") {
      return "这版结果停在澄清阶段，先补关键信息比继续微调更有效。";
    }
    if (hasReviewRisks(result)) {
      return "这版路线已经可以继续使用，但部分数据仍建议在决策前做二次确认。";
    }
    if (result.plan_state === "final") {
      return "这版路线已经接近最终出行决策，可优先做行前确认。";
    }
    return "这版路线已经形成草案，适合继续围绕预算、顺路程度和点位选择微调。";
  });

  const confidenceDescription = computed(() => {
    const result = readResult(resultRef);
    if (!result) {
      return "";
    }
    if (result.assistant_mode === "general") {
      return "继续补充目的地、天数、预算或必去点位后，系统会切回旅行规划模式并生成路线结果。";
    }
    if (normalizedResultStatus(result) === "failed") {
      return "建议回看执行轨迹和输入条件，确认失败原因后重新发起一轮生成。";
    }
    if (normalizedResultStatus(result) === "clarification") {
      return result.clarification_questions?.length
        ? `当前还缺少 ${result.clarification_questions.length} 项关键信息；补齐后更容易形成稳定路线。`
        : "系统仍需要更多关键信息，当前不建议把这一版当成正式路线。";
    }
    if (hasReviewRisks(result)) {
      return "可以先用它做路线方向和结构判断，但涉及预算、时间和资源可用性的部分仍建议二次确认。";
    }
    if (result.plan_state === "final") {
      return "如果目的地、时间和预算已基本稳定，可以将这一版作为最终方案保存，再基于变化做小范围修订。";
    }
    return "先判断这一版是否满足当前旅行意图，再决定继续修订、暂存草案，还是沉淀为最终方案。";
  });

  const confidenceMetrics = computed(() => {
    const result = readResult(resultRef);
    if (!result) {
      return [];
    }
    const metrics = [
      {
        label: "生成时间",
        value: formatDateTime(result.generated_at)
      }
    ];

    if (result.assistant_mode !== "general") {
      metrics.push({
        label: "来源数量",
        value: result.source_references?.length ? `${result.source_references.length} 条` : "待补充"
      });

      if (result.clarification_questions?.length) {
        metrics.push({
          label: "待补充",
          value: `${result.clarification_questions.length} 项`
        });
      } else if (result.warnings?.length) {
        metrics.push({
          label: "风险提醒",
          value: `${result.warnings.length} 条`
        });
      } else {
        metrics.push({
          label: "当前语义",
          value: planStateLabels[result.plan_state] || result.plan_state || "待确认"
        });
      }
    }

    return metrics.slice(0, 3);
  });

  const confidenceGuidanceCards = computed(() => {
    const result = readResult(resultRef);
    if (!result) {
      return [];
    }
    if (result.assistant_mode === "general") {
      return [
        {
          label: "现在适合",
          title: "继续补条件",
          detail: "给出目的地、天数、预算或必去点位后，结果面板会进入正式的旅行规划语义。"
        },
        {
          label: "使用边界",
          title: "暂不构成路线",
          detail: "当前回复更适合答疑，不适合作为旅行计划草案或最终方案保存。"
        },
        {
          label: "下一步",
          title: "切回规划模式",
          detail: "直接告诉系统你的目的地和时间范围，下一轮就能开始收敛路线。"
        }
      ];
    }

    const guidance = [];

    if (normalizedResultStatus(result) === "failed") {
      guidance.push(
        {
          label: "现在适合",
          title: "先定位失败原因",
          detail: "优先查看执行轨迹中的失败节点，再决定是重试还是补充约束。"
        },
        {
          label: "使用边界",
          title: "不要直接采用",
          detail: "失败态下的内容不应被当成旅行决策依据，也不适合沉淀成方案版本。"
        },
        {
          label: "下一步",
          title: "重新发起生成",
          detail: "补齐缺失条件或缩小问题范围后，再让系统生成一版新的路线。"
        }
      );
      return guidance;
    }

    if (normalizedResultStatus(result) === "clarification") {
      guidance.push(
        {
          label: "现在适合",
          title: "优先回答澄清问题",
          detail: "先补关键条件，系统才能把当前上下文继续收敛成可执行路线。"
        },
        {
          label: "使用边界",
          title: "暂不适合定稿",
          detail: "这一版更像阶段中间态，不建议直接拿来做最终决策或保存为最终方案。"
        },
        {
          label: "下一步",
          title: "补第一条缺口",
          detail: "优先回应最上面的澄清问题，通常能最快推动结果从澄清态进入草案态。"
        }
      );
      return guidance;
    }

    if (hasReviewRisks(result)) {
      guidance.push(
        {
          label: "现在适合",
          title: "先判断方向是否成立",
          detail: "可以优先确认路线结构、区域顺序和主要停靠点是否符合你的意图。"
        },
        {
          label: "使用边界",
          title: "关键数据需复核",
          detail: "预算、距离、时长或资源可用性中可能有估算成分，重要决策前建议二次确认。"
        },
        {
          label: "下一步",
          title: "围绕风险继续修订",
          detail: "根据提醒继续缩减预算、减少跨区移动，或生成更稳妥的备选路线。"
        }
      );
      return guidance;
    }

    if (result.plan_state === "final") {
      guidance.push(
        {
          label: "现在适合",
          title: "作为行前确认底稿",
          detail: "当前已经接近最终版，适合做最后一轮预算、节奏和资源核对。"
        },
        {
          label: "使用边界",
          title: "变化时再派生修订",
          detail: "如果目的地、同行人或节奏发生变化，建议基于这版派生新的继续修订会话。"
        },
        {
          label: "下一步",
          title: "保存为最终方案",
          detail: "在关键风险可接受的前提下，可以将它沉淀为最终方案，后续按版本继续演进。"
        }
      );
      return guidance;
    }

    guidance.push(
      {
        label: "现在适合",
        title: "继续做局部取舍",
        detail: "草案态最适合围绕预算、动线顺路程度和必去点位做小范围调整。"
      },
      {
        label: "使用边界",
        title: "先别急着定稿",
        detail: "如果还有明显的不确定项，先保存草案更稳妥，等路线收敛后再转成最终方案。"
      },
      {
        label: "下一步",
        title: "继续微调或先暂存",
        detail: "你可以直接给出改动方向，也可以先保存这版草案，稍后从历史资产继续修订。"
      }
    );
    return guidance;
  });

  const decisionCards = computed(() => {
    const result = readResult(resultRef);
    if (!result || result.assistant_mode === "general") {
      return [];
    }
    const cards = [];
    const constraints = result.confirmed_constraints || {};
    cards.push({
      label: "当前阶段",
      value: planStateLabels[result.plan_state] || result.plan_state,
      detail: statusLabels[result.status] || result.status
    });
    if (constraints.destination || constraints.days) {
      cards.push({
        label: "规划范围",
        value: [constraints.destination, constraints.days ? `${constraints.days} 天` : ""].filter(Boolean).join(" · "),
        detail: constraints.budget ? `预算 ${constraints.budget} 元` : "预算待进一步确认"
      });
    }
    if (result.route_overview?.total_stops) {
      cards.push({
        label: "路线规模",
        value: `${result.route_overview.total_stops} 个停靠点`,
        detail: result.route_overview.strategy
      });
    }
    if (result.warnings?.length || result.alternatives?.length) {
      cards.push({
        label: "决策提示",
        value: result.warnings?.length ? `${result.warnings.length} 条提醒` : `${result.alternatives.length} 条备选`,
        detail: result.warnings?.[0]?.message || result.alternatives?.[0]?.summary || "可以继续微调当前方案。"
      });
    }
    return cards.slice(0, 4);
  });

  const routeDays = computed(() => {
    const result = readResult(resultRef);
    if (!result?.route_stops?.length) {
      return [];
    }
    const itineraryByDay = new Map((result.daily_itinerary || []).map((item) => [item.day, item]));
    const grouped = new Map();

    for (const stop of result.route_stops) {
      const day = stop.day || 1;
      if (!grouped.has(day)) {
        grouped.set(day, []);
      }
      grouped.get(day).push(stop);
    }

    return [...grouped.entries()]
      .sort(([left], [right]) => left - right)
      .map(([day, stops]) => {
        const sortedStops = [...stops].sort((left, right) => left.order - right.order);
        const legs = (result.route_legs || []).filter((leg) => leg.day === day);
        const totalMinutes = legs.reduce((sum, leg) => sum + (leg.estimated_duration_minutes || 0), 0);
        const totalDistance = legs.reduce((sum, leg) => sum + (leg.estimated_distance_km || 0), 0);
        return {
          day,
          theme: itineraryByDay.get(day)?.theme || `第 ${day} 天路线`,
          stops: sortedStops,
          legs,
          totalMinutes,
          totalDistance: totalDistance ? Number(totalDistance.toFixed(1)) : null
        };
      });
  });

  const previewStops = computed(() => {
    const result = readResult(resultRef);
    const stops = result?.route_stops || [];
    if (!stops.length) {
      return [];
    }
    return stops.map((stop, index) => {
      const total = Math.max(stops.length - 1, 1);
      const x = 12 + (index / total) * 72;
      const y = slotWeight(stop.time_slot) + (stop.day - 1) * 4;
      return {
        ...stop,
        mapX: Number(x.toFixed(1)),
        mapY: Number(Math.min(86, y).toFixed(1)),
        pinStyle: {
          "--route-pin-left": `${Number(x.toFixed(1))}%`,
          "--route-pin-top": `${Number(Math.min(86, y).toFixed(1))}%`
        }
      };
    });
  });

  const previewSegments = computed(() => {
    const stops = previewStops.value;
    if (stops.length < 2) {
      return [];
    }
    return stops.slice(0, -1).map((stop, index) => {
      const next = stops[index + 1];
      const dx = next.mapX - stop.mapX;
      const dy = next.mapY - stop.mapY;
      const length = Math.sqrt(dx * dx + dy * dy);
      const angle = Math.atan2(dy, dx) * (180 / Math.PI);
      return {
        id: `${stop.stop_id}-${next.stop_id}`,
        left: stop.mapX,
        top: stop.mapY,
        width: length,
        angle,
        segmentStyle: {
          "--route-segment-left": `${stop.mapX}%`,
          "--route-segment-top": `${stop.mapY}%`,
          "--route-segment-width": `${length}%`,
          "--route-segment-angle": `${angle}deg`
        }
      };
    });
  });

  const changeHighlights = computed(() => {
    const result = readResult(resultRef);
    if (!result) {
      return [];
    }
    const highlights = [];
    const notes = result.revision_notes || [];
    if (notes.length) {
      for (const note of notes.slice(0, 3)) {
        highlights.push({
          title: note.summary,
          detail: note.changes?.length ? note.changes.join("；") : "本轮根据你的反馈做了局部调整。"
        });
      }
    }
    if (!highlights.length && result.route_overview) {
      highlights.push({
        title: "路线结构已收敛",
        detail: result.route_overview.strategy
      });
    }
    if ((result.alternatives || []).length) {
      highlights.push({
        title: "已给出替代版本",
        detail: `当前还保留了 ${(result.alternatives || []).length} 条备选动线，方便继续做取舍。`
      });
    }
    if ((result.warnings || []).length) {
      highlights.push({
        title: "风险点已标出",
        detail: (result.warnings || []).slice(0, 2).map((item) => item.message).join("；")
      });
    }
    return highlights.slice(0, 4);
  });

  return {
    budgetFillStyle,
    budgetRows,
    changeHighlights,
    clarificationItems,
    clarificationReplyTemplate,
    confidenceDescription,
    confidenceGuidanceCards,
    confidenceHeadline,
    confidenceMetrics,
    decisionCards,
    formatCurrency,
    formatDistance,
    formatDuration,
    formatSeverity,
    formatStopKind,
    formatTimeSlot,
    planStateLabels,
    previewSegments,
    previewStops,
    quickPrompts,
    refinementActions,
    resultConfidenceTone,
    routeDays,
    severityLabels,
    statusLabels,
    summaryPills
  };
}
