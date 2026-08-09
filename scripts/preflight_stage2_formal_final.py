"""Read-only preflight for the frozen final stage-two formal60 assets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.evaluation.policy_v3 import load_case_execution_policies_v3
from inbox2action.evaluation.preflight_final import preflight_formal_assets_final

PROJECT_ROOT = Path(__file__).parents[1]
DEFAULT_FORMAL_ROOT = PROJECT_ROOT / "evaluation" / "formal-final"
DEFAULT_CANDIDATE_MANIFEST = (
    PROJECT_ROOT / "evaluation" / "final-candidate-freeze.json"
)
DEFAULT_ASSET_MANIFEST = DEFAULT_FORMAL_ROOT / "formal-asset-manifest.json"
EXPECTED_CANDIDATE_MANIFEST_SHA256 = (
    "526071a22db0f40923099ec7ee08a8d1c8c713fa8af5af154d1b0ecbd05a4d47"
)
EXPECTED_ASSET_MANIFEST_SHA256 = (
    "674f7261097d55b0e8cba5c1a23a22ee2b5864552bbfbc2a343afc61f2e47a56"
)
EXPECTED_CANDIDATE_MANIFEST_SHA256_ATTEMPT_2 = (
    "e9961c181fad62bd84a4c8dd2764c5847e18e07d20e44fa7c23b8303efd34a58"
)
EXPECTED_ASSET_MANIFEST_SHA256_ATTEMPT_2 = (
    "fd4fc79ca6e5a07188976d601d14e7f244fc7b75f1ddec3be13bb323a73b47d3"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--attempt-id",
        choices=("attempt-1", "attempt-2"),
        default="attempt-1",
    )
    parser.add_argument("--evaluation-root", type=Path, default=DEFAULT_FORMAL_ROOT)
    parser.add_argument(
        "--policy-file",
        type=Path,
        default=DEFAULT_FORMAL_ROOT / "policies.jsonl",
    )
    parser.add_argument(
        "--holdout-ids",
        type=Path,
        default=DEFAULT_FORMAL_ROOT / "holdout.json",
    )
    parser.add_argument(
        "--candidate-manifest",
        type=Path,
        default=DEFAULT_CANDIDATE_MANIFEST,
    )
    parser.add_argument(
        "--asset-manifest",
        type=Path,
        default=DEFAULT_ASSET_MANIFEST,
    )
    return parser.parse_args()


def verify_hash_manifest(
    path: Path,
    *,
    expected_manifest_sha256: str | None = None,
) -> None:
    manifest_bytes = path.read_bytes()
    if (
        expected_manifest_sha256 is not None
        and hashlib.sha256(manifest_bytes).hexdigest()
        != expected_manifest_sha256
    ):
        raise ValueError("hash manifest identity mismatch")
    payload = json.loads(manifest_bytes.decode("utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("sha256"), dict):
        raise TypeError("hash manifest must contain a sha256 object")
    for raw_path, expected in payload["sha256"].items():
        if not isinstance(raw_path, str) or not isinstance(expected, str):
            raise TypeError("hash manifest entries must be strings")
        candidate = (PROJECT_ROOT / raw_path).resolve()
        if PROJECT_ROOT.resolve() not in candidate.parents:
            raise ValueError("hash manifest path escapes project root")
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("frozen file hash mismatch")


def main() -> int:
    args = parse_args()
    candidate_manifest_sha256 = (
        EXPECTED_CANDIDATE_MANIFEST_SHA256_ATTEMPT_2
        if args.attempt_id == "attempt-2"
        else EXPECTED_CANDIDATE_MANIFEST_SHA256
    )
    asset_manifest_sha256 = (
        EXPECTED_ASSET_MANIFEST_SHA256_ATTEMPT_2
        if args.attempt_id == "attempt-2"
        else EXPECTED_ASSET_MANIFEST_SHA256
    )
    try:
        verify_hash_manifest(
            args.candidate_manifest,
            expected_manifest_sha256=candidate_manifest_sha256,
        )
        verify_hash_manifest(
            args.asset_manifest,
            expected_manifest_sha256=asset_manifest_sha256,
        )
        bundle = load_evaluation_asset_bundle(args.evaluation_root)
        policies = load_case_execution_policies_v3(args.policy_file)
        holdout_payload = json.loads(args.holdout_ids.read_text(encoding="utf-8"))
        if not isinstance(holdout_payload, list) or any(
            not isinstance(case_id, str) for case_id in holdout_payload
        ):
            raise ValueError("holdout IDs must be a JSON string array")
        if len(holdout_payload) != len(set(holdout_payload)):
            raise ValueError("holdout IDs must be unique")
        result = preflight_formal_assets_final(
            bundle,
            case_policies=policies,
            holdout_case_ids=set(holdout_payload),
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "error_class": type(exc).__name__,
                    "failure_reasons": ["formal_preflight_input_invalid"],
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
