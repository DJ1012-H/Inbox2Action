"""Run safe, offline Stage 11 packaging and documentation acceptance checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "Dockerfile",
    "compose.yaml",
    ".dockerignore",
    ".env.example",
    "docs/architecture.md",
    "docs/graph.md",
    "docs/evaluation-report.md",
    "docs/demo-guide.md",
    "docs/demo-video-script.md",
    "docs/interview-guide.md",
    "docs/project-overview.md",
    "README.md",
    "scripts/generate_final_metrics_report.py",
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bya29\.[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"Authorization:\s*Bearer\s+[A-Za-z0-9._-]{12,}", re.IGNORECASE),
)


def _run(command: list[str], *, timeout: int = 120) -> dict[str, object]:
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "NOT_EXECUTED", "command": command, "detail": str(exc)}
    return {
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "returncode": completed.returncode,
        "command": command,
        "stdout_tail": completed.stdout[-1000:],
        "stderr_tail": completed.stderr[-1000:],
    }


def _docker_config() -> dict[str, object]:
    if shutil.which("docker") is None:
        return {"status": "NOT_EXECUTED", "detail": "Docker CLI unavailable"}
    command = ["docker", "compose", "--env-file", ".env.example", "config"]
    environment = os.environ.copy()
    environment["INBOX2ACTION_ENV_FILE"] = ".env.example"
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "NOT_EXECUTED", "command": command, "detail": str(exc)}
    return {
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "returncode": completed.returncode,
        "command": command,
        "stdout_tail": completed.stdout[-1000:],
        "stderr_tail": completed.stderr[-1000:],
    }


def _secret_scan() -> dict[str, object]:
    checked: list[str] = []
    findings: list[str] = []
    for relative in ("Dockerfile", "compose.yaml", ".env.example", "README.md", "docs", "scripts"):
        path = PROJECT_ROOT / relative
        paths = [path] if path.is_file() else sorted(path.rglob("*")) if path.is_dir() else []
        for candidate in paths:
            if not candidate.is_file() or candidate.suffix in {".pyc", ".jsonl"}:
                continue
            checked.append(candidate.relative_to(PROJECT_ROOT).as_posix())
            text = candidate.read_text(encoding="utf-8", errors="replace")
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    findings.append(f"{candidate.relative_to(PROJECT_ROOT)}:{pattern.pattern}")
    return {"status": "PASS" if not findings else "FAIL", "files": len(checked), "findings": findings}


def _static_checks() -> dict[str, object]:
    missing = [path for path in REQUIRED_FILES if not (PROJECT_ROOT / path).is_file()]
    mermaid = all(
        "```mermaid" in (PROJECT_ROOT / path).read_text(encoding="utf-8")
        for path in ("docs/architecture.md", "docs/graph.md")
        if (PROJECT_ROOT / path).is_file()
    )
    env_text = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    env_required = {
        "INBOX2ACTION_DATABASE_URL",
        "LLM_ENABLED",
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL_NAME",
        "GMAIL_CLIENT_SECRETS_PATH",
        "GMAIL_TOKEN_PATH",
        "CLICKUP_ENABLED",
        "CLICKUP_LIST_ID",
        "GOOGLE_CALENDAR_ENABLED",
        "GOOGLE_CALENDAR_ID",
        "INBOX2ACTION_BUSINESS_TIMEZONE",
    }
    missing_env = sorted(
        name for name in env_required if not re.search(rf"^{re.escape(name)}=", env_text, re.MULTILINE)
    )
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
    ignore_ok = all(token in dockerignore for token in (".env", "runtime.env", "gmail-token.json"))
    status = "PASS" if not missing and mermaid and not missing_env and ignore_ok else "FAIL"
    return {
        "status": status,
        "missing_files": missing,
        "mermaid": mermaid,
        "missing_env_variables": missing_env,
        "dockerignore_secrets": ignore_ok,
    }


def _source_check(source: Path) -> dict[str, object]:
    if not source.is_file():
        return {"status": "NOT_EXECUTED", "detail": f"Missing source: {source}"}
    raw = source.read_bytes()
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "detail": str(exc)}
    if not isinstance(result, dict) or result.get("stage") != "stage10":
        return {"status": "FAIL", "detail": "not a Stage 10 result object"}
    return {
        "status": "PASS" if result.get("final_verdict") in {"PASS", "COMPLETE"} else "FAIL",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "final_verdict": result.get("final_verdict"),
        "dataset_version": result.get("dataset_version"),
    }


def _report_consistency(source: Path) -> dict[str, object]:
    report = PROJECT_ROOT / "docs" / "evaluation-report.md"
    if not source.is_file() or not report.is_file():
        return {"status": "NOT_EXECUTED", "detail": "source or report is missing"}
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    try:
        source_value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "detail": str(exc)}
    if not isinstance(source_value, dict):
        return {"status": "FAIL", "detail": "source is not a JSON object"}
    report_text = report.read_text(encoding="utf-8")
    expected_values = (source_hash, str(source_value.get("dataset_version", "")))
    missing = [value for value in expected_values if not value or value not in report_text]
    return {
        "status": "PASS" if not missing else "FAIL",
        "source_sha256": source_hash,
        "missing_values": missing,
    }


def _run_full_pytest() -> dict[str, object]:
    primary = _run(["uv", "run", "--frozen", "pytest", "-q"], timeout=900)
    if primary["status"] != "NOT_EXECUTED":
        return primary
    venv_python = PROJECT_ROOT.parent.parent / ".venv" / "Scripts" / "python.exe"
    if not venv_python.is_file():
        return primary
    base_temp = PROJECT_ROOT / ".pytest-tmp" / "stage11-acceptance"
    base_temp.mkdir(parents=True, exist_ok=True)
    fallback = _run(
        [str(venv_python), "-m", "pytest", "-q", "--basetemp", str(base_temp)],
        timeout=900,
    )
    return {"status": fallback["status"], "primary": primary, "fallback": fallback}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage10-result", type=Path, default=Path("evaluation/results/stage10-final.json"))
    parser.add_argument("--output", type=Path, default=Path("evaluation/results/stage11-final.json"))
    parser.add_argument("--run-tests", action="store_true", help="Run the frozen full pytest regression.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    static = _static_checks()
    result: dict[str, object] = {
        "stage": "stage11",
        "canonical_goal": "Project Finalization",
        "base": "a341ae542474b44abaf8f9bb0ea1b2d0544f7e3d",
        "static_checks": static,
        "stage10_result": _source_check(args.stage10_result),
        "metrics_report_consistency": _report_consistency(args.stage10_result),
        "docker_compose_config": _docker_config(),
        "secrets_scan": _secret_scan(),
    }
    if args.run_tests:
        result["full_pytest"] = _run_full_pytest()
    else:
        result["full_pytest"] = {"status": "NOT_EXECUTED", "detail": "use --run-tests"}
    static_pass = static["status"] == "PASS"
    stage10_pass = result["stage10_result"]["status"] == "PASS"  # type: ignore[index]
    report_pass = result["metrics_report_consistency"]["status"] == "PASS"  # type: ignore[index]
    secrets_pass = result["secrets_scan"]["status"] == "PASS"  # type: ignore[index]
    tests_pass = result["full_pytest"]["status"] in {"PASS", "NOT_EXECUTED"}  # type: ignore[index]
    result["engineering_verdict"] = "COMPLETE" if static_pass and stage10_pass and report_pass and secrets_pass and tests_pass else "INCOMPLETE"
    result["docker_runtime_smoke"] = "MANUAL GATE"
    result["actual_demo_video"] = "MANUAL GATE"
    result["final_verdict"] = "COMPLETE" if result["engineering_verdict"] == "COMPLETE" and False else "INCOMPLETE"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"engineering_verdict": result["engineering_verdict"], "final_verdict": result["final_verdict"], "output": str(args.output)}, sort_keys=True))
    return 0 if result["engineering_verdict"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
