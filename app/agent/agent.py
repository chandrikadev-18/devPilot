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
    get_max_tool_result_characters,
)
from app.llm import strip_thinking_and_tool_tags
from app.llm.base import LLMProvider

DEFAULT_AGENT_SYSTEM_PROMPT = """You are DevPilot, an advanced codebase, Git, and Dependency Graph analysis agent.

You have access to read-only tools to inspect the repository code, Git history, and Dependency Graph.

Available tools include:
- search_code: semantic search across indexed codebase chunks
- read_file: read text contents or specific line ranges of a project file
- find_symbol: locate function, class, or method definitions by name or qualified path
- get_file_structure: inspect AST structure (classes, functions, methods, imports)
- get_file_history: retrieve recent Git commits that modified a specific file
- get_recent_commits: retrieve recent Git commits across the repository
- get_last_commit: retrieve the most recent Git commit modifying a specific file
- get_commit: retrieve detailed metadata and limited diff for a specific commit
- get_file_blame: inspect line-by-line blame, author, commit, and date information
- get_callers: find functions/methods that directly call a specific symbol (e.g. "What functions call X?")
- get_callees: find functions/methods called directly by a specific symbol (e.g. "What functions does X call?")
- get_dependencies: multi-step downstream call dependency traversal for a symbol (e.g. "What does X depend on?")
- get_dependents: multi-step upstream reverse dependency traversal for a symbol (e.g. "What depends on X?")
- get_impact: static impact analysis discovering all callers affected if a symbol changes (e.g. "What could be affected if X changes?")
- get_file_dependencies: inspect module and file import relationships for a file (e.g. "What files does X depend on?")

Rules:
1. Never modify project files. All operations must be strictly read-only.
2. Never execute arbitrary code or shell commands.
3. Never access secrets or files outside project boundaries.
4. Base all explanations strictly on evidence retrieved from tools. Do not invent information. If information is unavailable, explicitly state so.
5. When asked about code relationships, call hierarchy, dependencies, callers, callees, or impact:
   - "What functions does <symbol> call?": use get_callees with symbol="<symbol>".
   - "What functions call <symbol>?": use get_callers with symbol="<symbol>".
   - "What does <symbol> depend on?": use get_dependencies with symbol="<symbol>".
   - "What depends on <symbol>?": use get_dependents with symbol="<symbol>".
   - "What could be affected if <symbol> changes?": use get_impact with symbol="<symbol>".
   - "What files does <file> depend on?" or file imports: use get_file_dependencies with file_path="<file>".
   - Always choose these specialized graph tools directly for relationship/dependency questions rather than searching or finding symbols.
6. When explaining code, functions, methods, or classes (e.g. "Explain <symbol>", "Explain the <symbol> function", "What does <symbol> do?", "How does <symbol> work?"):
   - Step 1: Use find_symbol with symbol_name="<symbol>". This tool returns the exact symbol location (file and line numbers) and the full source code snippet.
   - Step 2: Use the source code snippet returned by find_symbol to synthesize your explanation. You do NOT need to call read_file if find_symbol already returned the code.
   - Step 3 (Optional): If understanding incoming/outgoing calls is helpful, call get_callees or get_callers.
   - Step 4: Synthesize the final explanation immediately. Never call read_file or any other tool repeatedly for the same file or symbol.
   - Provide a well-structured explanation covering:
     * Location (`file_path:line`)
     * Purpose / Overview
     * Signature, Parameters & Return Value
     * Main Responsibilities & Key Execution Steps
     * Important Functions Called (Callees) & Callers (Call Hierarchy)
     * Important Classes / Types Used & Dependencies
     * Side Effects & Error Handling (if visible)
     * Testing Considerations (how to test, mocks, edge cases)
7. When investigating "when" or "why" a function/file changed:
   - Locate the symbol or file using search_code / find_symbol / read_file.
   - Query Git history with get_file_history, get_last_commit, get_file_blame, or get_commit.
   - Base reasons on commit messages and diff evidence. Use phrases like "The commit message indicates..." or "The diff suggests...". Do not invent developer intentions.
8. Clearly distinguish Code sources, Git sources, and Graph sources.
9. Stop when enough evidence has been collected to give a complete, grounded answer. Do not repeat the same tool calls.
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
        executed_tool_calls_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        executed_file_reads: Dict[str, List[Tuple[Optional[int], Optional[int]]]] = {}
        consecutive_duplicate_iterations = 0

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
                cleaned_content = strip_thinking_and_tool_tags(response.content or "")
                assistant_msg: Dict[str, Any] = {
                    "role": "assistant",
                    "content": cleaned_content,
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

                has_new_call = False
                for tc in response.tool_calls:
                    if total_tool_calls_count >= self.max_tool_calls:
                        state.stopped_reason = "max_tool_calls_reached"
                        break

                    args_json = json.dumps(tc.arguments, sort_keys=True) if isinstance(tc.arguments, dict) else str(tc.arguments)
                    call_sig = (tc.name, args_json)
                    is_repeat = call_sig in executed_tool_calls_cache

                    is_redundant_read = False
                    if not is_repeat and tc.name == "read_file" and isinstance(tc.arguments, dict):
                        f_path = tc.arguments.get("file_path", "")
                        s_line = tc.arguments.get("start_line")
                        e_line = tc.arguments.get("end_line")
                        if f_path in executed_file_reads:
                            for prev_s, prev_e in executed_file_reads[f_path]:
                                if prev_s is None and prev_e is None:
                                    is_redundant_read = True
                                    break
                                if s_line is not None and e_line is not None and prev_s is not None and prev_e is not None:
                                    if prev_s <= s_line and prev_e >= e_line:
                                        is_redundant_read = True
                                        break

                    total_tool_calls_count += 1
                    call_record = {
                        "tool": tc.name,
                        "arguments": tc.arguments,
                    }
                    state.tool_calls.append(call_record)

                    if is_repeat:
                        prev_res = executed_tool_calls_cache[call_sig]
                        exec_result = {
                            "success": True,
                            "data": "Duplicate tool call detected. This exact tool call was already executed. Use the previous result instead.",
                            "sources": prev_res.get("sources", []),
                        }
                    elif is_redundant_read:
                        exec_result = {
                            "success": True,
                            "data": f"Duplicate tool call detected. The content of '{tc.arguments.get('file_path')}' is already available in previous tool results in conversation history. Please use the results already present in the conversation history.",
                            "sources": [],
                        }
                    else:
                        has_new_call = True
                        if on_tool_call:
                            on_tool_call(tc.name, tc.arguments)

                        exec_result = self.tool_registry.execute(tc.name, tc.arguments)
                        executed_tool_calls_cache[call_sig] = exec_result

                        if tc.name == "read_file" and isinstance(tc.arguments, dict) and exec_result.get("success"):
                            f_path = tc.arguments.get("file_path", "")
                            if f_path:
                                executed_file_reads.setdefault(f_path, []).append((
                                    tc.arguments.get("start_line"),
                                    tc.arguments.get("end_line")
                                ))

                        if on_tool_result:
                            on_tool_result(tc.name, exec_result)

                    # Track verified sources
                    for src in exec_result.get("sources", []):
                        state.add_source_if_new(src)

                    # Serialize output for LLM message history
                    if exec_result["success"]:
                        result_content = json.dumps(exec_result["data"], indent=2) if not isinstance(exec_result["data"], str) else exec_result["data"]
                    else:
                        result_content = json.dumps({"error": exec_result["error"]})

                    max_chars = get_max_tool_result_characters()
                    if len(result_content) > max_chars:
                        result_content = result_content[:max_chars] + "\n\n[Tool output truncated to max character limit]"

                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": result_content,
                    }
                    state.messages.append(tool_msg)
                    state.tool_results.append(exec_result)

                if not has_new_call:
                    consecutive_duplicate_iterations += 1
                    if consecutive_duplicate_iterations >= 1:
                        state.stopped_reason = "repeated_tool_call"
                        break
                else:
                    consecutive_duplicate_iterations = 0

            else:
                # LLM finished reasoning and returned text answer
                state.final_answer = strip_thinking_and_tool_tags(response.content or "")
                state.stopped_reason = "completed"
                break

        # If loop reached max iterations or stopped without returning final text answer
        if state.final_answer is None or not state.final_answer.strip():
            if state.stopped_reason == "running":
                state.stopped_reason = "max_iterations_reached"

            synthesis_messages = list(state.messages) + [
                {
                    "role": "user",
                    "content": "Please synthesize a clear, comprehensive explanation to the question based on the retrieved code and tool results collected above.",
                }
            ]
            final_res = self.llm.chat(messages=synthesis_messages)
            synthesis_text = strip_thinking_and_tool_tags(final_res.content or "")

            if synthesis_text and synthesis_text.strip():
                state.final_answer = synthesis_text.strip()
            else:
                state.final_answer = self._generate_fallback_explanation(state)

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

    def _generate_fallback_explanation(self, state: AgentState) -> str:
        """Generates a grounded fallback explanation from collected tool results if synthesis returns empty."""
        for res in state.tool_results:
            if not res.get("success"):
                continue
            data = res.get("data")
            if isinstance(data, list) and data:
                first = data[0]
                if isinstance(first, dict) and "symbol_name" in first and "file_path" in first:
                    sym = first["symbol_name"]
                    f_path = first["file_path"]
                    s_line = first.get("start_line", 1)
                    e_line = first.get("end_line", s_line)
                    code = first.get("code", "")
                    return f"## {sym}()\n\n**Location:** `{f_path}:{s_line}-{e_line}`\n\n**Description:**\n{sym} is defined in `{f_path}`.\n\n```python\n{code}\n```"
            elif isinstance(data, dict) and "file_path" in data and "content" in data:
                f_path = data["file_path"]
                content = data["content"]
                return f"## Source Explanation for `{f_path}`\n\n```python\n{content[:2000]}\n```"

        return "Could not retrieve sufficient evidence to explain the requested symbol."
