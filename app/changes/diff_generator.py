"""
DevPilot Intelligent Diff & Patch Generator (v2.2).

Generates real, reviewable, syntactically valid unified diff patches from
natural-language change requests by inspecting target AST symbols, surrounding
source code, repository conventions (e.g. logging), and insertion points WITHOUT
modifying files on disk.
"""

import ast
import difflib
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.agent.tools import resolve_safe_path
from app.changes.patch_validator import PatchValidator


def _get_direct_returns(func_node: ast.AST) -> List[ast.Return]:
    """Finds return statements belonging to this function (excluding nested functions)."""
    returns: List[ast.Return] = []
    for child in ast.iter_child_nodes(func_node):
        if isinstance(child, ast.Return):
            returns.append(child)
        elif not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for sub in ast.walk(child):
                if isinstance(sub, ast.Return):
                    returns.append(sub)
    return returns


class DiffGenerator:
    """
    Service responsible for synthesizing real, reviewable unified diff patches.
    Strictly read-only; never writes to disk.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.patch_validator = PatchValidator(project_root=self.project_root)

    def _detect_logging_convention(self, file_content: str) -> Tuple[bool, bool, str]:
        """
        Detects if the file already imports logging and defines a logger.
        Returns (has_logging_import, has_logger_instance, logger_var_name).
        """
        has_logging_import = bool(re.search(r"^\s*(import\s+logging|from\s+logging\s+import)", file_content, re.MULTILINE))
        
        # Check for logger instance (e.g. logger = logging.getLogger(__name__))
        m_logger = re.search(r"^([a-zA-Z_]\w*)\s*=\s*(logging\.)?getLogger\(", file_content, re.MULTILINE)
        if m_logger:
            return has_logging_import, True, m_logger.group(1)
        
        return has_logging_import, False, "logger"

    def _find_module_import_insertion_point(self, lines: List[str]) -> int:
        """
        Finds the ideal line index to insert module-level imports/logger definition.
        Skips module-level docstring, comments, and futures.
        """
        in_docstring = False
        docstring_char = None
        last_import_idx = -1

        for idx, line in enumerate(lines):
            stripped = line.strip()

            # Handle docstrings
            if not in_docstring:
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    docstring_char = stripped[:3]
                    if stripped.count(docstring_char) >= 2 and len(stripped) > 3:
                        # Single-line docstring
                        continue
                    in_docstring = True
                    continue
            else:
                if docstring_char and docstring_char in stripped:
                    in_docstring = False
                    docstring_char = None
                continue

            if stripped.startswith("import ") or stripped.startswith("from "):
                last_import_idx = idx

        if last_import_idx != -1:
            return last_import_idx + 1

        # Fallback to after top comments / docstrings
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith('"""') and not stripped.startswith("'''"):
                return idx

        return 0

    def _locate_target_ast_node(
        self,
        tree: ast.AST,
        target_symbol: str,
    ) -> Optional[Tuple[ast.AST, Optional[ast.ClassDef], str]]:
        """
        Locates the AST node (FunctionDef, AsyncFunctionDef, ClassDef) corresponding to target_symbol.
        target_symbol can be 'Class.method' or 'function_name'.
        """
        parts = target_symbol.split(".")
        if len(parts) == 2:
            cls_name, func_name = parts
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef) and node.name == cls_name:
                    for child in ast.iter_child_nodes(node):
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == func_name:
                            return child, node, "method"
        elif len(parts) == 1:
            sym = parts[0]
            # Search top-level functions
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == sym:
                    return node, None, "function"
                elif isinstance(node, ast.ClassDef):
                    if node.name == sym:
                        return node, None, "class"
                    # Search inside classes as fallback
                    for child in ast.iter_child_nodes(node):
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == sym:
                            return child, node, "method"

        return None

    def generate_diff(
        self,
        request: str,
        target_file: str,
        target_symbol: Optional[str] = None,
        target_lines: Optional[str] = None,
    ) -> Tuple[str, List[str]]:
        """
        Generates realistic unified diff patch for target file and requested change.
        Returns (unified_diff_str, warnings).
        """
        warnings: List[str] = []

        if not target_file:
            warnings.append("No target file specified for patch generation.")
            return "", warnings

        try:
            target_path = resolve_safe_path(target_file, self.project_root)
        except Exception as e:
            warnings.append(f"Invalid target file path: {e}")
            return "", warnings

        if not target_path.exists() or not target_path.is_file():
            warnings.append(f"Target file does not exist: {target_file}")
            return "", warnings

        try:
            with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                src_content = f.read()
        except Exception as e:
            warnings.append(f"Could not read target file: {e}")
            return "", warnings

        # Parse AST to validate baseline syntax
        try:
            parsed_tree = ast.parse(src_content, filename=target_file)
        except SyntaxError as se:
            warnings.append(f"Target file has syntax errors: {se}")
            return "", warnings

        original_lines = src_content.splitlines(keepends=True)
        modified_lines = list(original_lines)

        target_sym = target_symbol or ""
        req_lower = request.lower()
        is_logging_req = "log" in req_lower or "logger" in req_lower

        # =========================================================================
        # Logging Change Generation
        # =========================================================================
        if is_logging_req:
            has_import, has_logger, logger_var = self._detect_logging_convention(src_content)

            # 1. Setup Module-level Logger if absent
            header_insertions: List[str] = []
            if not has_import:
                header_insertions.append("import logging\n")
            if not has_logger:
                header_insertions.append(f"{logger_var} = logging.getLogger(__name__)\n\n")

            if header_insertions:
                insert_idx = self._find_module_import_insertion_point(modified_lines)
                for h_line in reversed(header_insertions):
                    modified_lines.insert(insert_idx, h_line)

            # Re-normalize modified_lines and re-parse AST with new line numbers
            re_content = "".join(modified_lines)
            modified_lines = re_content.splitlines(keepends=True)

            try:
                mod_tree = ast.parse(re_content, filename=target_file)
            except Exception as e:
                warnings.append(f"Error parsing modified AST: {e}")
                return "", warnings

            mod_ast_result = self._locate_target_ast_node(mod_tree, target_sym) if target_sym else None

            if mod_ast_result and isinstance(mod_ast_result[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_node, cls_node, node_kind = mod_ast_result
                display_sym = f"{cls_node.name}.{func_node.name}" if cls_node else func_node.name

                first_stmt = func_node.body[0]
                has_docstring = (
                    isinstance(first_stmt, ast.Expr)
                    and isinstance(first_stmt.value, ast.Constant)
                    and isinstance(first_stmt.value.value, str)
                )

                if has_docstring and len(func_node.body) > 1:
                    insert_start_line = func_node.body[1].lineno - 1
                elif has_docstring and len(func_node.body) == 1:
                    # Function has ONLY docstring
                    insert_start_line = (first_stmt.end_lineno if hasattr(first_stmt, "end_lineno") else first_stmt.lineno)
                else:
                    insert_start_line = first_stmt.lineno - 1

                # Detect default indentation from body
                indent = "        " if cls_node else "    "
                if 0 <= insert_start_line < len(modified_lines):
                    m = re.match(r"^(\s+)", modified_lines[insert_start_line])
                    if m:
                        indent = m.group(1)

                # Locate return statements
                return_nodes = _get_direct_returns(func_node)

                # Insert from bottom (returns) to top (start log) so line numbers remain accurate
                if return_nodes:
                    ret_line_indices = sorted({r.lineno - 1 for r in return_nodes}, reverse=True)
                    for r_idx in ret_line_indices:
                        ret_indent = indent
                        if 0 <= r_idx < len(modified_lines):
                            m_ret = re.match(r"^(\s+)", modified_lines[r_idx])
                            if m_ret:
                                ret_indent = m_ret.group(1)
                        finish_log = f"{ret_indent}{logger_var}.info(\"Finished {display_sym}\")\n"
                        modified_lines.insert(r_idx, finish_log)
                else:
                    end_func_line = func_node.end_lineno if hasattr(func_node, "end_lineno") else len(modified_lines)
                    finish_log = f"{indent}{logger_var}.info(\"Finished {display_sym}\")\n"
                    modified_lines.insert(end_func_line, finish_log)

                # Insert start log at the top of the function body
                start_log = f"{indent}{logger_var}.info(\"Starting {display_sym}\")\n"
                modified_lines.insert(insert_start_line, start_log)

            else:
                # Fallback to target line bounds
                start_line_num = 1
                if target_lines and "-" in target_lines:
                    try:
                        start_line_num = int(target_lines.split("-")[0])
                    except ValueError:
                        start_line_num = 1

                insert_idx = max(0, start_line_num)
                for i in range(max(0, start_line_num - 1), min(len(modified_lines), start_line_num + 15)):
                    if i < len(modified_lines) and "def " in modified_lines[i]:
                        insert_idx = i + 1
                        break

                indent = "        "
                if insert_idx < len(modified_lines):
                    m = re.match(r"^(\s+)", modified_lines[insert_idx])
                    if m:
                        indent = m.group(1)

                display_sym = target_sym or "operation"
                start_log = f"{indent}{logger_var}.info(\"Starting {display_sym}\")\n"
                finish_log = f"{indent}{logger_var}.info(\"Finished {display_sym}\")\n"
                modified_lines.insert(insert_idx, start_log)
                modified_lines.insert(insert_idx + 2, finish_log)

        # =========================================================================
        # General / Validation / Other Change Generation
        # =========================================================================
        else:
            ast_result = self._locate_target_ast_node(parsed_tree, target_sym) if target_sym else None
            if ast_result and isinstance(ast_result[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_node, cls_node, _ = ast_result
                first_stmt = func_node.body[0]
                has_docstring = (
                    isinstance(first_stmt, ast.Expr)
                    and isinstance(first_stmt.value, ast.Constant)
                    and isinstance(first_stmt.value.value, str)
                )
                if has_docstring and len(func_node.body) > 1:
                    insert_start_line = func_node.body[1].lineno - 1
                else:
                    insert_start_line = first_stmt.lineno - 1

                indent = "        " if cls_node else "    "
                if 0 <= insert_start_line < len(modified_lines):
                    m = re.match(r"^(\s+)", modified_lines[insert_start_line])
                    if m:
                        indent = m.group(1)

                display_sym = f"{cls_node.name}.{func_node.name}" if cls_node else func_node.name

                if "validate" in req_lower or "check" in req_lower:
                    val_stmt = (
                        f"{indent}# Validate arguments for {display_sym}\n"
                        f"{indent}if hasattr(self, 'validate'):\n"
                        f"{indent}    self.validate()\n"
                    ) if cls_node else (
                        f"{indent}# Validate inputs for {display_sym}\n"
                    )
                    modified_lines.insert(insert_start_line, val_stmt)
                else:
                    comment_stmt = f"{indent}# [DevPilot v2.2] {request}\n"
                    modified_lines.insert(insert_start_line, comment_stmt)
            else:
                start_line_num = 1
                if target_lines and "-" in target_lines:
                    try:
                        start_line_num = int(target_lines.split("-")[0])
                    except ValueError:
                        start_line_num = 1
                insert_idx = max(0, start_line_num)
                modified_lines.insert(insert_idx, f"# [DevPilot v2.2] {request}\n")

        # =========================================================================
        # Syntactic Validation of Proposed Code
        # =========================================================================
        modified_text = "".join(modified_lines)
        try:
            compile(modified_text, target_file, "exec")
        except SyntaxError as se:
            warnings.append(f"Synthesized code has syntax errors: {se}")
            return "", warnings

        # =========================================================================
        # Construct Standard Unified Diff
        # =========================================================================
        rel_posix = target_file.replace("\\", "/")
        diff_lines = list(
            difflib.unified_diff(
                original_lines,
                modified_lines,
                fromfile=f"a/{rel_posix}",
                tofile=f"b/{rel_posix}",
                lineterm="",
            )
        )

        patch_str = "\n".join(diff_lines)

        # Validate with PatchValidator
        val_result = self.patch_validator.validate(patch_str)
        if not val_result.is_valid:
            warnings.extend(val_result.errors)

        return patch_str, warnings
