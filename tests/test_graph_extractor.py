"""
Tests for AST Relationship Extractor.
"""

from app.graph.extractor import ASTExtractor


def test_extractor_classes_and_methods():
    source = """
import os
from .utils import helper

class AuthService:
    def __init__(self, key):
        self.key = key

    def login(self, username, password):
        hashed = self.hash_password(password)
        return helper(username, hashed)

    def hash_password(self, password):
        return os.urandom(16)

def standalone_func():
    service = AuthService("key")
    return service.login("admin", "secret")
"""
    extractor = ASTExtractor()
    parsed = extractor.extract_file("test_auth.py", source_code=source)

    # Verify classes
    assert len(parsed.classes) == 1
    assert parsed.classes[0]["name"] == "AuthService"

    # Verify methods
    method_names = [m["name"] for m in parsed.methods]
    assert "login" in method_names
    assert "hash_password" in method_names

    # Verify functions
    func_names = [f["name"] for f in parsed.functions]
    assert "standalone_func" in func_names

    # Verify imports
    import_mods = [imp.module_name for imp in parsed.imports]
    assert "os" in import_mods
    assert ".utils" in import_mods or "utils" in import_mods

    # Verify call extraction
    call_callees = [(c.caller_name, c.callee_name, c.call_type) for c in parsed.calls]
    assert ("login", "hash_password", "self_method") in call_callees
    assert ("login", "helper", "direct") in call_callees
