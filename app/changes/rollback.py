"""
DevPilot Checkpoint & Rollback Manager (v1.7).

Provides localized, isolated backup checkpoints for DevPilot patch applications.
Reverts ONLY DevPilot-modified files without resetting or destroying unrelated Git changes.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agent.tools import resolve_safe_path
from app.changes.models import RollbackResult


class RollbackManager:
    """
    Manages pre-apply file backups and atomic rollback operations.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.checkpoints_dir = self.project_root / "data" / "checkpoints"

    def _ensure_dir(self) -> Path:
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        return self.checkpoints_dir

    def create_checkpoint(self, files: List[str]) -> str:
        """
        Captures pre-modification snapshots of the specified files.
        Returns the unique checkpoint identifier.
        """
        self._ensure_dir()
        now_utc = datetime.now(timezone.utc)
        ts = now_utc.strftime("%Y%m%d_%H%M%S_%f")
        checkpoint_id = f"checkpoint_{ts}"

        snapshots: Dict[str, Optional[str]] = {}
        for f_rel in files:
            norm_rel = f_rel.replace("\\", "/")
            try:
                safe_target = resolve_safe_path(norm_rel, self.project_root)
                if safe_target.exists() and safe_target.is_file():
                    with open(safe_target, "r", encoding="utf-8", errors="replace") as f:
                        snapshots[norm_rel] = f.read()
                else:
                    # File did not exist before (was created by patch)
                    snapshots[norm_rel] = None
            except Exception:
                snapshots[norm_rel] = None

        data = {
            "checkpoint_id": checkpoint_id,
            "created_at": now_utc.isoformat(),
            "files": list(snapshots.keys()),
            "snapshots": snapshots,
        }

        # Save checkpoint file
        cp_file = self.checkpoints_dir / f"{checkpoint_id}.json"
        with open(cp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # Update latest pointer
        latest_file = self.checkpoints_dir / "latest.json"
        with open(latest_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return checkpoint_id

    def has_checkpoint(self) -> bool:
        """Checks if a valid rollback checkpoint is available."""
        latest_file = self.checkpoints_dir / "latest.json"
        return latest_file.exists() and latest_file.is_file()

    def get_latest_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Retrieves the latest checkpoint metadata."""
        latest_file = self.checkpoints_dir / "latest.json"
        if not latest_file.exists():
            return None
        try:
            with open(latest_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def restore_checkpoint(self, checkpoint_id: Optional[str] = None) -> RollbackResult:
        """
        Restores only the files captured in the checkpoint.
        Unrelated working tree changes are preserved untouched.
        """
        if not self.has_checkpoint() and checkpoint_id is None:
            return RollbackResult(
                status="no_checkpoint",
                reverted_files=[],
                checkpoint_id=None,
                message="No rollback checkpoint found.",
            )

        if checkpoint_id:
            cp_file = self.checkpoints_dir / f"{checkpoint_id}.json"
        else:
            cp_file = self.checkpoints_dir / "latest.json"

        if not cp_file.exists():
            return RollbackResult(
                status="no_checkpoint",
                reverted_files=[],
                checkpoint_id=checkpoint_id,
                message=f"Checkpoint '{checkpoint_id}' not found.",
            )

        try:
            with open(cp_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return RollbackResult(
                status="failed",
                reverted_files=[],
                checkpoint_id=checkpoint_id,
                message=f"Error reading checkpoint: {str(e)}",
            )

        cid = data.get("checkpoint_id", checkpoint_id or "unknown")
        snapshots: Dict[str, Optional[str]] = data.get("snapshots", {})
        reverted_files: List[str] = []

        for f_rel, original_content in snapshots.items():
            try:
                safe_target = resolve_safe_path(f_rel, self.project_root)
                if original_content is None:
                    # File was newly created by patch; delete it
                    if safe_target.exists():
                        safe_target.unlink()
                    reverted_files.append(f_rel)
                else:
                    # Restore original content
                    safe_target.parent.mkdir(parents=True, exist_ok=True)
                    with open(safe_target, "w", encoding="utf-8") as f:
                        f.write(original_content)
                    reverted_files.append(f_rel)
            except Exception as e:
                pass

        # Cleanup latest pointer once restored
        latest_file = self.checkpoints_dir / "latest.json"
        if latest_file.exists():
            try:
                latest_file.unlink()
            except Exception:
                pass

        return RollbackResult(
            status="success",
            reverted_files=reverted_files,
            checkpoint_id=cid,
            message=f"Successfully restored {len(reverted_files)} file(s) from checkpoint '{cid}'.",
        )
