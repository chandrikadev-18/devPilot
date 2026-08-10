import pytest
from pathlib import Path
from app.parser.python_parser import PythonParser

@pytest.fixture
def parser():
    return PythonParser()

@pytest.fixture
def sample_dir():
    return Path(__file__).parent.parent / "sample_project"

def test_parse_auth_file(parser, sample_dir):
    auth_file = sample_dir / "auth.py"
    result = parser.parse_file(auth_file)
    
    assert result['file'] == str(auth_file)
    
    # Check imports
    imports = [imp['source'] for imp in result['imports']]
    assert "import hashlib" in imports
    assert "import os" in imports
    
    # Check classes
    classes = [c['name'] for c in result['classes']]
    assert "AuthService" in classes
    
    # Check methods
    methods = [m['name'] for m in result['methods']]
    assert "__init__" in methods
    assert "hash_password" in methods
    assert "verify_password" in methods
    
    # Check parent class of methods
    for m in result['methods']:
        assert m['parent_class'] == "AuthService"
        
    # Check functions
    functions = [f['name'] for f in result['functions']]
    assert "login_user" in functions

def test_parse_directory(parser, sample_dir):
    results = parser.parse_directory(sample_dir)
    assert len(results) == 3 # auth.py, users.py, utils.py
    
    parsed_files = [Path(r['file']).name for r in results]
    assert "auth.py" in parsed_files
    assert "users.py" in parsed_files
    assert "utils.py" in parsed_files
