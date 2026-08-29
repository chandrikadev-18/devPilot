"""
DevPilot Change Proposal Module (v2.1).

Exports ChangeProposal dataclass and ChangeProposalGenerator service.
"""

from app.changes.diff_generator import DiffGenerator
from app.changes.models import ChangeProposal
from app.changes.proposal_generator import ChangeProposalGenerator

__all__ = [
    "ChangeProposal",
    "ChangeProposalGenerator",
    "DiffGenerator",
]
