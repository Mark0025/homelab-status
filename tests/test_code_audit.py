"""#13: code_audit reads the REAL code (deps + routes), not commit metadata."""

from homelab_status import project_intel as pi


def test_parse_python_deps_only_real_packages_not_toml_keys():
    pyproject = '''
[project]
name = "myapp"
version = "0.1.0"
dependencies = [
    "fastapi>=0.111.0",
    "httpx>=0.27.0",
    "loguru>=0.7.2",
]
[tool.pytest.ini_options]
addopts = "-q"
'''
    deps = pi._parse_python_deps(pyproject)
    assert "fastapi" in deps and "httpx" in deps and "loguru" in deps
    # the bug we fixed: TOML keys must NOT appear as deps
    assert "addopts" not in deps
    assert "name" not in deps and "version" not in deps and "dependencies" not in deps


def test_parse_requirements_txt():
    deps = pi._parse_python_deps("fastapi==0.111\nhttpx>=0.27\n# comment\n-e .\n")
    assert "fastapi" in deps and "httpx" in deps


def test_parse_npm_deps():
    pkg = '{"dependencies":{"next":"15","react":"19"},"devDependencies":{"vitest":"2"}}'
    assert pi._parse_npm_deps(pkg) == ["next", "react", "vitest"]


def test_extract_routes_fastapi_and_express():
    src = '''
@api.get("/api/status")
@router.post("/users")
app.get('/health')
router.delete('/items/:id')
'''
    routes = pi._extract_routes_from_source(src)
    assert "GET /api/status" in routes
    assert "POST /users" in routes
    assert "GET /health" in routes
    assert "DELETE /items/:id" in routes
