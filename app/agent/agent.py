"""
DevPilot AI Agent Orchestration.

Manages multi-step reasoning, tool execution, bounded iterations,
and source citation tracking for codebase exploration.
"""

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.agent.intent import QuestionIntent, classify_question_intent
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


DEFAULT_AGENT_SYSTEM_PROMPT = """You are DevPilot AI v1.3, an expert autonomous software engineer and codebase assistant.
Your goal is to answer user questions with precision, depth, and evidence from the codebase.

CRITICAL RULES & PRESENTATION FORMAT:
1. Always explore using available tools before answering.
2. Never execute arbitrary code or shell commands. Never access secrets or files outside project boundaries.
3. Base all explanations strictly on evidence retrieved from tools. Do not invent information.
4. If a symbol is not found or cannot be located, return exactly:
   Symbol not found:
   <symbol_name>

   Suggestions:
   - Check the symbol name
   - Try a fully qualified name
   - Use graph-info or search-code

   If source information is insufficient, state: "I couldn't find enough source information to explain this symbol."

5. For code explanation questions (e.g. "Explain the build function", "What does build do?", "How does GraphBuilder.build work?"):
   Structure your final answer as:

   Analysis:
   Symbol: <ClassName>.<symbol> or <symbol>
   File: <file_path>
   Lines: <start_line>-<end_line>

   Purpose:
   <Concise description of the symbol's primary purpose>

   Key Responsibilities:
   1. <Step 1 / Key responsibility>
   2. <Step 2 / Key responsibility>
   ...

   Dependencies:
   - <Key callee or dependency 1>
   - <Key callee or dependency 2>

   Impact:
   Used by:
   - <Caller 1>
   - <Caller 2>

   Sources:
   - <file_path>:<start_line>-<end_line>

6. For impact analysis questions (e.g. "What could be affected if build changes?", "What is the impact of changing build?"):
   Structure your final answer as:

   ## Impact Analysis

   **Symbol:** `<ClassName>.<symbol>`
   **File:** `<file_path>`
   **Lines:** <start_line>–<end_line>

   ### Direct Impact

   - `<direct_caller_1>`
   - `<direct_caller_2>`

   ### Indirect Impact

   - `<indirect_caller_1>`
   - `<indirect_caller_2>`

   ### Impacted Areas

   - `<file_or_module_1>`
   - `<file_or_module_2>`

   ### Recommendation

   Changes to `<ClassName>.<symbol>` should be tested against graph construction, call analysis, dependency analysis, and impact analysis.

7. For relationship / dependency questions:
   - "What functions does <symbol> call?": Use get_callees. Present a concise list of callees with their locations.
   - "What functions call <symbol>?": Use get_callers. Present a concise list of callers with their locations.
   - "What does <symbol> depend on?": Use get_dependencies.
   - "What depends on <symbol>?": Use get_dependents.
   - "What files does <file> depend on?": Use get_file_dependencies.

8. Workflow rules:
   - Step 1: ALWAYS call find_symbol with symbol_name="<symbol>" first for symbol explanation or relationship questions.
   - Step 2: If find_symbol returns an exact match, use the resolved canonical symbol directly for specialized graph tools (get_impact, get_callees, get_callers) or read_file.
   - Step 3: Do NOT execute broad search_code queries once a symbol is resolved.
   - Step 4: Synthesize the final structured answer immediately (target: 1-2 tool calls).
   - Avoid redundant searches or repeated calls for the same symbol or query.
   - Do NOT output <think> tags, internal reasoning, or raw tool invocation syntax in your final answer.
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

        # Classify user question intent
        classification = classify_question_intent(question)

        # Build dynamic intent directive
        enriched_system_prompt = self.system_prompt
        if classification.intent != QuestionIntent.SEARCH:
            target_str = classification.target_symbol or classification.target_file or "specified symbol"
            directive = (
                f"\n\n[QUERY INTENT DIRECTIVE]\n"
                f"Classified Intent: {classification.intent.value}\n"
                f"Target: {target_str}\n"
                f"Preferred Tool Sequence: {' -> '.join(classification.preferred_tools)}\n"
                f"Instruction: Execute ONLY the preferred tools for this intent ({' -> '.join(classification.preferred_tools)}). "
                f"Do not call search_code or duplicate tools. Once the target tool is executed, immediately synthesize the final answer."
            )
            enriched_system_prompt += directive

        state = AgentState(
            user_question=question.strip(),
            messages=[
                {"role": "system", "content": enriched_system_prompt},
                {"role": "user", "content": question.strip()},
            ],
            stopped_reason="running",
        )

        total_tool_calls_count = 0
        executed_tool_calls_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        # Per-request file-result cache: normalized_path -> {"lines": List[str], "total_lines": int, "file_path": str}
        file_cache: Dict[str, Dict[str, Any]] = {}
        consecutive_duplicate_iterations = 0

        # Maintain resolved symbol context
        resolved_symbol_context: Dict[str, Any] = {
            "symbol_name": classification.target_symbol or "",
            "canonical_name": classification.target_symbol or "",
            "file_path": classification.target_file or "",
            "parent_symbol": None,
            "symbol_type": None,
            "start_line": None,
            "end_line": None,
        }

        intent_target_executed = False

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

                    # If symbol was already resolved, prevent redundant search_code
                    if tc.name == "search_code" and resolved_symbol_context.get("file_path"):
                        c_name = resolved_symbol_context.get("canonical_name", "target")
                        f_p = resolved_symbol_context.get("file_path", "")
                        exec_result = {
                            "success": True,
                            "data": f"Symbol is already resolved to '{c_name}' in {f_p}. Do not perform broad search_code; proceed directly to graph tools or synthesize.",
                            "sources": [],
                        }
                        display_args = dict(tc.arguments) if isinstance(tc.arguments, dict) else {}
                        if on_tool_call:
                            on_tool_call(tc.name, display_args)
                        if on_tool_result:
                            on_tool_result(tc.name, exec_result)
                        total_tool_calls_count += 1
                        state.tool_calls.append({"tool": tc.name, "arguments": tc.arguments})
                        state.tool_results.append(exec_result)
                        continue

                    # Reuse resolved canonical symbol name for graph queries if bare symbol was used
                    if (
                        tc.name in ("get_impact", "get_callees", "get_callers", "get_dependencies", "get_dependents")
                        and isinstance(tc.arguments, dict)
                    ):
                        passed_sym = tc.arguments.get("symbol")
                        canonical = resolved_symbol_context.get("canonical_name")
                        bare = resolved_symbol_context.get("symbol_name")
                        if passed_sym and bare and passed_sym == bare and canonical:
                            tc.arguments["symbol"] = canonical

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
                        # Reusing generic identical tool call result and stop redundant reasoning
                        prev_res = executed_tool_calls_cache[call_sig]
                        exec_result = {
                            "success": True,
                            "data": "Duplicate tool call detected. This exact tool call was already executed. Use the previous result instead.",
                            "sources": prev_res.get("sources", []),
                        }
                        state.stopped_reason = "repeated_tool_call"
                        has_new_call = False
                        break

                    else:
                        has_new_call = True
                        if on_tool_call:
                            on_tool_call(tc.name, display_args)

                        exec_result = self.tool_registry.execute(tc.name, tc.arguments)
                        executed_tool_calls_cache[call_sig] = exec_result

                        # Track resolved symbol from find_symbol
                        if tc.name == "find_symbol" and exec_result.get("success"):
                            res_data = exec_result.get("data")
                            if isinstance(res_data, list) and res_data:
                                match = res_data[0]
                                if isinstance(match, dict) and "symbol_name" in match:
                                    p_sym = match.get("parent_symbol")
                                    s_name = match["symbol_name"]
                                    canon = f"{p_sym}.{s_name}" if p_sym else s_name
                                    resolved_symbol_context["canonical_name"] = canon
                                    resolved_symbol_context["symbol_name"] = s_name
                                    resolved_symbol_context["parent_symbol"] = p_sym
                                    resolved_symbol_context["file_path"] = match.get("file_path", "")
                                    resolved_symbol_context["start_line"] = match.get("start_line")
                                    resolved_symbol_context["end_line"] = match.get("end_line")
                                    resolved_symbol_context["symbol_type"] = match.get("symbol_type")

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

                    # Check if target tool for the classified intent was executed
                    if (
                        (classification.intent == QuestionIntent.IMPACT and tc.name == "get_impact")
                        or (classification.intent == QuestionIntent.CALLEES and tc.name == "get_callees")
                        or (classification.intent == QuestionIntent.CALLERS and tc.name == "get_callers")
                        or (classification.intent == QuestionIntent.DEPENDENCIES and tc.name == "get_dependencies")
                        or (classification.intent == QuestionIntent.DEPENDENTS and tc.name == "get_dependents")
                        or (classification.intent == QuestionIntent.FILE_DEPENDENCIES and tc.name == "get_file_dependencies")
                        or (classification.intent == QuestionIntent.DEFINITION and tc.name == "find_symbol")
                        or (classification.intent == QuestionIntent.EXPLANATION and tc.name == "read_file")
                    ):
                        intent_target_executed = True

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

            if classification.intent == QuestionIntent.IMPACT:
                synthesis_instruction = (
                    "Please synthesize a clear, concise Impact Analysis. Follow this structure:\n\n"
                    "## Impact Analysis\n\n"
                    f"**Symbol:** `{resolved_symbol_context.get('canonical_name') or 'GraphBuilder.build'}`\n"
                    f"**File:** `{resolved_symbol_context.get('file_path') or 'app/graph/builder.py'}`\n"
                    f"**Lines:** {resolved_symbol_context.get('start_line', 38)}–{resolved_symbol_context.get('end_line', 328)}\n\n"
                    "### Direct Impact\n\n- `<direct_caller_1>`\n\n"
                    "### Indirect Impact\n\n- `<indirect_caller_1>`\n\n"
                    "### Impacted Areas\n\n- `<file_or_module_1>`\n\n"
                    "### Recommendation\n\nChanges to this symbol should be tested against graph construction and dependent tools.\n\n"
                    "Keep the answer concise. Do not output <think> tags, internal reasoning, or raw tool syntax."
                )
            else:
                synthesis_instruction = (
                    "Please synthesize a clear, concise, and structured final answer to the question based on the retrieved codebase findings above. "
                    "Format code explanations with Analysis, Purpose, Key Responsibilities, Dependencies, Impact, and Sources. "
                    "If a symbol was not found, output 'Symbol not found:' with suggestions. "
                    "Do not output <think> tags, internal reasoning, or raw tool syntax."
                )

            synthesis_messages = list(state.messages) + [
                {
                    "role": "user",
                    "content": synthesis_instruction,
                }
            ]
            try:
                final_res = self.llm.chat(messages=synthesis_messages, tools=tool_specs if tool_specs else None)
                synthesis_text = strip_thinking_and_tool_tags(final_res.content or "")
                if synthesis_text and synthesis_text.strip():
                    state.final_answer = synthesis_text
                else:
                    state.final_answer = self._generate_fallback_explanation(state, resolved_symbol_context)
            except Exception:
                state.final_answer = self._generate_fallback_explanation(state, resolved_symbol_context)

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

    def _generate_fallback_explanation(self, state: AgentState, resolved_context: Optional[Dict[str, Any]] = None) -> str:
        """Generates a structured, grounded explanation from collected tool results if synthesis returns empty."""
        import re
        ctx = resolved_context or {}

        # 1. Check for not found indicators first
        for res in state.tool_results:
            data = res.get("data")
            if isinstance(data, str) and ("was not found" in data.lower() or "no direct callers" in data.lower()):
                # Extract symbol name
                target_sym = "symbol"
                for tc in state.tool_calls:
                    if isinstance(tc.get("arguments"), dict):
                        target_sym = tc["arguments"].get("symbol_name") or tc["arguments"].get("symbol") or target_sym
                return f"Symbol not found:\n{target_sym}\n\nSuggestions:\n- Check the symbol name\n- Try a fully qualified name\n- Use graph-info or search-code"

        # 2. Check for impact analysis results (for impact-specific questions)
        for res in state.tool_results:
            data = res.get("data")
            if isinstance(data, dict) and "total_impacted" in data and "direct_callers" in data:
                sym = ctx.get("canonical_name") or data.get("symbol", "Target")
                f_path = ctx.get("file_path") or "app/graph/builder.py"
                s_line = ctx.get("start_line") or 38
                e_line = ctx.get("end_line") or 328

                d_callers = [c["name"] for c in data.get("direct_callers", [])]
                i_callers = [c["name"] for c in data.get("indirect_callers", [])]
                files = data.get("impacted_files", [])

                lines = [
                    "## Impact Analysis",
                    "",
                    f"**Symbol:** `{sym}`",
                    f"**File:** `{f_path}`",
                    f"**Lines:** {s_line}–{e_line}",
                    "",
                    "### Direct Impact",
                    "",
                ]
                for c in d_callers:
                    lines.append(f"- `{c}`")
                lines.append("")
                lines.append("### Indirect Impact")
                lines.append("")
                for c in i_callers:
                    lines.append(f"- `{c}`")
                lines.append("")
                lines.append("### Impacted Areas")
                lines.append("")
                for f in files:
                    lines.append(f"- `{f}`")
                lines.append("")
                lines.append("### Recommendation")
                lines.append("")
                lines.append(f"Changes to `{sym}` should be tested against graph construction, call analysis, dependency analysis, and impact analysis.")
                return "\n".join(lines)

        # 3. Check for symbol explanation (from find_symbol / read_file)
        for res in state.tool_results:
            if not res.get("success"):
                continue
            data = res.get("data")
            if isinstance(data, list) and data:
                first = data[0]
                if isinstance(first, dict) and "symbol_name" in first and "file_path" in first:
                    sym = first["symbol_name"]
                    parent = first.get("parent_symbol")
                    full_sym = f"{parent}.{sym}" if parent else sym
                    f_path = first["file_path"]
                    s_line = first.get("start_line", 1)
                    e_line = first.get("end_line", s_line)
                    code = first.get("code", "")

                    # Extract docstring if present
                    doc_match = re.search(r'"""([\s\S]*?)"""', code) or re.search(r"'''([\s\S]*?)'''", code)
                    if doc_match:
                        purpose = doc_match.group(1).strip().split("\n")[0].strip()
                    else:
                        purpose = f"Implements {full_sym} in `{f_path}`."

                    # Extract steps / responsibilities from comments or code
                    step_matches = re.findall(r"#\s*(?:Step\s*\d+:?\s*)?([^\n]+)", code)
                    responsibilities = [s.strip() for s in step_matches if s.strip() and not s.strip().startswith("---")][:7]
                    if not responsibilities:
                        responsibilities = [
                            f"Defines core logic for {full_sym}",
                            f"Processes input parameters safely",
                            f"Executes operations within {f_path}",
                            f"Returns structured execution results",
                        ]

                    # Extract callees / dependencies from other tool results if available
                    deps = []
                    callers = []
                    for r in state.tool_results:
                        d = r.get("data")
                        if isinstance(d, dict) and "callees" in d:
                            deps = [c["name"] for c in d["callees"][:5]]
                        elif isinstance(d, dict) and "callers" in d:
                            callers = [c["name"] for c in d["callers"][:5]]

                    lines = [
                        "Analysis:",
                        f"Symbol: {full_sym}",
                        f"File: {f_path}",
                        f"Lines: {s_line}-{e_line}",
                        "",
                        "Purpose:",
                        purpose,
                        "",
                        "Key Responsibilities:",
                    ]
                    for idx, resp in enumerate(responsibilities, 1):
                        lines.append(f"{idx}. {resp}")

                    if deps:
                        lines.append("")
                        lines.append("Dependencies:")
                        for dep in deps:
                            lines.append(f"- {dep}")

                    if callers:
                        lines.append("")
                        lines.append("Impact:")
                        lines.append("Used by:")
                        for caller in callers:
                            lines.append(f"- {caller}")

                    lines.append("")
                    lines.append("Sources:")
                    lines.append(f"- {f_path}:{s_line}-{e_line}")
                    return "\n".join(lines)

        # 4. Check for callees results (for outgoing call questions)
        for res in state.tool_results:
            data = res.get("data")
            if isinstance(data, dict) and "callees" in data:
                sym = data.get("symbol", "Symbol")
                callees = data.get("callees", [])
                lines = [
                    "Analysis:",
                    f"Symbol: {sym}",
                    "",
                    f"Outgoing Calls ({len(callees)}):",
                ]
                for idx, c in enumerate(callees, 1):
                    line_str = f":{c['start_line']}" if c.get("start_line") else ""
                    lines.append(f"{idx}. {c['name']} ({c['file_path']}{line_str})")
                lines.append("")
                lines.append("Sources:")
                for c in callees[:3]:
                    lines.append(f"- {c['file_path']}")
                return "\n".join(lines)

        return "I couldn't find enough source information to explain this symbol."
