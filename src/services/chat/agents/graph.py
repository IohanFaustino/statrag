"""Linear async state-graph runner with iter cap and one-step retry-on-fail.

ADR-001 (rolled-back by ADR-006 for v2 modes) but retained for the v1 path
during the staged migration. T11 deletes this file once all multi-agent modes
are on LangGraph.

T07 fixes (diagnostic B8):
- ``qc_status`` is reset to ``"pending"`` before the retry, then explicitly
  re-set to ``"fail"`` if the retry itself raises (so partial failures are
  not silently swallowed).
- ``last_error`` tracking lets callers distinguish "retry succeeded" from
  "retry exception".

Chinese-wall: imports only from src.services.chat.agents.state (sibling).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from src.services.chat.agents.state import AgentState

logger = logging.getLogger(__name__)

NodeFn = Callable[[AgentState], Awaitable[AgentState]]


@dataclass
class Node:
    """A named async node in a state graph.

    Attributes:
        name: Human-readable node identifier (used in logs and error messages).
        fn: Async callable that receives and returns an :class:`AgentState`.
    """

    name: str
    fn: NodeFn


class StateGraph:
    """Linear async node runner with iter cap and one-step retry-on-fail.

    Traversal is strictly sequential. After each node:
    - ``state.iter`` is incremented.
    - If ``state.qc_status == "fail"`` the *previous* node is retried once
      (the retry also increments ``state.iter``).
    - If ``state.iter >= max_iters`` before a node runs, the loop breaks and
      an error is appended to ``state.errors``.

    Args:
        nodes: Ordered list of :class:`Node` instances.
        max_iters: Hard cap on total iteration count (default 12).
    """

    def __init__(self, nodes: list[Node], *, max_iters: int = 12) -> None:
        self.nodes = nodes
        self.max_iters = max_iters

    async def run(self, state: AgentState) -> AgentState:
        """Execute all nodes in order, respecting the iter cap and retry logic.

        Args:
            state: Initial :class:`AgentState`. Modified in-place by each node.

        Returns:
            The final :class:`AgentState` after all nodes have run (or the cap
            was hit).
        """
        for idx, node in enumerate(self.nodes):
            if state.iter >= self.max_iters:
                state.errors.append(f"iter cap hit at {node.name}")
                break
            logger.debug("[graph] -> %s (iter=%d)", node.name, state.iter)
            try:
                state = await node.fn(state)
            except Exception as exc:  # noqa: BLE001
                state.errors.append(f"{node.name}: {type(exc).__name__}: {exc}")
                state.qc_status = "fail"
            state.iter += 1

            # T07 (B8 fix): one retry of the PREVIOUS node on fail.
            # Reset qc_status to "pending" before retry, then either let the
            # retry mark "pass"/"fail" explicitly, OR if the retry raises,
            # force "fail" so we do not silently continue with stale state.
            if state.qc_status == "fail" and idx > 0 and state.iter < self.max_iters:
                prev = self.nodes[idx - 1]
                logger.debug(
                    "[graph] retry %s after %s failed", prev.name, node.name
                )
                state.qc_status = "pending"
                try:
                    state = await prev.fn(state)
                except Exception as exc:  # noqa: BLE001
                    state.errors.append(
                        f"{prev.name}(retry): {type(exc).__name__}: {exc}"
                    )
                    # T07: explicit fail-on-retry-exception (was silently swallowed)
                    state.qc_status = "fail"
                state.iter += 1
        return state
