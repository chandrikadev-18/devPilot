"""
DevPilot AST Relationship Extractor.

Extracts classes, functions, methods, imports, and function/method call sites
from Python source files using Tree-sitter AST traversal.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import tree_sitter_python
from tree_sitter import Language, Parser


@dataclass
class CallSite:
    """Represents a call invocation identified in AST."""
    caller_name: str
    caller_type: str  # 'function' or 'method'
    parent_class: Optional[str]
    callee_name: str
    receiver: Optional[str]  # e.g., 'self', 'service', 'os.path'
    call_type: str  # 'direct', 'self_method', 'attribute'
    line_number: int


@dataclass
class ImportRecord:
    """Represents an import statement in AST."""
    import_type: str  # 'module' or 'from'
    module_name: str  # e.g., 'os', '.auth', 'backend.auth'
    imported_names: List[str] = field(default_factory=list)  # symbols imported
    aliases: Dict[str, str] = field(default_factory=dict)  # name -> alias
    line_number: int = 1
    raw_source: str = ""


@dataclass
class ParsedFileRelationships:
    """Aggregated structural and call-site relationships for a single file."""
    file_path: str
    classes: List[Dict[str, Any]] = field(default_factory=list)
    functions: List[Dict[str, Any]] = field(default_factory=list)
    methods: List[Dict[str, Any]] = field(default_factory=list)
    imports: List[ImportRecord] = field(default_factory=list)
    calls: List[CallSite] = field(default_factory=list)


class ASTExtractor:
    """
    Parses Python source code with Tree-sitter to extract definitions,
    imports, and call sites without executing code.
    """

    def __init__(self):
        self.lang = Language(tree_sitter_python.language())
        self.parser = Parser(self.lang)

    def extract_file(self, file_path: str | Path, source_code: Optional[str] = None) -> ParsedFileRelationships:
        """Extracts AST entities and relationships from a file path or provided string."""
        path = Path(file_path)
        if source_code is None:
            if not path.is_file():
                raise FileNotFoundError(f"File not found: {path}")
            with open(path, "rb") as f:
                source_bytes = f.read()
        else:
            source_bytes = source_code.encode("utf-8")

        tree = self.parser.parse(source_bytes)
        result = ParsedFileRelationships(file_path=path.as_posix())

        def _extract_imports(node) -> Optional[ImportRecord]:
            line = node.start_point[0] + 1
            raw = node.text.decode("utf-8", errors="replace")

            if node.type == "import_statement":
                # e.g. import os, sys
                # or import numpy as np
                module_names = []
                aliases = {}
                for child in node.children:
                    if child.type == "dotted_name":
                        module_names.append(child.text.decode("utf-8"))
                    elif child.type == "aliased_import":
                        name_n = child.child_by_field_name("name")
                        alias_n = child.child_by_field_name("alias")
                        if name_n:
                            n_str = name_n.text.decode("utf-8")
                            module_names.append(n_str)
                            if alias_n:
                                aliases[n_str] = alias_n.text.decode("utf-8")
                mod_main = module_names[0] if module_names else raw.replace("import", "").strip()
                return ImportRecord(
                    import_type="module",
                    module_name=mod_main,
                    imported_names=module_names,
                    aliases=aliases,
                    line_number=line,
                    raw_source=raw,
                )

            elif node.type == "import_from_statement":
                # e.g. from .auth import login_user, AuthService
                # or from math import sqrt as s
                module_node = node.child_by_field_name("module_name")
                # Handle relative dot imports like from . import X or from .auth import X
                mod_name = ""
                if module_node:
                    mod_name = module_node.text.decode("utf-8")
                else:
                    # check for relative dots before module_name
                    raw_parts = raw.split()
                    if len(raw_parts) >= 2 and raw_parts[0] == "from":
                        mod_name = raw_parts[1]

                imported_names = []
                aliases = {}
                for child in node.children:
                    if child.type == "dotted_name":
                        # Skip if it's the module name itself
                        if module_node and child.id == module_node.id:
                            continue
                        imported_names.append(child.text.decode("utf-8"))
                    elif child.type == "identifier":
                        # names imported
                        if module_node and child.id == module_node.id:
                            continue
                        text = child.text.decode("utf-8")
                        if text not in ("from", "import", mod_name):
                            imported_names.append(text)
                    elif child.type == "aliased_import":
                        name_n = child.child_by_field_name("name")
                        alias_n = child.child_by_field_name("alias")
                        if name_n:
                            n_str = name_n.text.decode("utf-8")
                            imported_names.append(n_str)
                            if alias_n:
                                aliases[n_str] = alias_n.text.decode("utf-8")

                return ImportRecord(
                    import_type="from",
                    module_name=mod_name,
                    imported_names=imported_names,
                    aliases=aliases,
                    line_number=line,
                    raw_source=raw,
                )

            return None

        def _extract_calls_in_scope(scope_node, caller_name: str, caller_type: str, parent_class: Optional[str]):
            """Recursively finds all call nodes within a function/method definition."""
            stack = [scope_node]
            while stack:
                curr = stack.pop()
                # If we encounter a nested function definition, skip it here so it gets its own scope
                if curr.id != scope_node.id and curr.type in ("function_definition", "class_definition"):
                    continue

                if curr.type == "call":
                    func_n = curr.child_by_field_name("function")
                    line_no = curr.start_point[0] + 1
                    if func_n:
                        if func_n.type == "identifier":
                            callee = func_n.text.decode("utf-8")
                            result.calls.append(
                                CallSite(
                                    caller_name=caller_name,
                                    caller_type=caller_type,
                                    parent_class=parent_class,
                                    callee_name=callee,
                                    receiver=None,
                                    call_type="direct",
                                    line_number=line_no,
                                )
                            )
                        elif func_n.type == "attribute":
                            obj_n = func_n.child_by_field_name("object")
                            attr_n = func_n.child_by_field_name("attribute")
                            if attr_n:
                                callee = attr_n.text.decode("utf-8")
                                obj_text = obj_n.text.decode("utf-8") if obj_n else None
                                c_type = "self_method" if obj_text == "self" else "attribute"
                                result.calls.append(
                                    CallSite(
                                        caller_name=caller_name,
                                        caller_type=caller_type,
                                        parent_class=parent_class,
                                        callee_name=callee,
                                        receiver=obj_text,
                                        call_type=c_type,
                                        line_number=line_no,
                                    )
                                )

                stack.extend(curr.children)

        def _traverse(node, current_class=None):
            if node.type == "class_definition":
                name_n = node.child_by_field_name("name")
                if name_n:
                    c_name = name_n.text.decode("utf-8")
                    result.classes.append({
                        "name": c_name,
                        "type": "class",
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                        "source": node.text.decode("utf-8", errors="replace"),
                    })
                    for child in node.children:
                        _traverse(child, current_class=c_name)
                    return

            elif node.type == "function_definition":
                name_n = node.child_by_field_name("name")
                if name_n:
                    f_name = name_n.text.decode("utf-8")
                    start_l = node.start_point[0] + 1
                    end_l = node.end_point[0] + 1
                    src = node.text.decode("utf-8", errors="replace")

                    if current_class:
                        result.methods.append({
                            "name": f_name,
                            "type": "method",
                            "parent_class": current_class,
                            "start_line": start_l,
                            "end_line": end_l,
                            "source": src,
                        })
                        _extract_calls_in_scope(node, caller_name=f_name, caller_type="method", parent_class=current_class)
                    else:
                        result.functions.append({
                            "name": f_name,
                            "type": "function",
                            "start_line": start_l,
                            "end_line": end_l,
                            "source": src,
                        })
                        _extract_calls_in_scope(node, caller_name=f_name, caller_type="function", parent_class=None)

            elif node.type in ("import_statement", "import_from_statement"):
                imp_rec = _extract_imports(node)
                if imp_rec:
                    result.imports.append(imp_rec)

            for child in node.children:
                _traverse(child, current_class=current_class)

        _traverse(tree.root_node)
        return result
