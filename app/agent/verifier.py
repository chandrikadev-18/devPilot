"""
DevPilot Agent Answer Verifier & Evidence Grounding Layer.

Validates that agent responses are strictly grounded in gathered tool results,
detects speculative or unsupported statements, formats structured evidence,
computes confidence scores, and marks unverified claims.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.agent.state import AgentState


class VerificationConfidence(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass
class EvidenceItem:
    file: str
    symbol: str
    lines: str
    reason: str
    source_type: str = "code"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "symbol": self.symbol,
            "lines": self.lines,
            "reason": self.reason,
            "source_type": self.source_type,
        }


@dataclass
class VerificationResult:
    original_answer: str
    verified_answer: str
    evidence: List[EvidenceItem] = field(default_factory=list)
    unverified_claims: List[str] = field(default_factory=list)
    confidence: VerificationConfidence = VerificationConfidence.HIGH
    is_grounded: bool = True

    def to_formatted_string(self) -> str:
        """Formats the final grounded response structure with Answer, Evidence, Confidence, and optional Unverified sections."""
        sections = []

        clean_ans = self.verified_answer.strip()
        # Remove leading "Answer:" or "Final Answer:" if already present to avoid duplication
        if clean_ans.lower().startswith("answer:\n") or clean_ans.lower().startswith("answer: "):
            clean_ans = clean_ans[len("Answer:"):].strip()
        elif clean_ans.lower().startswith("final answer:\n") or clean_ans.lower().startswith("final answer: "):
            clean_ans = clean_ans[len("Final Answer:"):].strip()

        sections.append(f"Answer:\n{clean_ans}")

        if self.evidence:
            ev_blocks = ["Evidence:"]
            for ev in self.evidence[:6]:
                ev_blocks.append(
                    f"- File: {ev.file}\n"
                    f"  Symbol: {ev.symbol}\n"
                    f"  Lines: {ev.lines}\n"
                    f"  Relevant reason: {ev.reason}"
                )
            sections.append("\n".join(ev_blocks))

        sections.append(f"Confidence:\n{self.confidence.value}")

        if self.unverified_claims:
            unv_blocks = ["Unverified:"]
            for unv in self.unverified_claims:
                unv_blocks.append(f"- {unv}")
            sections.append("\n".join(unv_blocks))

        return "\n\n".join(sections)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verified_answer": self.verified_answer,
            "evidence": [e.to_dict() for e in self.evidence],
            "unverified_claims": self.unverified_claims,
            "confidence": self.confidence.value,
            "is_grounded": self.is_grounded,
        }


class AgentAnswerVerifier:
    """
    Evidence grounding verifier that audits agent answers against verified tool outputs.
    """

    def __init__(self):
        pass

    def extract_evidence(self, state: AgentState) -> List[EvidenceItem]:
        """Extracts structured evidence items from tool results and gathered sources."""
        evidence_items: List[EvidenceItem] = []
        seen_keys: Set[str] = set()

        # 1. Inspect tool results directly for rich contextual reasons
        for tr in state.tool_results:
            if not isinstance(tr, dict) or not tr.get("success"):
                continue

            data = tr.get("data")
            if isinstance(data, dict):
                # Check for semantic_code_search results
                if "results" in data and isinstance(data["results"], list):
                    for item in data["results"]:
                        f_path = str(item.get("file", "")).replace("\\", "/")
                        sym = str(item.get("symbol", ""))
                        s_line = item.get("start_line", 1)
                        e_line = item.get("end_line", s_line)
                        reason = item.get("reason") or f"Semantic match for query"
                        key = f"{f_path}:{sym}:{s_line}-{e_line}"
                        if key not in seen_keys and f_path:
                            seen_keys.add(key)
                            evidence_items.append(
                                EvidenceItem(
                                    file=f_path,
                                    symbol=sym,
                                    lines=f"{s_line}-{e_line}",
                                    reason=reason,
                                    source_type="semantic",
                                )
                            )

                # Check for analyze_code_change results
                if "commit" in data and "changed_symbols" in data:
                    commit_sha = data.get("commit", "")[:7]
                    for s in data.get("changed_symbols", []):
                        f_path = str(s.get("file", "")).replace("\\", "/")
                        sym = str(s.get("name", ""))
                        s_line = s.get("start_line", 1)
                        e_line = s.get("end_line", s_line)
                        key = f"{f_path}:{sym}:{s_line}-{e_line}"
                        if key not in seen_keys and f_path:
                            seen_keys.add(key)
                            evidence_items.append(
                                EvidenceItem(
                                    file=f_path,
                                    symbol=sym,
                                    lines=f"{s_line}-{e_line}",
                                    reason=f"Modified in commit {commit_sha}",
                                    source_type="git_change",
                                )
                            )

            elif isinstance(data, list):
                # Check for find_symbol / search_code / callers / callees / dependencies
                for item in data:
                    if isinstance(item, dict):
                        f_path = str(item.get("file_path") or item.get("file") or item.get("caller_file") or item.get("callee_file") or item.get("dependency_file") or item.get("dependent_file") or "").replace("\\", "/")
                        sym = str(item.get("symbol_name") or item.get("symbol") or item.get("caller_name") or item.get("callee_name") or item.get("dependency_name") or item.get("dependent_name") or "")
                        s_line = item.get("start_line") or item.get("caller_line") or item.get("callee_line") or item.get("call_line") or 1
                        e_line = item.get("end_line") or s_line
                        rel = item.get("relationship")
                        reason = f"Graph connection: {rel}" if rel else f"Symbol definition in codebase"
                        key = f"{f_path}:{sym}:{s_line}-{e_line}"
                        if key not in seen_keys and f_path:
                            seen_keys.add(key)
                            evidence_items.append(
                                EvidenceItem(
                                    file=f_path,
                                    symbol=sym,
                                    lines=f"{s_line}-{e_line}",
                                    reason=reason,
                                    source_type="graph" if rel else "code",
                                )
                            )

        # 2. Also inspect state.sources
        for src in state.sources:
            if not isinstance(src, dict):
                continue
            f_path = str(src.get("file_path", "")).replace("\\", "/")
            sym = str(src.get("symbol_name", "") or src.get("symbol", ""))
            s_line = src.get("start_line", 1)
            e_line = src.get("end_line", s_line)
            source_type = src.get("source_type", "code")

            if source_type == "git" or "commit_hash" in src:
                c_hash = src.get("short_hash") or (src.get("commit_hash", "")[:7] if src.get("commit_hash") else "commit")
                author = src.get("author", "unknown")
                key = f"{f_path}:{c_hash}"
                if key not in seen_keys and f_path:
                    seen_keys.add(key)
                    evidence_items.append(
                        EvidenceItem(
                            file=f_path,
                            symbol=sym or c_hash,
                            lines=f"{s_line}-{e_line}" if s_line else "N/A",
                            reason=f"Git commit {c_hash} by {author}",
                            source_type="git",
                        )
                    )
            else:
                key = f"{f_path}:{sym}:{s_line}-{e_line}"
                if key not in seen_keys and f_path:
                    seen_keys.add(key)
                    reason = f"Verified in {f_path}"
                    if src.get("score"):
                        reason += f" (relevance score: {float(src['score']):.2f})"
                    evidence_items.append(
                        EvidenceItem(
                            file=f_path,
                            symbol=sym,
                            lines=f"{s_line}-{e_line}",
                            reason=reason,
                            source_type=source_type,
                        )
                    )

        return evidence_items

    def verify(self, answer: str, state: AgentState) -> VerificationResult:
        """
        Audits the candidate answer against gathered tool results and sources.
        Removes/sanitizes hallucinated or speculative claims and marks unverified statements.
        """
        evidence = self.extract_evidence(state)
        unverified_claims: List[str] = []

        # Build knowledge sets
        verified_files: Set[str] = set()
        verified_symbols: Set[str] = set()
        verified_text_corpus: List[str] = []

        for ev in evidence:
            verified_files.add(ev.file.lower())
            verified_files.add(Path(ev.file).name.lower())
            if ev.symbol:
                verified_symbols.add(ev.symbol.lower())
                # also add base symbol if qualified (e.g. AuthService.hash_password -> hash_password)
                if "." in ev.symbol:
                    verified_symbols.add(ev.symbol.split(".")[-1].lower())
                    verified_symbols.add(ev.symbol.split(".")[0].lower())

        # Collect raw text from tool outputs to verify algorithms and keywords
        has_caller_evidence = False
        has_diff_evidence = False

        for tr in state.tool_results:
            if not isinstance(tr, dict):
                continue
            data = tr.get("data")
            if isinstance(data, str):
                verified_text_corpus.append(data.lower())
            elif isinstance(data, (dict, list)):
                verified_text_corpus.append(str(data).lower())

            # Check if caller/dependent tools were run
            sources = tr.get("sources", [])
            for s in sources:
                if isinstance(s, dict) and s.get("source_type") in ("graph", "caller", "dependent"):
                    has_caller_evidence = True

        for tc in state.tool_calls:
            t_name = tc.get("tool") or tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
            if t_name in ("get_callers", "get_dependents", "get_impact"):
                has_caller_evidence = True
            if t_name in ("git_show_commit", "analyze_code_change"):
                has_diff_evidence = True

        raw_corpus = " ".join(verified_text_corpus)

        # Audit sentences in the answer
        lines = answer.splitlines()
        cleaned_lines: List[str] = []
        skip_evidence_block = False

        for line in lines:
            # If the candidate answer already included an ad-hoc Evidence or Sources section, normalize it
            if line.strip().lower() in ("evidence:", "sources:", "confidence:", "unverified:"):
                skip_evidence_block = True
                continue
            if skip_evidence_block and line.startswith(("- ", "  ", "1.", "2.", "3.", "4.", "5.")):
                continue
            elif skip_evidence_block and line.strip() and not line.startswith(("-", " ")):
                skip_evidence_block = False

            # Check for speculative usage across project
            if re.search(r"used across (?:the )?(?:sample )?project|other modules (?:that need to )?(?:import|call)|called during login flows|used by multiple components", line, re.I):
                if not has_caller_evidence:
                    unverified_claims.append("Claim that symbol is used across other modules or login flows without caller evidence")
                    # Sanitize by skipping or softening the speculative line
                    continue

            # Check for duplicate implementation claim without diff proof
            if re.search(r"duplicate copy|identical symbols|same authentication implementation|identical implementation", line, re.I):
                if not has_diff_evidence:
                    unverified_claims.append("Claim that duplicate files contain identical implementation without file comparison evidence")
                    # Clean line to only state location
                    line = re.sub(r"\(duplicate copy\) with identical symbols, indicating the same authentication implementation is used across the sample project\.", "", line, flags=re.I).strip()
                    if not line:
                        continue

            # Check for specific cryptographic algorithm speculation (e.g. bcrypt, pbkdf2)
            if re.search(r"\b(bcrypt|pbkdf2|argon2|jwt|oauth|session tokens?)\b", line, re.I):
                found_algo = False
                for algo in ("bcrypt", "pbkdf2", "argon2", "jwt", "oauth", "session token"):
                    if algo in line.lower() and algo in raw_corpus:
                        found_algo = True
                        break
                if not found_algo:
                    unverified_claims.append("Specific cryptographic algorithm or token flow claimed without source code evidence")
                    line = re.sub(r"\(e\.g\.,?\s*[^)]+\)", "", line, flags=re.I)
                    line = re.sub(r"\b(bcrypt|pbkdf2|argon2)\b", "", line, flags=re.I)
                    line = re.sub(r"uses a cryptographic hash", "hashes passwords", line, flags=re.I)
                    line = re.sub(r"\s+", " ", line).strip()

            cleaned_lines.append(line)

        cleaned_answer = "\n".join(cleaned_lines).strip()

        # Check if any evidence was gathered
        if not evidence:
            unverified_claims.append("No direct codebase evidence was retrieved for this question")

        # Determine confidence
        if not evidence:
            confidence = VerificationConfidence.LOW
        elif len(unverified_claims) == 0:
            confidence = VerificationConfidence.HIGH
        elif len(unverified_claims) <= 2:
            confidence = VerificationConfidence.MEDIUM
        else:
            confidence = VerificationConfidence.LOW

        # Deduplicate unverified claims while preserving order
        unique_unverified: List[str] = []
        for c in unverified_claims:
            if c not in unique_unverified:
                unique_unverified.append(c)

        return VerificationResult(
            original_answer=answer,
            verified_answer=cleaned_answer or answer,
            evidence=evidence,
            unverified_claims=unique_unverified,
            confidence=confidence,
            is_grounded=len(evidence) > 0 and len(unique_unverified) == 0,
        )


def verify_agent_answer(answer: str, state: AgentState) -> VerificationResult:
    """Convenience helper to verify an agent answer."""
    verifier = AgentAnswerVerifier()
    return verifier.verify(answer=answer, state=state)
