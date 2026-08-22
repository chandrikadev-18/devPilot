"""
DevPilot AI Agent Orchestration.

Manages multi-step reasoning, tool execution, bounded iterations,
and source citation tracking for codebase exploration.
"""

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.agent.state import AgentResult, AgentState
from app.agent.tool_registry import ToolRegistry
from app.config import (
    get_max_agent_iterations,
    get_max_tool_calls,
    get_max_tool_result_characters,
)
from app.llm import strip_thinking_and_tool_tags
from app.llm.base import LLMProvider


def _normalize_path_key(p: str) -> str:
    """Normalizes a file path for cache lookups."""
    if not p:
        return ""
    norm = p.replace("\\", "/").strip().lower()
    while norm.startswith("./"):
        norm = norm[2:]
    return norm


def _normalize_tool_call_sig(name: str, args: Any) -> Tuple[str, str]:
    """Generates a canonical signature for generic tool deduplication."""
    if isinstance(args, dict):
        norm_dict = {}
        for k, v in sorted(args.items()):
            if k == "_cache":
                continue
            if isinstance(v, str) and ("/" in v or "\\" in v):
                norm_dict[k] = _normalize_path_key(v)
            elif isinstance(v, str):
                norm_dict[k] = v.strip().lower()
            else:
                norm_dict[k] = v
        return (name, json.dumps(norm_dict, sort_keys=True))
    return (name, str(args))


