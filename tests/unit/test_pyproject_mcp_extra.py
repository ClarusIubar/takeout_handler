import tomllib
from pathlib import Path

_PYPROJECT_PATH = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"


def _load_pyproject():
    return tomllib.loads(_PYPROJECT_PATH.read_text(encoding="utf-8"))


def test_mcp_is_an_optional_dependency_not_a_hard_dependency():
    data = _load_pyproject()
    project = data["project"]

    # 핵심 파이프라인은 여전히 무의존성이어야 한다 — mcp가 [project.dependencies]에
    # 들어가면 run.py/common/vendors까지 mcp SDK를 강제로 요구하게 되므로 금지.
    hard_deps = project.get("dependencies", [])
    assert not any("mcp" in dep for dep in hard_deps)

    optional = project.get("optional-dependencies", {})
    assert "mcp" in optional
    assert any(dep.lower().startswith("mcp") for dep in optional["mcp"])


def test_mcp_server_package_is_registered():
    data = _load_pyproject()
    packages = data["tool"]["setuptools"]["packages"]
    assert "mcp_server" in packages


def test_requirements_mcp_txt_pins_mcp_sdk():
    req_path = _PYPROJECT_PATH.parent / "requirements-mcp.txt"
    assert req_path.exists()
    content = req_path.read_text(encoding="utf-8")
    assert "mcp" in content.lower()
