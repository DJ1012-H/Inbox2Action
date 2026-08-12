"""Build deterministic human-review batches for the dataset vNext candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parents[1]
DATASET_ROOT = PROJECT_ROOT / "evaluation" / "dataset-vnext"
DEFAULT_OUTPUT_ROOT = DATASET_ROOT / "reviews" / "human-review"
REVIEW_BASE_COMMIT = "f0d015013178f0c7a74294d1d68a182cf2bdd3fe"
CREATED_AT = date(2026, 8, 13)
BATCH_SIZE = 20

EMAIL_SOURCES = (
    "cases/development.jsonl",
    "cases/regression.jsonl",
    "cases/security-challenge.jsonl",
)
CONTROL_SOURCES = (
    "gmail/access-policy-cases.jsonl",
    "gmail/pagination-cases.jsonl",
    "content-policy/model-input-gold.jsonl",
    "observability/boundary-gold.jsonl",
    "gmail/access-injection-matrix.jsonl",
    "response-safety/scorer-calibration.jsonl",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        value = json.loads(raw_line)
        if not isinstance(value, dict):
            raise TypeError(f"{path}:{line_number} is not a JSON object")
        records.append(value)
    return records


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def _write_json(path: Path, value: object) -> None:
    _write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _render_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _sha256_lf(path: Path) -> str:
    normalized = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def _chunks(records: list[dict[str, Any]]) -> Iterable[list[dict[str, Any]]]:
    for offset in range(0, len(records), BATCH_SIZE):
        yield records[offset : offset + BATCH_SIZE]


def _review_map(dataset_root: Path, filename: str) -> dict[str, dict[str, Any]]:
    records = _load_jsonl(dataset_root / "reviews" / filename)
    return {str(item["case_id"]): item for item in records}


def _email_item(
    source: str,
    candidate: dict[str, Any],
    review: dict[str, Any],
) -> dict[str, Any]:
    return {
        "item_id": candidate["case_id"],
        "domain": "email",
        "source_path": source,
        "candidate": candidate,
        "current_review": review,
    }


def _control_item(
    source: str,
    candidate: dict[str, Any],
    review: dict[str, Any],
) -> dict[str, Any]:
    return {
        "item_id": candidate["case_id"],
        "domain": "control",
        "control_type": source.removesuffix(".jsonl").replace("/", ":"),
        "source_path": source,
        "candidate": candidate,
        "current_review": review,
    }


def _collect_items(dataset_root: Path) -> list[dict[str, Any]]:
    email_reviews = _review_map(dataset_root, "review-records.jsonl")
    control_reviews = _review_map(dataset_root, "control-review-records.jsonl")
    items: list[dict[str, Any]] = []
    for source in EMAIL_SOURCES:
        for candidate in _load_jsonl(dataset_root / source):
            item_id = str(candidate["case_id"])
            items.append(_email_item(source, candidate, email_reviews[item_id]))
    for source in CONTROL_SOURCES:
        for candidate in _load_jsonl(dataset_root / source):
            item_id = str(candidate["case_id"])
            items.append(_control_item(source, candidate, control_reviews[item_id]))
    if len(items) != 260 or len({item["item_id"] for item in items}) != 260:
        raise ValueError("review packet requires exactly 260 globally unique items")
    if any(item["current_review"]["status"] != "draft" for item in items):
        raise ValueError("review packet generation requires every item to remain draft")
    return items


def _render_email(item: dict[str, Any]) -> str:
    candidate = item["candidate"]
    envelope = candidate["envelope"]
    sections = [
        f"- Split/category: `{candidate['split']}` / `{candidate['category']}`",
        f"- Language: `{candidate['language']}`",
        f"- Source: `{item['source_path']}`",
        f"- Subject: {envelope['subject']}",
        "",
        "Complete synthetic body:",
        "",
        "```text",
        envelope["body"],
        "```",
    ]
    if envelope.get("html") is not None:
        sections.extend(["", "HTML candidate:", "", "```html", envelope["html"], "```"])
    sections.extend(
        [
            "",
            "Envelope metadata and attachments:",
            "",
            "```json",
            _render_json(
                {
                    "from_address": envelope["from_address"],
                    "reply_to": envelope.get("reply_to"),
                    "received_at": envelope["received_at"],
                    "provider_thread_id": envelope.get("provider_thread_id"),
                    "headers": envelope["headers"],
                    "attachments": envelope["attachments"],
                }
            ),
            "```",
            "",
            "Gold candidate:",
            "",
            "```json",
            _render_json(candidate["expected"]),
            "```",
        ]
    )
    return "\n".join(sections)


def _render_item(item: dict[str, Any], ordinal: int) -> str:
    body = (
        _render_email(item)
        if item["domain"] == "email"
        else "\n".join(
            [
                f"- Control type: `{item['control_type']}`",
                f"- Source: `{item['source_path']}`",
                "",
                "Complete control candidate and Gold:",
                "",
                "```json",
                _render_json(item["candidate"]),
                "```",
            ]
        )
    )
    return "\n".join(
        [
            f"## {ordinal}. `{item['item_id']}`",
            "",
            f"Current review state: `{item['current_review']['status']}`",
            "",
            body,
            "",
            "Reviewer decision: `PENDING`",
            "",
            "Reviewer notes: _fill during human review_",
            "",
        ]
    )


def _render_batch(batch_number: int, records: list[dict[str, Any]]) -> str:
    domain = records[0]["domain"]
    header = [
        f"# Dataset vNext Human Review Batch {batch_number:02d}",
        "",
        f"Candidate commit: `{REVIEW_BASE_COMMIT}`",
        f"Review domain: `{domain}`",
        f"Items: `{len(records)}`",
        "",
        "Inspect every complete candidate and Gold Label. Reply using one of:",
        "",
        f"- `APPROVE DATASET-VNEXT REVIEW BATCH-{batch_number:02d}`",
        f"- `REQUEST CHANGES DATASET-VNEXT REVIEW BATCH-{batch_number:02d}: <item_id>: <reason>`",
        "",
        "Approval applies only to this batch and does not create or authorize a holdout.",
        "",
    ]
    return "\n".join(
        [*header, *(_render_item(item, index) for index, item in enumerate(records, 1))]
    )


def _render_index(batch_metadata: list[dict[str, Any]]) -> str:
    rows = [
        "# Dataset vNext Human Review Packet",
        "",
        f"Candidate commit: `{REVIEW_BASE_COMMIT}`",
        f"Created: `{CREATED_AT.isoformat()}`",
        "",
        "All 260 items remain draft until the project owner explicitly approves each batch.",
        "The first six batches cover 120 email candidates; the remaining seven cover",
        "140 Gmail boundary controls. Holdout creation remains prohibited.",
        "",
        "| Batch | Domain | Items | Status | File |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for item in batch_metadata:
        rows.append(
            f"| {item['batch']:02d} | {item['domain']} | {item['count']} | PENDING | "
            f"[{item['filename']}]({item['filename']}) |"
        )
    return "\n".join(rows) + "\n"


def build_review_packet(dataset_root: Path, output_root: Path) -> None:
    items = _collect_items(dataset_root.resolve())
    batch_metadata: list[dict[str, Any]] = []
    asset_paths: list[Path] = []
    for batch_number, records in enumerate(_chunks(items), start=1):
        filename = f"batch-{batch_number:02d}.md"
        path = output_root / filename
        _write_text(path, _render_batch(batch_number, records))
        asset_paths.append(path)
        batch_metadata.append(
            {
                "batch": batch_number,
                "domain": records[0]["domain"],
                "count": len(records),
                "filename": filename,
                "first_item_id": records[0]["item_id"],
                "last_item_id": records[-1]["item_id"],
            }
        )

    decisions = [
        {
            "item_id": item["item_id"],
            "batch": (index // BATCH_SIZE) + 1,
            "decision": "pending",
            "reviewer": None,
            "reviewed_at": None,
            "notes": None,
        }
        for index, item in enumerate(items)
    ]
    decisions_path = output_root / "decisions-template.jsonl"
    _write_text(
        decisions_path,
        "".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
            for item in decisions
        ),
    )
    asset_paths.append(decisions_path)
    index_path = output_root / "README.md"
    _write_text(index_path, _render_index(batch_metadata))
    asset_paths.append(index_path)
    _write_json(
        output_root / "review-packet-manifest.json",
        {
            "schema_version": "dataset-vnext-review-packet-1",
            "candidate_commit": REVIEW_BASE_COMMIT,
            "created_at": CREATED_AT.isoformat(),
            "review_state": "draft",
            "email_item_count": 120,
            "control_item_count": 140,
            "item_count": 260,
            "batch_size": BATCH_SIZE,
            "batch_count": len(batch_metadata),
            "formal_holdout_created": False,
            "batch_metadata": batch_metadata,
            "asset_sha256": {
                path.name: _sha256_lf(path) for path in sorted(asset_paths)
            },
        },
    )


def validate_review_packet(dataset_root: Path, output_root: Path) -> None:
    items = _collect_items(dataset_root.resolve())
    manifest = json.loads(
        (output_root / "review-packet-manifest.json").read_text(encoding="utf-8")
    )
    if manifest["candidate_commit"] != REVIEW_BASE_COMMIT:
        raise ValueError("review packet is not bound to the approved candidate commit")
    if manifest["item_count"] != len(items) or manifest["batch_count"] != 13:
        raise ValueError("review packet counts are incomplete")
    if manifest["review_state"] != "draft" or manifest["formal_holdout_created"]:
        raise ValueError("review packet must remain draft and holdout-free")
    for filename, expected_hash in manifest["asset_sha256"].items():
        if _sha256_lf(output_root / filename) != expected_hash:
            raise ValueError("review packet asset hash mismatch")


def main() -> int:
    args = parse_args()
    if not args.check:
        build_review_packet(args.dataset_root, args.output_root)
    validate_review_packet(args.dataset_root, args.output_root)
    print(
        json.dumps(
            {
                "status": "PASS",
                "candidate_commit": REVIEW_BASE_COMMIT,
                "item_count": 260,
                "batch_count": 13,
                "review_state": "draft",
                "formal_holdout_created": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
