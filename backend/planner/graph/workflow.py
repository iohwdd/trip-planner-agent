from __future__ import annotations

from typing import Callable

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - sequential fallback remains available
    END = None
    START = None
    StateGraph = None

from planner.domain.schemas import (
    ExecutionStep,
    PlanningContext,
    TripPlanOutput,
    TripPlanningRequest,
    WorkflowState,
)
from planner.graph.nodes import PlanningNodes
from planner.services.planning_context import build_form_context


StepCallback = Callable[[ExecutionStep], None]


class TripPlannerWorkflow:
    def __init__(self, nodes: PlanningNodes) -> None:
        self.nodes = nodes

    def run(
        self,
        request: TripPlanningRequest,
        step_callback: StepCallback | None = None,
    ) -> TripPlanOutput:
        return self.run_context(build_form_context(request), step_callback)

    def run_context(
        self,
        context: PlanningContext,
        step_callback: StepCallback | None = None,
    ) -> TripPlanOutput:
        step_callback = step_callback or (lambda step: None)
        try:
            return self._run_with_langgraph(context, step_callback)
        except Exception:
            return self._run_sequential(context, step_callback)

    def _run_with_langgraph(
        self,
        context: PlanningContext,
        step_callback: StepCallback,
    ) -> TripPlanOutput:
        if StateGraph is None or START is None or END is None:
            raise RuntimeError("langgraph is not installed")

        graph = StateGraph(dict)
        graph.add_node("normalize_input", lambda state: self._wrap_step(state, step_callback, self.nodes.normalize_input))
        graph.add_node("assess_requirements", lambda state: self._wrap_step(state, step_callback, self.nodes.assess_requirements))
        graph.add_node("fetch_live_data", lambda state: self._wrap_step(state, step_callback, self.nodes.fetch_live_data))
        graph.add_node("validate_live_data", lambda state: self._wrap_step(state, step_callback, self.nodes.validate_live_data))
        graph.add_node("plan_trip", lambda state: self._wrap_step(state, step_callback, self.nodes.plan_trip))
        graph.add_node("build_route_plan", lambda state: self._wrap_step(state, step_callback, self.nodes.build_route_plan))
        graph.add_node("verify_plan_consistency", lambda state: self._wrap_step(state, step_callback, self.nodes.verify_plan_consistency))

        graph.add_edge(START, "normalize_input")
        graph.add_edge("normalize_input", "assess_requirements")
        graph.add_edge("assess_requirements", "fetch_live_data")
        graph.add_edge("fetch_live_data", "validate_live_data")
        graph.add_edge("validate_live_data", "plan_trip")
        graph.add_edge("plan_trip", "build_route_plan")
        graph.add_edge("build_route_plan", "verify_plan_consistency")
        graph.add_edge("verify_plan_consistency", END)

        compiled = graph.compile()
        state = WorkflowState(request=context.request, planning_context=context)
        compiled.invoke({"workflow_state": state})
        return self._finalize(state, step_callback)

    def _run_sequential(
        self,
        context: PlanningContext,
        step_callback: StepCallback,
    ) -> TripPlanOutput:
        state = WorkflowState(request=context.request, planning_context=context)
        state, step = self.nodes.normalize_input(state)
        step_callback(step)

        state, step = self.nodes.assess_requirements(state)
        step_callback(step)

        if state.status == "clarification":
            return self._finalize(state, step_callback)

        state, step = self.nodes.fetch_live_data(state)
        step_callback(step)

        state, step = self.nodes.validate_live_data(state)
        step_callback(step)

        if state.status == "clarification":
            return self._finalize(state, step_callback)

        state, step = self.nodes.plan_trip(state)
        step_callback(step)

        state, step = self.nodes.build_route_plan(state)
        step_callback(step)

        state, step = self.nodes.verify_plan_consistency(state)
        step_callback(step)
        return self._finalize(state, step_callback)

    def _finalize(self, state: WorkflowState, step_callback: StepCallback) -> TripPlanOutput:
        if state.status == "failed":
            _, output, step = self.nodes.fallback_or_clarify(state)
        else:
            _, output, step = self.nodes.assemble_output(state)
        step_callback(step)
        return output

    @staticmethod
    def _wrap_step(state: dict, callback: StepCallback, func):
        workflow_state = state["workflow_state"]
        workflow_state, step = func(workflow_state)
        callback(step)
        return {"workflow_state": workflow_state}
