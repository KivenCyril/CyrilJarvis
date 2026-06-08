"""Workflow execution engine for JARVIS.

Executes workflows with full support for branching, loops, sub-workflows,
approval gates, data transformations, and parallel execution.
"""

from __future__ import annotations

import asyncio
import logging
import operator
import re
import time
from datetime import datetime, timezone
from typing import Any

from .models import (
    StepType,
    Workflow,
    WorkflowStatus,
    WorkflowStep,
)

logger = logging.getLogger(__name__)

# Safe operators for expression evaluation
_COMPARE_OPS: dict[str, Any] = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "in": lambda a, b: a in b,
    "not in": lambda a, b: a not in b,
}


class WorkflowEngine:
    """Executes workflows with full support for branching, loops, and sub-workflows.

    Execution model:
    1. Initialize variables from input
    2. Find ready steps (no unmet dependencies)
    3. Execute ready steps (parallel when possible)
    4. Handle step results:
       - ACTION: record output, proceed
       - CONDITION: evaluate, follow true/false branch
       - LOOP: iterate over collection, execute body for each item
       - PARALLEL: execute child steps concurrently
       - SUB_WORKFLOW: launch child workflow, wait for completion
       - WAIT: sleep or wait for event
       - APPROVAL: pause and wait for human approval
       - TRANSFORM: apply transformation to data
    5. Check for completion or errors
    6. Repeat from step 2
    """

    def __init__(self, orchestrator: Any | None = None, llm_registry: Any | None = None):
        self._workflows: dict[str, Workflow] = {}
        self._orchestrator = orchestrator
        self._llm = llm_registry
        self._execution_log: list[dict[str, Any]] = []
        self._approval_events: dict[str, asyncio.Event] = {}
        self._approval_results: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self, workflow: Workflow, input_data: dict[str, Any] | None = None
    ) -> Workflow:
        """Execute a workflow end-to-end.

        Args:
            workflow: The workflow to execute.
            input_data: Optional mapping of variable name -> value to
                populate before execution starts.

        Returns:
            The same ``Workflow`` instance with updated step statuses and
            variable values.
        """
        # Register
        self._workflows[workflow.id] = workflow

        # Initialise variables from input
        if input_data:
            for key, val in input_data.items():
                workflow.set_variable(key, val)

        # Validate
        errors = workflow.validate()
        if errors:
            workflow.status = WorkflowStatus.FAILED
            self._log(workflow.id, "validation_failed", {"errors": errors})
            logger.error("Workflow %s validation failed: %s", workflow.id, errors)
            return workflow

        workflow.status = WorkflowStatus.RUNNING
        self._log(workflow.id, "started", {})

        try:
            await self._run_loop(workflow)
        except Exception as exc:
            workflow.status = WorkflowStatus.FAILED
            self._log(workflow.id, "error", {"error": str(exc)})
            logger.exception("Workflow %s failed", workflow.id)
            return workflow

        # Determine final status
        if workflow.status == WorkflowStatus.PAUSED:
            pass  # stay paused (approval gate)
        elif any(s.is_failed for s in workflow.steps):
            workflow.status = WorkflowStatus.FAILED
        elif workflow.status != WorkflowStatus.CANCELLED:
            workflow.status = WorkflowStatus.COMPLETED

        self._log(workflow.id, "finished", {"status": workflow.status.value})
        return workflow

    async def pause(self, workflow_id: str) -> None:
        """Pause a running workflow."""
        wf = self._workflows.get(workflow_id)
        if wf and wf.status == WorkflowStatus.RUNNING:
            wf.status = WorkflowStatus.PAUSED
            self._log(workflow_id, "paused", {})

    async def resume(self, workflow_id: str) -> None:
        """Resume a paused workflow."""
        wf = self._workflows.get(workflow_id)
        if wf and wf.status == WorkflowStatus.PAUSED:
            wf.status = WorkflowStatus.RUNNING
            self._log(workflow_id, "resumed", {})
            await self._run_loop(wf)
            if not any(s.is_failed for s in wf.steps):
                if wf.status != WorkflowStatus.PAUSED:
                    wf.status = WorkflowStatus.COMPLETED
            else:
                wf.status = WorkflowStatus.FAILED

    async def cancel(self, workflow_id: str) -> None:
        """Cancel a running or paused workflow."""
        wf = self._workflows.get(workflow_id)
        if wf:
            wf.status = WorkflowStatus.CANCELLED
            self._log(workflow_id, "cancelled", {})

    async def approve(
        self, workflow_id: str, step_id: str, approved: bool
    ) -> None:
        """Approve or reject a pending approval step.

        Sets the approval result and signals the waiting coroutine.
        """
        key = f"{workflow_id}:{step_id}"
        self._approval_results[key] = approved
        evt = self._approval_events.get(key)
        if evt:
            evt.set()
        self._log(
            workflow_id,
            "approval",
            {"step_id": step_id, "approved": approved},
        )

    def get_execution_log(
        self, workflow_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Return execution log entries, optionally filtered by workflow."""
        if workflow_id is None:
            return list(self._execution_log)
        return [e for e in self._execution_log if e.get("workflow_id") == workflow_id]

    # ------------------------------------------------------------------
    # Main execution loop
    # ------------------------------------------------------------------

    async def _run_loop(self, workflow: Workflow) -> None:
        """Core scheduling loop: find ready steps and execute them."""
        max_iterations = sum(s.max_iterations for s in workflow.steps) + len(workflow.steps) * 2
        iteration = 0

        while workflow.status == WorkflowStatus.RUNNING:
            iteration += 1
            if iteration > max_iterations:
                logger.warning("Workflow %s exceeded max iterations", workflow.id)
                break

            ready = workflow.get_ready_steps()
            if not ready:
                # Nothing left to do — either all done or we're stuck
                break

            # Execute all ready steps (in parallel if more than one)
            if len(ready) == 1:
                await self._execute_step(workflow, ready[0])
            else:
                tasks = [self._execute_step(workflow, s) for s in ready]
                await asyncio.gather(*tasks)

            # If workflow was paused (e.g. by approval), stop the loop
            if workflow.status != WorkflowStatus.RUNNING:
                break

    # ------------------------------------------------------------------
    # Step dispatcher
    # ------------------------------------------------------------------

    async def _execute_step(self, workflow: Workflow, step: WorkflowStep) -> None:
        """Dispatch a single step based on its type."""
        step.mark_running()
        self._log(
            workflow.id,
            "step_started",
            {"step_id": step.id, "step_name": step.name, "type": step.step_type.value},
        )

        try:
            handler = {
                StepType.ACTION: self._execute_action_step,
                StepType.CONDITION: self._execute_condition_step,
                StepType.LOOP: self._execute_loop,
                StepType.PARALLEL: self._execute_parallel,
                StepType.SUB_WORKFLOW: self._execute_sub_workflow,
                StepType.WAIT: self._execute_wait,
                StepType.APPROVAL: self._execute_approval,
                StepType.TRANSFORM: self._execute_transform,
            }.get(step.step_type, self._execute_action_step)

            result = await handler(workflow, step)
            if step.status == "running":
                step.mark_completed(result)

            self._log(
                workflow.id,
                "step_completed",
                {"step_id": step.id, "step_name": step.name, "output": result},
            )
        except Exception as exc:
            await self._handle_step_error(workflow, step, exc)

    # ------------------------------------------------------------------
    # Step type handlers
    # ------------------------------------------------------------------

    async def _execute_action_step(
        self, workflow: Workflow, step: WorkflowStep
    ) -> Any:
        """Execute an action step via the orchestrator or as a no-op."""
        if self._orchestrator is not None:
            # Delegate to orchestrator
            result = await self._orchestrator.execute_task(
                agent=step.agent,
                action=step.action,
                tool=step.tool,
                tool_args=step.tool_args,
            )
            return result

        # No orchestrator — return a synthetic result for testing
        return {
            "status": "completed",
            "agent": step.agent,
            "action": step.action,
        }

    async def _execute_condition_step(
        self, workflow: Workflow, step: WorkflowStep
    ) -> bool:
        """Evaluate a condition and activate the appropriate branch."""
        result = await self._evaluate_condition(workflow, step)
        step.mark_completed(result)

        # Activate / skip the correct branch
        if step.on_true or step.on_false:
            target_id = step.on_true if result else step.on_false
            skip_id = step.on_false if result else step.on_true
            if skip_id:
                skip_step = workflow.get_step(skip_id)
                if skip_step and skip_step.is_pending:
                    skip_step.mark_skipped()

        # Also handle ConditionalBranch objects
        for branch in workflow.branches:
            if branch.condition == step.condition:
                active = branch.true_branch if result else branch.false_branch
                inactive = branch.false_branch if result else branch.true_branch
                for sid in inactive:
                    s = workflow.get_step(sid)
                    if s and s.is_pending:
                        s.mark_skipped()

        return result

    async def _evaluate_condition(
        self, workflow: Workflow, step: WorkflowStep
    ) -> bool:
        """Evaluate a condition expression.

        Supports:
        - Simple comparisons: ``variable > 5``, ``result == 'success'``
        - Variable references: ``steps.step1.output.score > 0.8``
        - Boolean logic: ``var1 and var2``, ``not var3``
        - Membership: ``value in ['a', 'b']``
        """
        expr = step.condition.strip()
        if not expr:
            return True

        return self._eval_expression(workflow, expr)

    def _eval_expression(self, workflow: Workflow, expr: str) -> bool:
        """Safely evaluate a boolean expression against workflow context."""

        # Handle "not ..."
        if expr.startswith("not "):
            return not self._eval_expression(workflow, expr[4:].strip())

        # Handle "... and ..."
        if " and " in expr:
            parts = expr.split(" and ", 1)
            return self._eval_expression(
                workflow, parts[0].strip()
            ) and self._eval_expression(workflow, parts[1].strip())

        # Handle "... or ..."
        if " or " in expr:
            parts = expr.split(" or ", 1)
            return self._eval_expression(
                workflow, parts[0].strip()
            ) or self._eval_expression(workflow, parts[1].strip())

        # "x in [...]" / "x not in [...]"
        not_in_match = re.match(
            r"(.+?)\s+not\s+in\s+(.+)", expr
        )
        in_match = re.match(r"(.+?)\s+in\s+(.+)", expr)

        if not_in_match:
            left = self._resolve_expression(workflow, not_in_match.group(1).strip())
            right = self._resolve_expression(workflow, not_in_match.group(2).strip())
            return left not in right

        if in_match:
            left = self._resolve_expression(workflow, in_match.group(1).strip())
            right = self._resolve_expression(workflow, in_match.group(2).strip())
            return left in right

        # Comparison operators
        for op_str in ("!=", ">=", "<=", "==", ">", "<"):
            if op_str in expr:
                parts = expr.split(op_str, 1)
                left = self._resolve_expression(workflow, parts[0].strip())
                right = self._resolve_expression(workflow, parts[1].strip())
                return _COMPARE_OPS[op_str](left, right)

        # Single value — truthy check
        val = self._resolve_expression(workflow, expr)
        return bool(val)

    async def _execute_loop(
        self, workflow: Workflow, step: WorkflowStep
    ) -> list[Any]:
        """Execute a loop step, iterating over a collection.

        For each element in the ``loop_over`` variable, sets
        ``loop_variable`` and executes the loop body steps.
        """
        collection = self._resolve_expression(workflow, step.loop_over)
        if not isinstance(collection, (list, tuple)):
            collection = list(collection) if collection else []

        results: list[Any] = []
        iterations = min(len(collection), step.max_iterations)

        for i in range(iterations):
            item = collection[i]
            workflow.set_variable(step.loop_variable, item)
            workflow.set_variable("loop_index", i)

            # Reset loop body steps for this iteration
            for body_id in step.loop_body:
                body_step = workflow.get_step(body_id)
                if body_step:
                    body_step.reset()

            # Execute body steps sequentially
            for body_id in step.loop_body:
                body_step = workflow.get_step(body_id)
                if body_step:
                    await self._execute_step(workflow, body_step)
                    results.append(body_step.output)

        return results

    async def _execute_parallel(
        self, workflow: Workflow, step: WorkflowStep
    ) -> list[Any]:
        """Execute parallel child steps concurrently.

        Uses ``depends_on`` in reverse: steps that depend on nothing and
        are listed in step.loop_body (reused as child step list) run
        concurrently.
        """
        child_ids = step.loop_body  # reuse loop_body as child list
        if not child_ids:
            # If no explicit children, find steps that depend only on this step
            child_ids = [
                s.id for s in workflow.steps
                if step.id in s.depends_on and s.is_pending
            ]

        tasks = []
        for cid in child_ids:
            child = workflow.get_step(cid)
            if child and child.is_pending:
                tasks.append(self._execute_step(workflow, child))

        if tasks:
            await asyncio.gather(*tasks)

        results = []
        for cid in child_ids:
            child = workflow.get_step(cid)
            if child:
                results.append(child.output)
        return results

    async def _execute_sub_workflow(
        self, workflow: Workflow, step: WorkflowStep
    ) -> Any:
        """Launch and execute a sub-workflow.

        Looks up the sub-workflow by ID from registered workflows,
        maps input variables, executes it, and returns its output.
        """
        sub_wf = self._workflows.get(step.sub_workflow_id)
        if sub_wf is None:
            raise ValueError(
                f"Sub-workflow '{step.sub_workflow_id}' not found"
            )

        # Map inputs
        input_data: dict[str, Any] = {}
        for target_var, source_expr in step.sub_workflow_input.items():
            input_data[target_var] = self._resolve_expression(
                workflow, source_expr
            )

        # Execute sub-workflow
        sub_wf.parent_workflow_id = workflow.id
        sub_wf.reset_all_steps()
        await self.execute(sub_wf, input_data)

        # Return sub-workflow outputs as dict
        return {
            "status": sub_wf.status.value,
            "variables": {v.name: v.resolve() for v in sub_wf.variables},
        }

    async def _execute_wait(
        self, workflow: Workflow, step: WorkflowStep
    ) -> dict[str, Any]:
        """Execute a wait step — sleep for the specified duration."""
        if step.wait_seconds > 0:
            await asyncio.sleep(step.wait_seconds)
        return {"waited": step.wait_seconds}

    async def _execute_approval(
        self, workflow: Workflow, step: WorkflowStep
    ) -> dict[str, Any]:
        """Execute an approval step — pause and wait for human approval.

        The workflow is paused until ``approve()`` is called.
        """
        key = f"{workflow.id}:{step.id}"

        # Check if already approved (pre-approved before execution)
        if key in self._approval_results:
            approved = self._approval_results.pop(key)
            step.mark_completed({"approved": approved})
            if not approved:
                step.mark_failed("Approval rejected")
            return {"approved": approved}

        # Set up event and pause
        evt = asyncio.Event()
        self._approval_events[key] = evt
        workflow.status = WorkflowStatus.PAUSED
        step.status = "waiting_approval"

        self._log(
            workflow.id,
            "approval_required",
            {"step_id": step.id, "message": step.approval_message},
        )

        # Wait for approval signal
        await evt.wait()

        # Process result
        approved = self._approval_results.pop(key, False)
        self._approval_events.pop(key, None)

        if approved:
            step.mark_completed({"approved": True})
            workflow.status = WorkflowStatus.RUNNING
        else:
            step.mark_failed("Approval rejected")
            workflow.status = WorkflowStatus.RUNNING

        return {"approved": approved}

    async def _execute_transform(
        self, workflow: Workflow, step: WorkflowStep
    ) -> Any:
        """Apply data transformation between steps.

        Transform expressions:
        - ``upper(variable)`` -- string uppercase
        - ``lower(variable)`` -- string lowercase
        - ``json_extract(data, 'key.nested')`` -- JSON path extraction
        - ``concat(a, b)`` -- string concatenation
        - ``sum(items)`` -- numeric aggregation
        - ``len(items)`` -- collection length
        - ``map(items, field)`` -- extract field from list of dicts
        - ``filter(items, field, value)`` -- filter list of dicts
        """
        expr = step.transform_expression.strip()
        if not expr:
            return None

        return self._apply_transform(workflow, expr)

    # ------------------------------------------------------------------
    # Transform helpers
    # ------------------------------------------------------------------

    def _apply_transform(self, workflow: Workflow, expr: str) -> Any:
        """Parse and apply a transform expression."""
        # Function-style: func(args...)
        func_match = re.match(r"(\w+)\((.+)\)$", expr, re.DOTALL)
        if func_match:
            func_name = func_match.group(1)
            raw_args = func_match.group(2)
            args = self._parse_func_args(raw_args)
            return self._call_transform_func(workflow, func_name, args)

        # Fallback: resolve as expression
        return self._resolve_expression(workflow, expr)

    def _parse_func_args(self, raw: str) -> list[str]:
        """Split function arguments respecting quotes and nested parens."""
        args: list[str] = []
        depth = 0
        current = ""
        in_quote: str | None = None

        for ch in raw:
            if in_quote:
                current += ch
                if ch == in_quote:
                    in_quote = None
                continue
            if ch in ("'", '"'):
                in_quote = ch
                current += ch
                continue
            if ch == "(":
                depth += 1
                current += ch
            elif ch == ")":
                depth -= 1
                current += ch
            elif ch == "," and depth == 0:
                args.append(current.strip())
                current = ""
            else:
                current += ch

        if current.strip():
            args.append(current.strip())
        return args

    def _call_transform_func(
        self, workflow: Workflow, func: str, args: list[str]
    ) -> Any:
        """Execute a named transform function."""
        if func == "upper":
            val = self._resolve_expression(workflow, args[0])
            return str(val).upper() if val is not None else ""

        if func == "lower":
            val = self._resolve_expression(workflow, args[0])
            return str(val).lower() if val is not None else ""

        if func == "concat":
            parts = [
                str(self._resolve_expression(workflow, a)) for a in args
            ]
            return "".join(parts)

        if func == "sum":
            val = self._resolve_expression(workflow, args[0])
            if isinstance(val, (list, tuple)):
                return sum(val)
            return val

        if func == "len":
            val = self._resolve_expression(workflow, args[0])
            if val is None:
                return 0
            return len(val)

        if func == "json_extract":
            data = self._resolve_expression(workflow, args[0])
            path = args[1].strip("'\"")
            return self._json_path(data, path)

        if func == "map":
            items = self._resolve_expression(workflow, args[0])
            field = args[1].strip("'\"")
            if isinstance(items, list):
                return [
                    item.get(field) if isinstance(item, dict) else None
                    for item in items
                ]
            return []

        if func == "filter":
            items = self._resolve_expression(workflow, args[0])
            field = args[1].strip("'\"")
            value = self._resolve_expression(workflow, args[2])
            if isinstance(items, list):
                return [
                    item
                    for item in items
                    if isinstance(item, dict) and item.get(field) == value
                ]
            return []

        raise ValueError(f"Unknown transform function: {func}")

    @staticmethod
    def _json_path(data: Any, path: str) -> Any:
        """Extract a value from nested dicts/lists via dot-separated path."""
        if data is None:
            return None
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, (list, tuple)):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return current

    # ------------------------------------------------------------------
    # Expression resolution
    # ------------------------------------------------------------------

    def _resolve_expression(self, workflow: Workflow, expression: str) -> Any:
        """Resolve a variable expression to its value.

        Supports:
        - Direct variable: ``my_var``
        - Step output: ``steps.step_id.output``
        - Nested: ``steps.step_id.output.key.subkey``
        - Literals: numbers, quoted strings, booleans, lists
        """
        expr = expression.strip()

        # Quoted string literal
        if (expr.startswith("'") and expr.endswith("'")) or (
            expr.startswith('"') and expr.endswith('"')
        ):
            return expr[1:-1]

        # Boolean literals
        if expr.lower() == "true":
            return True
        if expr.lower() == "false":
            return False
        if expr.lower() == "none":
            return None

        # Numeric literal
        try:
            if "." in expr:
                return float(expr)
            return int(expr)
        except ValueError:
            pass

        # List literal: ['a', 'b', 'c']
        if expr.startswith("[") and expr.endswith("]"):
            inner = expr[1:-1].strip()
            if not inner:
                return []
            items = [
                self._resolve_expression(workflow, item.strip())
                for item in self._split_list_items(inner)
            ]
            return items

        # Step output reference: steps.<name_or_id>.output[.path...]
        if expr.startswith("steps."):
            return self._resolve_step_ref(workflow, expr)

        # Workflow variable
        val = workflow.get_variable(expr)
        if val is not None:
            return val

        # Return expression as-is if nothing matched
        return expr

    def _resolve_step_ref(self, workflow: Workflow, expr: str) -> Any:
        """Resolve ``steps.<id_or_name>.<field>[.path]``."""
        parts = expr.split(".")
        if len(parts) < 3:
            return None

        step_ref = parts[1]
        field = parts[2]

        # Find step by ID first, then by name
        step = workflow.get_step(step_ref)
        if step is None:
            step = workflow.get_step_by_name(step_ref)
        if step is None:
            return None

        # Get field
        if field == "output":
            value = step.output
        elif field == "status":
            value = step.status
        elif field == "error":
            value = step.error
        else:
            value = getattr(step, field, None)

        # Resolve nested path
        remaining = parts[3:]
        for part in remaining:
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, (list, tuple)):
                try:
                    value = value[int(part)]
                except (ValueError, IndexError):
                    return None
            else:
                return None

        return value

    @staticmethod
    def _split_list_items(s: str) -> list[str]:
        """Split comma-separated list items respecting quotes."""
        items: list[str] = []
        current = ""
        in_quote: str | None = None

        for ch in s:
            if in_quote:
                current += ch
                if ch == in_quote:
                    in_quote = None
                continue
            if ch in ("'", '"'):
                in_quote = ch
                current += ch
            elif ch == ",":
                items.append(current.strip())
                current = ""
            else:
                current += ch

        if current.strip():
            items.append(current.strip())
        return items

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    async def _handle_step_error(
        self, workflow: Workflow, step: WorkflowStep, exc: Exception
    ) -> None:
        """Handle a step execution error according to workflow policy."""
        error_msg = str(exc)
        self._log(
            workflow.id,
            "step_error",
            {"step_id": step.id, "step_name": step.name, "error": error_msg},
        )

        policy = workflow.on_error

        if policy == "retry" and step.retry_count < step.max_retries:
            step.retry_count += 1
            step.status = "pending"
            step.error = ""
            step.started_at = None
            logger.info(
                "Retrying step %s (attempt %d/%d)",
                step.name,
                step.retry_count,
                step.max_retries,
            )
            return

        if policy == "skip":
            step.mark_skipped()
            logger.warning("Skipping failed step %s: %s", step.name, error_msg)
            return

        if policy == "rollback":
            step.mark_failed(error_msg)
            await self._rollback(workflow)
            return

        # Default: stop
        step.mark_failed(error_msg)
        workflow.status = WorkflowStatus.FAILED

    async def _rollback(self, workflow: Workflow) -> None:
        """Execute rollback steps when workflow fails with rollback policy."""
        self._log(workflow.id, "rollback_started", {})
        for step_id in workflow.rollback_steps:
            step = workflow.get_step(step_id)
            if step:
                step.reset()
                try:
                    await self._execute_step(workflow, step)
                except Exception as exc:
                    logger.error(
                        "Rollback step %s failed: %s", step.name, exc
                    )
        self._log(workflow.id, "rollback_completed", {})

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(
        self,
        workflow_id: str,
        event: str,
        data: dict[str, Any],
    ) -> None:
        """Append an entry to the execution log."""
        entry = {
            "workflow_id": workflow_id,
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        self._execution_log.append(entry)
        logger.debug("Workflow %s: %s %s", workflow_id, event, data)
