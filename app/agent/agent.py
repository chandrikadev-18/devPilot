"""
DevPilot AI Agent Orchestration.

Manages multi-step reasoning, tool execution, bounded iterations,
and source citation tracking for codebase exploration.
"""

import json
import time
from typing import Any, Callable, Dict, List, Optional

from app.agent.state import AgentResult, AgentState
from app.agent.tool_registry import ToolRegistry
from app.config import (
    get_max_agent_iterations,
    get_max_tool_calls,
)
from app.llm.base import LLMProvider

DEFAULT_AGENT_SYSTEM_PROMPT = """You are DevPilot, a codebase analysis agent.

You have access to read-only tools to inspect the repository.

Use tools when necessary to answer the user's question.

Rules:
1. Never modify project files.
2. Never execute code.
3. Never execute shell commands.
4. Never access secrets.
5. Never invent code or files.
6. Use retrieved evidence.
7. If evidence is insufficient, say so.
8. Prefer search_code before reading large files.
9. Use read_file only when additional context is needed.
10. Cite files and symbols in the final answer.
11. Stop when enough evidence has been collected.
12. Do not call tools unnecessarily.
"""


class CodebaseAgent:
    """
    Autonomous read-only agent that reasons over user questions,
    dispatches tools, inspects codebase findings, and synthesizes answers.
    """

    def __init__(
        self,
        llm: LLMProvider,
        tool_registry: ToolRegistry,
        system_prompt: Optional[str] = None,
        max_iterations: Optional[int] = None,
        max_tool_calls: Optional[int] = None,
    ):
        self.llm = llm
        self.tool_registry = tool_registry
        self.system_prompt = system_prompt or DEFAULT_AGENT_SYSTEM_PROMPT
        self.max_iterations = max_iterations if max_iterations is not None else get_max_agent_iterations()
        self.max_tool_calls = max_tool_calls if max_tool_calls is not None else get_max_tool_calls()

    def run(
        self,
        question: str,
        on_iteration_start: Optional[Callable[[int], None]] = None,
        on_tool_call: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_tool_result: Optional[Callable[[str, Any], None]] = None,
    ) -> AgentResult:
        """
        Executes the bounded agent reasoning loop for the given question.
        """
        if not question or not question.strip():
            raise ValueError("Question cannot be empty.")

        t_start = time.time()
        tool_specs = self.tool_registry.get_tool_specs()

        state = AgentState(
            user_question=question.strip(),
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": question.strip()},
            ],
            stopped_reason="running",
        )

        total_tool_calls_count = 0

        for iteration in range(1, self.max_iterations + 1):
            state.iteration_count = iteration
            if on_iteration_start:
                on_iteration_start(iteration)

            if total_tool_calls_count >= self.max_tool_calls:
                state.stopped_reason = "max_tool_calls_reached"
                break

            response = self.llm.chat(
                messages=state.messages,
                tools=tool_specs if tool_specs else None,
            )

            # If LLM returned tool calls
            if response.has_tool_calls:
                assistant_msg: Dict[str, Any] = {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else str(tc.arguments),
                            },
                        }
                        for tc in response.tool_calls
                    ],
                }
                state.messages.append(assistant_msg)

                for tc in response.tool_calls:
                    if total_tool_calls_count >= self.max_tool_calls:
                        state.stopped_reason = "max_tool_calls_reached"
                        break

                    total_tool_calls_count += 1
                    call_record = {
                        "tool": tc.name,
                        "arguments": tc.arguments,
                    }
                    state.tool_calls.append(call_record)

                    if on_tool_call:
                        on_tool_call(tc.name, tc.arguments)

                    # Execute tool safely
                    exec_result = self.tool_registry.execute(tc.name, tc.arguments)

                    if on_tool_result:
                        on_tool_result(tc.name, exec_result)

                    # Track verified sources
                    for src in exec_result.get("sources", []):
                        state.add_source_if_new(src)

                    # Serialize output for LLM message history
                    if exec_result["success"]:
                        result_content = json.dumps(exec_result["data"], indent=2)
                    else:
                        result_content = json.dumps({"error": exec_result["error"]})

                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": result_content,
                    }
                    state.messages.append(tool_msg)
                    state.tool_results.append(exec_result)

            else:
                # LLM finished reasoning and returned text answer
                state.final_answer = response.content or ""
                state.stopped_reason = "completed"
                break

        # If loop reached max iterations without returning final text answer
        if state.final_answer is None:
            if state.stopped_reason == "running":
                state.stopped_reason = "max_iterations_reached"

            synthesis_messages = list(state.messages) + [
                {
                    "role": "user",
                    "content": "Please synthesize your final answer to the question using all retrieved evidence collected so far.",
                }
            ]
            final_res = self.llm.chat(messages=synthesis_messages)
            state.final_answer = final_res.content or "Could not complete synthesis within execution limits."

        total_time = time.time() - t_start

        return AgentResult(
            question=state.user_question,
            answer=state.final_answer.strip(),
            sources=state.sources,
            tool_calls=state.tool_calls,
            iterations=state.iteration_count,
            provider=self.llm.provider_name,
            model=self.llm.model_name,
            timing={"total": total_time},
            stopped_reason=state.stopped_reason,
        )
