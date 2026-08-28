import os
from pathlib import Path
import tree_sitter_python
from tree_sitter import Language, Parser

class PythonParser:
    def __init__(self):
        self.lang = Language(tree_sitter_python.language())
        self.parser = Parser(self.lang)

    def parse_code(self, source: str | bytes, filepath: str = "snippet.py") -> dict:
        if isinstance(source, str):
            source_bytes = source.encode("utf-8")
        else:
            source_bytes = source

        tree = self.parser.parse(source_bytes)
        
        results = {
            'file': str(filepath),
            'classes': [],
            'functions': [],
            'methods': [],
            'imports': []
        }

        def traverse(node, parent_class=None):
            current_parent_class = parent_class
            
            if node.type == 'class_definition':
                name_node = node.child_by_field_name('name')
                if name_node:
                    name = name_node.text.decode('utf8')
                    results['classes'].append({
                        'name': name,
                        'type': 'class',
                        'start_line': node.start_point[0] + 1,
                        'end_line': node.end_point[0] + 1,
                        'source': node.text.decode('utf8')
                    })
                    current_parent_class = name

            elif node.type == 'function_definition':
                name_node = node.child_by_field_name('name')
                if name_node:
                    name = name_node.text.decode('utf8')
                    if parent_class:
                        results['methods'].append({
                            'name': name,
                            'type': 'method',
                            'parent_class': parent_class,
                            'start_line': node.start_point[0] + 1,
                            'end_line': node.end_point[0] + 1,
                            'source': node.text.decode('utf8')
                        })
                    else:
                        results['functions'].append({
                            'name': name,
                            'type': 'function',
                            'start_line': node.start_point[0] + 1,
                            'end_line': node.end_point[0] + 1,
                            'source': node.text.decode('utf8')
                        })

            elif node.type in ('import_statement', 'import_from_statement'):
                results['imports'].append({
                    'type': 'import',
                    'source': node.text.decode('utf8'),
                    'start_line': node.start_point[0] + 1,
                    'end_line': node.end_point[0] + 1,
                })
            
            for child in node.children:
                traverse(child, current_parent_class)

        traverse(tree.root_node)
        return results

    def parse_file(self, filepath: str | Path) -> dict:
        path = Path(filepath)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        try:
            with open(path, "rb") as f:
                source = f.read()
        except Exception as e:
            return {'error': str(e), 'file': str(path)}

        return self.parse_code(source, str(path))


    def parse_directory(self, directory: str | Path) -> list:
        root_path = Path(directory).resolve()
        if not root_path.is_dir():
            raise NotADirectoryError(f"Directory not found: {root_path}")
            
        parsed_files = []
        for path in root_path.rglob("*.py"):
            # skip virtualenvs in parsing if they happen to be here
            if any(part in {".venv", "venv", "env"} for part in path.parts):
                continue
            parsed_files.append(self.parse_file(path))
            
        return parsed_files