DEFAULT_AGENT_SYSTEM_PROMPT = """You are DevPilot AI v1.2, an expert autonomous software engineer and codebase assistant.
Your goal is to answer user questions with precision, depth, and evidence from the codebase.

CRITICAL RULES:
1. Always explore using available tools before answering.
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
   - Step 1: ALWAYS call find_symbol with symbol_name="<symbol>" first.
   - Step 2: If find_symbol returns an exact unique match, proceed directly with that symbol and its file. Do NOT execute broad search_code queries.
   - Step 3: Inspect the source code by calling read_file ONCE for the file (or using the snippet in find_symbol). Do NOT call read_file repeatedly for the same file.
   - Step 4 (Optional): If understanding caller/callee relationships is needed, call get_callees or get_callers.
   - Step 5: Synthesize a comprehensive final explanation immediately. The entire workflow should take 2-4 tool calls.
   - Provide a well-structured explanation covering:
     * Symbol Name & Location (`file_path:line`)
     * Purpose / Overview
     * Signature, Parameters & Return Value (when visible)
     * Main Execution Steps & Implementation Details
     * Important Functions/Methods Called (Callees) & Callers
     * Classes / Types Used & Dependencies
     * Side Effects & Error Handling (if visible)
     * Testing Considerations (how to test, mocks, edge cases)
7. When investigating "when" or "why" a function/file changed:
   - Locate the symbol or file using find_symbol / read_file.
   - Query Git history with get_file_history, get_last_commit, get_file_blame, or get_commit.
   - Base reasons on commit messages and diff evidence. Use phrases like "The commit message indicates..." or "The diff suggests...". Do not invent developer intentions.
8. Clearly distinguish Code sources, Git sources, and Graph sources.
9. Stop when enough evidence has been collected to give a complete, grounded answer. Avoid redundant tool calls.
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
        # Per-request file-result cache: normalized_path -> {"lines": List[str], "total_lines": int, "file_path": str}
        file_cache: Dict[str, Dict[str, Any]] = {}
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

                    call_sig = _normalize_tool_call_sig(tc.name, tc.arguments)
                    is_repeat_call = call_sig in executed_tool_calls_cache

                    # Check read_file specific caching
                    is_file_cache_hit = False
                    f_path = ""
                    s_line = None
                    e_line = None
                    if tc.name == "read_file" and isinstance(tc.arguments, dict):
                        f_path = tc.arguments.get("file_path", "")
                        norm_p = _normalize_path_key(f_path)
                        s_line = tc.arguments.get("start_line")
                        e_line = tc.arguments.get("end_line")
                        if norm_p in file_cache:
                            is_file_cache_hit = True

                    total_tool_calls_count += 1
                    call_record = {
                        "tool": tc.name,
                        "arguments": tc.arguments,
                    }
                    state.tool_calls.append(call_record)

                    # Prepare display arguments with Cache indicator
                    display_args = dict(tc.arguments) if isinstance(tc.arguments, dict) else {}
                    if tc.name == "read_file":
                        display_args["_cache"] = "HIT" if (is_file_cache_hit or is_repeat_call) else "MISS"

                    if is_file_cache_hit and not is_repeat_call:
                        # Serve from request-scoped file_cache
                        norm_p = _normalize_path_key(f_path)
                        cached_entry = file_cache[norm_p]
                        c_lines = cached_entry["lines"]
                        t_lines = cached_entry["total_lines"]
                        s_idx = max(1, s_line) if s_line is not None else 1
                        e_idx = min(t_lines, e_line) if e_line is not None else t_lines
                        if s_idx > e_idx:
                            s_idx = e_idx
                        sliced_content = "\n".join(c_lines[s_idx - 1 : e_idx])
                        max_chars = get_max_tool_result_characters()
                        truncated = False
                        if len(sliced_content) > max_chars:
                            sliced_content = sliced_content[:max_chars].rstrip() + "\n\n[File truncated due to size limit]"
                            truncated = True

                        exec_result = {
                            "success": True,
                            "data": {
                                "file_path": f_path,
                                "lines": t_lines,
                                "start_line": s_idx,
                                "end_line": e_idx,
                                "truncated": truncated,
                                "content": sliced_content,
                                "cached": True,
                            },
                            "sources": [{
                                "file_path": f_path,
                                "symbol_name": Path(f_path).name,
                                "symbol_type": "file",
                                "start_line": s_idx,
                                "end_line": e_idx,
                            }],
                        }
                        executed_tool_calls_cache[call_sig] = exec_result

                        if on_tool_call:
                            on_tool_call(tc.name, display_args)
                        if on_tool_result:
                            on_tool_result(tc.name, exec_result)

                    elif is_repeat_call:
                        # Reusing generic identical tool call result
                        prev_res = executed_tool_calls_cache[call_sig]
                        exec_result = {
                            "success": True,
                            "data": "Duplicate tool call detected. This exact tool call was already executed. Use the previous result instead.",
                            "sources": prev_res.get("sources", []),
                        }
                        if on_tool_call:
                            on_tool_call(tc.name, display_args)
                        if on_tool_result:
                            on_tool_result(tc.name, exec_result)

                    else:
                        has_new_call = True
                        if on_tool_call:
                            on_tool_call(tc.name, display_args)

                        exec_result = self.tool_registry.execute(tc.name, tc.arguments)
                        executed_tool_calls_cache[call_sig] = exec_result

                        # Populate file_cache on successful read_file
                        if tc.name == "read_file" and isinstance(tc.arguments, dict) and exec_result.get("success"):
                            f_p = tc.arguments.get("file_path", "")
                            norm_p = _normalize_path_key(f_p)
                            res_data = exec_result.get("data", {})
                            if isinstance(res_data, dict) and "content" in res_data:
                                file_cache[norm_p] = {
                                    "lines": res_data["content"].splitlines(),
                                    "total_lines": res_data.get("lines", len(res_data["content"].splitlines())),
                                    "file_path": f_p,
                                }

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
            try:
                final_res = self.llm.chat(messages=synthesis_messages, tools=tool_specs if tool_specs else None)
                synthesis_text = strip_thinking_and_tool_tags(final_res.content or "")
                if synthesis_text and synthesis_text.strip():
                    state.final_answer = synthesis_text
                else:
                    state.final_answer = self._generate_fallback_explanation(state)
            except Exception:
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
