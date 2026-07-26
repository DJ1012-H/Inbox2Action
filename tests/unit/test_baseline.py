import tomllib
from pathlib import Path


def test_project_baseline_declares_supported_python_and_no_forbidden_runtime_dependency() -> (
    None
):
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]

    assert project["requires-python"] == ">=3.12"
    assert not {"langgraph", "fastapi", "sqlalchemy"}.intersection(
        project["dependencies"]
    )
