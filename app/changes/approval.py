"""
DevPilot Change Approval & Human-in-the-Loop Service (v2.2).

Manages review, approval, rejection, staleness detection, and safety enforcement
for change proposals prior to patch application.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.agent.tools import resolve_safe_path
from app.changes.models import ChangeProposal, ProposalStatus
from app.changes.proposal_store import ProposalStore, compute_file_hash


class ApprovalError(Exception):
    """Base error for proposal approval workflow."""
    pass


class ProposalNotFoundError(ApprovalError):
    """Raised when the requested proposal does not exist."""
    pass


class DuplicateApprovalError(ApprovalError):
    """Raised when approving an already-approved proposal."""
    pass


class RejectedProposalError(ApprovalError):
    """Raised when attempting to approve an already-rejected proposal."""
    pass


class AlreadyAppliedError(ApprovalError):
    """Raised when attempting to approve or reject an already-applied proposal."""
    pass


class StaleProposalError(ApprovalError):
    """Raised when the target file or environment changed after proposal creation."""
    pass


class HighRiskConfirmationError(ApprovalError):
    """Raised when HIGH risk changes are approved without explicit confirmation."""
    pass


class ApprovalService:
    """
    Coordinates proposal inspection, human approval, rejection, and pre-application validation.
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        store: Optional[ProposalStore] = None,
    ):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.store = store or ProposalStore(project_root=self.project_root)

    def get_proposal(self, proposal_id: str) -> ChangeProposal:
        """
        Retrieves a proposal by ID.
        Raises ProposalNotFoundError if not found.
        """
        proposal = self.store.get(proposal_id)
        if not proposal:
            raise ProposalNotFoundError(f"Proposal '{proposal_id}' was not found.")
        return proposal

    def approve_proposal(
        self,
        proposal_id: str,
        reason: Optional[str] = None,
        force: bool = False,
    ) -> ChangeProposal:
        """
        Approves a proposal with human confirmation, staleness detection, and state validation.
        """
        proposal = self.get_proposal(proposal_id)

        # 1. State validations
        if proposal.status == ProposalStatus.APPLIED.value:
            raise AlreadyAppliedError(f"Proposal '{proposal_id}' has already been APPLIED.")

        if proposal.status == ProposalStatus.REJECTED.value:
            raise RejectedProposalError(f"Cannot approve proposal '{proposal_id}' because it was REJECTED.")

        if proposal.status == ProposalStatus.APPROVED.value:
            raise DuplicateApprovalError(f"Proposal '{proposal_id}' is already APPROVED.")

        # 2. Target Staleness & Drift Validation
        if proposal.target_file:
            try:
                target_path = resolve_safe_path(proposal.target_file, self.project_root)
            except Exception as e:
                raise StaleProposalError(f"Target file path '{proposal.target_file}' is invalid: {e}")

            if not target_path.exists() or not target_path.is_file():
                raise StaleProposalError(f"Target file '{proposal.target_file}' no longer exists.")

            if proposal.target_content_hash:
                curr_hash = compute_file_hash(target_path)
                if curr_hash != proposal.target_content_hash:
                    raise StaleProposalError(
                        f"Target file '{proposal.target_file}' has been modified since proposal creation. "
                        f"Please generate a fresh proposal."
                    )

        # 3. High Risk Explicit Confirmation Requirement
        if proposal.risk == "HIGH" and not force:
            raise HighRiskConfirmationError(
                f"Proposal '{proposal_id}' has HIGH risk. "
                f"Explicit confirmation (--force) is required for approval."
            )

        # 4. Transition State
        proposal.status = ProposalStatus.APPROVED.value
        proposal.approved_at = datetime.now(timezone.utc).isoformat()
        proposal.decision = "approved"
        proposal.decision_reason = reason or "Approved by developer"

        self.store.save(proposal)
        return proposal

    def reject_proposal(
        self,
        proposal_id: str,
        reason: Optional[str] = None,
    ) -> ChangeProposal:
        """
        Rejects a proposal and records developer decision.
        """
        proposal = self.get_proposal(proposal_id)

        if proposal.status == ProposalStatus.APPLIED.value:
            raise AlreadyAppliedError(f"Cannot reject proposal '{proposal_id}' because it is already APPLIED.")

        proposal.status = ProposalStatus.REJECTED.value
        proposal.rejected_at = datetime.now(timezone.utc).isoformat()
        proposal.decision = "rejected"
        proposal.decision_reason = reason or "Rejected by developer"

        self.store.save(proposal)
        return proposal
