"""
DevPilot Proposal Store.

Provides persistent storage and lookup for change proposals and approval metadata.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import uuid

from app.agent.tools import resolve_safe_path
from app.changes.models import ChangeProposal, ProposalStatus


def compute_file_hash(file_path: Path) -> Optional[str]:
    """Computes SHA256 hex digest of file contents."""
    if not file_path.exists() or not file_path.is_file():
        return None
    try:
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def generate_proposal_id() -> str:
    """Generates unique proposal ID (e.g. prop_20260829_a1b2c3d4)."""
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    rand_part = uuid.uuid4().hex[:8]
    return f"prop_{now_str}_{rand_part}"


class ProposalStore:
    """
    Manages persistent storage of ChangeProposal objects in JSON files under .devpilot/proposals/.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.storage_dir = self.project_root / ".devpilot" / "proposals"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_proposal_file(self, proposal_id: str) -> Path:
        # Sanitize proposal_id to prevent directory traversal
        clean_id = re.sub(r"[^\w\-_]", "", proposal_id)
        return self.storage_dir / f"{clean_id}.json"

    def save(self, proposal: ChangeProposal) -> ChangeProposal:
        """
        Saves or updates a proposal in storage.
        """
        if not proposal.proposal_id:
            proposal.proposal_id = generate_proposal_id()

        now_iso = datetime.now(timezone.utc).isoformat()
        if not proposal.created_at:
            proposal.created_at = now_iso
        proposal.updated_at = now_iso

        # Compute target file hash if available
        if proposal.target_file and not proposal.target_content_hash:
            try:
                full_path = resolve_safe_path(proposal.target_file, self.project_root)
                proposal.target_content_hash = compute_file_hash(full_path)
            except Exception:
                pass

        p_file = self._get_proposal_file(proposal.proposal_id)
        temp_file = p_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(proposal.to_dict(), f, indent=2)
        temp_file.replace(p_file)

        return proposal

    def get(self, proposal_id: str) -> Optional[ChangeProposal]:
        """
        Retrieves proposal by ID, or returns None if not found.
        """
        if not proposal_id:
            return None

        p_file = self._get_proposal_file(proposal_id)
        if not p_file.exists():
            return None

        try:
            with open(p_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            return ChangeProposal(
                request=data.get("request", ""),
                proposal_id=data.get("proposal_id"),
                target_symbol=data.get("target_symbol"),
                target_file=data.get("target_file"),
                target_lines=data.get("target_lines"),
                change_summary=data.get("change_summary", ""),
                affected_files=data.get("affected_files", []),
                affected_symbols=data.get("affected_symbols", []),
                proposed_changes=data.get("proposed_changes", []),
                patch=data.get("patch", ""),
                tests_to_update=data.get("tests_to_update", []),
                tests_to_add=data.get("tests_to_add", []),
                risk=data.get("risk", "LOW"),
                reasoning=data.get("reasoning", ""),
                confidence=data.get("confidence"),
                warnings=data.get("warnings", []),
                unverified_assumptions=data.get("unverified_assumptions", []),
                status=data.get("status", ProposalStatus.PENDING_APPROVAL.value),
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at"),
                approved_at=data.get("approved_at"),
                rejected_at=data.get("rejected_at"),
                applied_at=data.get("applied_at"),
                decision=data.get("decision"),
                decision_reason=data.get("decision_reason"),
                target_content_hash=data.get("target_content_hash"),
            )
        except Exception:
            return None

    def list_proposals(self) -> List[ChangeProposal]:
        """
        Lists all saved change proposals sorted newest first.
        """
        results: List[ChangeProposal] = []
        for p_file in self.storage_dir.glob("*.json"):
            prop = self.get(p_file.stem)
            if prop:
                results.append(prop)

        results.sort(key=lambda p: p.created_at or "", reverse=True)
        return results
