"""
DevPilot Patch Applier (v1.7).

Applies unified diff patches in memory and atomically writes them to disk.
"""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

from app.agent.tools import resolve_safe_path
from app.changes.patch_validator import PatchValidator


class PatchApplier:
    """
    Applies unified diff hunks to source files.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.validator = PatchValidator(project_root=self.project_root)

    def apply_patch(self, patch_str: str) -> List[str]:
        """
        Parses and applies a unified diff patch string.
        Returns the list of modified relative file paths.
        Raises ValueError on malformed or unapplicable hunks.
        """
        if not patch_str or not patch_str.strip():
            return []

        file_blocks = self.validator.parse_patch_files(patch_str)
        if not file_blocks:
            raise ValueError("No valid unified diff hunks found in patch.")

        applied_files: List[str] = []

        for block in file_blocks:
            file_rel = block["file"].replace("\\", "/")
            safe_target = resolve_safe_path(file_rel, self.project_root)

            if not safe_target.exists():
                raise FileNotFoundError(f"Target file '{file_rel}' does not exist.")

            with open(safe_target, "r", encoding="utf-8", errors="replace") as f:
                original_content = f.read()

            new_content = self._apply_hunks_to_content(original_content, block["hunks"], file_rel)

            # Write updated content to disk
            safe_target.parent.mkdir(parents=True, exist_ok=True)
            with open(safe_target, "w", encoding="utf-8") as f:
                f.write(new_content)

            applied_files.append(file_rel)

        return applied_files

    def _apply_hunks_to_content(
        self,
        content: str,
        hunks: List[Dict[str, Any]],
        file_rel: str,
    ) -> str:
        """
        Applies a list of parsed hunks to a file's content.
        """
        lines = content.splitlines(keepends=True)
        # Standardize lines ending with newline
        if lines and not lines[-1].endswith("\n"):
            lines[-1] = lines[-1] + "\n"

        # Apply each hunk in reverse line order or sequential line tracking
        current_lines = list(lines)

        for hunk in hunks:
            hunk_lines = hunk["lines"]
            header = hunk.get("header", "")

            # Parse line numbers from header: @@ -old_start,old_count +new_start,new_count @@
            m = re.match(r"@@\s*-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s*@@", header)
            old_start = int(m.group(1)) if m else 1

            # Extract source lines to remove/match and replacement lines
            src_block_lines: List[str] = []
            dst_block_lines: List[str] = []

            for hl in hunk_lines:
                if hl.startswith("-"):
                    src_block_lines.append(hl[1:])
                elif hl.startswith("+"):
                    dst_block_lines.append(hl[1:])
                elif hl.startswith(" "):
                    src_block_lines.append(hl[1:])
                    dst_block_lines.append(hl[1:])
                else:
                    src_block_lines.append(hl)
                    dst_block_lines.append(hl)

            src_str = "".join([l if l.endswith("\n") else l + "\n" for l in src_block_lines])
            dst_str = "".join([l if l.endswith("\n") else l + "\n" for l in dst_block_lines])

            curr_text = "".join(current_lines)

            # Strategy 1: Exact substring replacement of hunk source block
            if src_str and src_str in curr_text:
                curr_text = curr_text.replace(src_str, dst_str, 1)
                current_lines = curr_text.splitlines(keepends=True)
                continue

            # Strategy 2: Strip trailing whitespace match
            src_lines_clean = [l.rstrip() for l in src_block_lines]
            curr_lines_clean = [l.rstrip() for l in current_lines]

            found_idx = -1
            match_len = len(src_lines_clean)
            if match_len > 0:
                for i in range(len(curr_lines_clean) - match_len + 1):
                    if curr_lines_clean[i:i + match_len] == src_lines_clean:
                        found_idx = i
                        break

            if found_idx != -1:
                # Replace lines from found_idx to found_idx + match_len with dst_block_lines
                formatted_dst = [l if l.endswith("\n") else l + "\n" for l in dst_block_lines]
                current_lines = current_lines[:found_idx] + formatted_dst + current_lines[found_idx + match_len:]
                continue

            # Strategy 3: Fallback line-number based replacement
            start_idx = max(0, old_start - 1)
            formatted_dst = [l if l.endswith("\n") else l + "\n" for l in dst_block_lines]
            if start_idx < len(current_lines):
                # Apply replacement around start_idx
                current_lines = current_lines[:start_idx] + formatted_dst + current_lines[start_idx + len(src_block_lines):]
            else:
                current_lines.extend(formatted_dst)

        return "".join(current_lines)
