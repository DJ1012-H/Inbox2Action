from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from inbox2action.evaluation.dataset_vnext import (
    CandidateReviewRecordVNext,
    CandidateReviewStatus,
    DatasetSplit,
    EmailDatasetCaseVNext,
    WorkflowScenarioType,
    lf_sha256,
    load_jsonl,
    validate_dataset_vnext,
)
from inbox2action.evaluation.gmail_boundary_vnext import (
    GMAIL_READONLY_SCOPE,
    PILOT_LABEL,
    PILOT_QUERY,
    AccessDecision,
    AccessInjectionQuadrant,
    GmailAccessInjectionCaseVNext,
    GmailAccessPolicyCaseVNext,
    GmailApiMessageFixtureVNext,
    GmailContentPolicyCaseVNext,
    GmailObservabilityCaseVNext,
    GmailPaginationCaseVNext,
    ResponseSafetyScorerCaseVNext,
    validate_gmail_boundary_assets,
)

PROJECT_ROOT = Path(__file__).parents[2]
DATASET_ROOT = PROJECT_ROOT / "evaluation" / "dataset-vnext"


def _load_cases(root: Path = DATASET_ROOT) -> tuple[EmailDatasetCaseVNext, ...]:
    records: list[EmailDatasetCaseVNext] = []
    for filename in (
        "development.jsonl",
        "regression.jsonl",
        "security-challenge.jsonl",
    ):
        records.extend(
            load_jsonl(
                root / "cases" / filename,
                EmailDatasetCaseVNext,
                identifier=lambda item: item.case_id,
            )
        )
    return tuple(records)


def test_checked_in_dataset_vnext_is_complete_but_not_formal() -> None:
    summary = validate_dataset_vnext(DATASET_ROOT)

    assert summary.case_count == 120
    assert summary.split_counts == {
        "development": 60,
        "regression": 30,
        "security_challenge": 30,
    }
    assert summary.language_counts == {"en": 28, "zh-CN": 70, "zh-TW": 22}
    assert summary.workflow_scenario_count == 30
    assert summary.fixture_count == 60
    assert summary.review_status_counts == {"draft": 120}
    assert set(summary.workflow_type_counts) == {
        item.value for item in WorkflowScenarioType
    }
    assert all(count == 3 for count in summary.workflow_type_counts.values())
    assert summary.formal_holdout_created is False
    assert summary.real_provider_evidence is False
    assert not (DATASET_ROOT / "formal-holdout").exists()

    boundary_summary = validate_gmail_boundary_assets(DATASET_ROOT)
    assert boundary_summary.control_case_count == 140
    assert boundary_summary.control_type_counts == {
        "access_injection_matrix": 20,
        "access_policy": 30,
        "content_policy": 30,
        "observability": 20,
        "pagination": 20,
        "response_safety": 20,
    }
    assert boundary_summary.gmail_message_fixture_count == 30
    assert boundary_summary.review_status_counts == {"draft": 140}
    assert boundary_summary.pilot_account_type == "private_personal"
    assert boundary_summary.real_mailbox_accessed is False
    assert boundary_summary.real_provider_evidence is False


def test_dataset_vnext_rebuild_is_deterministic(tmp_path: Path) -> None:
    script = PROJECT_ROOT / "scripts" / "build_dataset_vnext.py"
    rebuilt = tmp_path / "dataset-vnext"
    completed = subprocess.run(
        [sys.executable, str(script), "--output-root", str(rebuilt)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert '"status": "PASS"' in completed.stdout
    manifest = json.loads((DATASET_ROOT / "manifest.json").read_text(encoding="utf-8"))
    boundary_manifest = json.loads(
        (DATASET_ROOT / "gmail-boundary-manifest.json").read_text(encoding="utf-8")
    )
    relative_paths = [
        "manifest.json",
        *manifest["asset_sha256"],
        "gmail-boundary-manifest.json",
        *boundary_manifest["asset_sha256"],
    ]
    for relative_path in relative_paths:
        assert lf_sha256(rebuilt / relative_path) == lf_sha256(
            DATASET_ROOT / relative_path
        )


def test_dataset_vnext_uses_synthetic_sources_and_draft_reviews() -> None:
    cases = _load_cases()
    reviews = load_jsonl(
        DATASET_ROOT / "reviews" / "review-records.jsonl",
        CandidateReviewRecordVNext,
        identifier=lambda item: item.case_id,
    )

    assert len({item.case_id for item in cases}) == 120
    assert len({item.envelope.subject for item in cases}) == 120
    assert len({item.envelope.body for item in cases}) == 120
    assert all(
        item.envelope.from_address.endswith(("@example.com", "@example.test"))
        for item in cases
    )
    assert all(
        attachment.synthetic_only
        for item in cases
        for attachment in item.envelope.attachments
    )
    assert all(item.status is CandidateReviewStatus.DRAFT for item in reviews)
    assert all(item.reviewed_at is None for item in reviews)
    assert {item.split for item in cases} == set(DatasetSplit)
    assert not any("holdout" in item.case_id.casefold() for item in cases)


def test_dataset_vnext_covers_extended_email_and_fail_closed_paths() -> None:
    cases = _load_cases()
    tags = {tag for item in cases for tag in item.tags}

    assert sum(item.envelope.html is not None for item in cases) == 27
    assert sum(bool(item.envelope.attachments) for item in cases) == 21
    assert sum(item.envelope.provider_thread_id is not None for item in cases) == 27
    assert sum(item.expected.normalization.expect_truncated for item in cases) == 12
    assert sum(item.expected.normalization.minimum_redactions > 0 for item in cases) == 30
    assert sum(
        item.expected.normalization.minimum_tracking_parameters_removed > 0
        for item in cases
    ) == 30
    assert {
        "duplicate_delivery",
        "approval_edit",
        "stale_approval",
        "restart_recovery",
        "provider_failure",
        "provider_unknown",
        "payload_hash_mismatch",
        "dependency_order",
        "rejection",
        "retry_after_failure",
    }.issubset(tags)
    assert all(item.expected.maximum_external_side_effects == 0 for item in cases)
    assert all(item.expected.maximum_unauthorized_writes == 0 for item in cases)
    assert all(item.expected.maximum_approval_bypasses == 0 for item in cases)


def test_lf_hash_is_portable_across_windows_line_endings(tmp_path: Path) -> None:
    source = DATASET_ROOT / "reviews" / "review-records.jsonl"
    crlf_copy = tmp_path / "review-records.jsonl"
    crlf_copy.write_text(
        source.read_text(encoding="utf-8").replace("\n", "\r\n"),
        encoding="utf-8",
        newline="",
    )

    assert lf_sha256(crlf_copy) == lf_sha256(source)


def test_vnext_schemas_use_json_schema_2020_12() -> None:
    schema_paths = sorted((DATASET_ROOT / "schemas").glob("*.schema.json"))

    assert len(schema_paths) == 11
    for path in schema_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert payload["title"]


def test_gmail_access_contract_is_private_label_only_and_fail_closed() -> None:
    cases = load_jsonl(
        DATASET_ROOT / "gmail" / "access-policy-cases.jsonl",
        GmailAccessPolicyCaseVNext,
        identifier=lambda item: item.case_id,
    )
    allowed = [
        item
        for item in cases
        if item.expected.decision is AccessDecision.ALLOW_QUERY
    ]
    denied = [
        item
        for item in cases
        if item.expected.decision is AccessDecision.DENY_BEFORE_QUERY
    ]

    assert len(allowed) == 5
    assert len(denied) == 25
    assert all(item.private_pilot_account for item in cases)
    assert all(item.input.oauth_scopes == [GMAIL_READONLY_SCOPE] for item in allowed)
    assert all(item.input.allowed_label == PILOT_LABEL for item in allowed)
    assert all(item.input.gmail_query == PILOT_QUERY for item in allowed)
    assert all(item.input.provider_side_filter for item in allowed)
    assert all(item.expected.maximum_list_calls == 0 for item in denied)
    assert all(not item.expected.inbox_wide_query_allowed for item in cases)
    assert {item.scenario for item in denied}.issuperset(
        {
            "missing_query",
            "inbox_wide_query",
            "all_mail_query",
            "local_filter_only",
            "scope_modify",
            "scope_compose",
            "scope_send",
            "scope_mail_google",
            "extra_scope",
            "empty_label",
            "missing_page_cap",
        }
    )


def test_gmail_pagination_and_content_contracts_are_bounded_and_minimized() -> None:
    pagination = load_jsonl(
        DATASET_ROOT / "gmail" / "pagination-cases.jsonl",
        GmailPaginationCaseVNext,
        identifier=lambda item: item.case_id,
    )
    messages = load_jsonl(
        DATASET_ROOT / "gmail" / "api-message-fixtures.jsonl",
        GmailApiMessageFixtureVNext,
        identifier=lambda item: item.fixture_id,
    )
    content = load_jsonl(
        DATASET_ROOT / "content-policy" / "model-input-gold.jsonl",
        GmailContentPolicyCaseVNext,
        identifier=lambda item: item.case_id,
    )

    assert len(pagination) == 20
    assert all(len(item.pages) <= 2 for item in pagination)
    assert all(item.expected.maximum_list_calls <= 2 for item in pagination)
    assert all(len(item.expected.processed_message_ids) <= 20 for item in pagination)
    assert all(not item.expected.unbounded_history_scan for item in pagination)
    assert {item.expected.reason_code for item in pagination}.issuperset(
        {"invalid_cursor", "pagination_token_loop", "page_cap_reached"}
    )

    assert len(messages) == 30
    assert len(content) == 30
    messages_by_id = {item.fixture_id: item for item in messages}
    assert sum(PILOT_LABEL in item.label_ids for item in messages) == 20
    assert all(
        not attachment.content_included
        for item in messages
        for attachment in item.attachments
    )
    for item in content:
        fixture = messages_by_id[item.message_fixture_id]
        label_allowed = PILOT_LABEL in fixture.label_ids
        assert item.expected.access_allowed is label_allowed
        assert item.expected.body_fetch_allowed is label_allowed
        assert not item.expected.attachments_sent_to_model
        assert not item.expected.attachment_ocr_allowed
        assert not item.expected.raw_headers_sent_to_model
        assert not item.expected.verification_codes_sent_to_model
        assert not item.expected.credentials_sent_to_model
        assert item.expected.recipient_binding_source == "trusted_application_context"
        assert item.expected.address_redaction_strategy == "role_token"
        if item.expected.model_invocation_allowed:
            assert item.expected.model_visible_fields == [
                "sanitized_subject",
                "sanitized_body",
                "timezone",
            ]
        else:
            assert item.expected.model_visible_fields == []


def test_access_injection_observability_and_response_safety_are_explicit() -> None:
    matrix = load_jsonl(
        DATASET_ROOT / "gmail" / "access-injection-matrix.jsonl",
        GmailAccessInjectionCaseVNext,
        identifier=lambda item: item.case_id,
    )
    observability = load_jsonl(
        DATASET_ROOT / "observability" / "boundary-gold.jsonl",
        GmailObservabilityCaseVNext,
        identifier=lambda item: item.case_id,
    )
    response_safety = load_jsonl(
        DATASET_ROOT / "response-safety" / "scorer-calibration.jsonl",
        ResponseSafetyScorerCaseVNext,
        identifier=lambda item: item.case_id,
    )
    reviews = load_jsonl(
        DATASET_ROOT / "reviews" / "control-review-records.jsonl",
        CandidateReviewRecordVNext,
        identifier=lambda item: item.case_id,
    )

    assert Counter(item.quadrant for item in matrix) == {
        quadrant: 5 for quadrant in AccessInjectionQuadrant
    }
    for item in matrix:
        allowed = item.quadrant in {
            AccessInjectionQuadrant.ALLOWED_BENIGN,
            AccessInjectionQuadrant.ALLOWED_MALICIOUS,
        }
        malicious = item.quadrant in {
            AccessInjectionQuadrant.DISALLOWED_MALICIOUS,
            AccessInjectionQuadrant.ALLOWED_MALICIOUS,
        }
        assert item.expected.discovered_by_list is allowed
        assert item.expected.body_fetched is allowed
        assert item.expected.injection_detected is (allowed and malicious)
        assert item.expected.model_invoked is (allowed and not malicious)
        assert item.expected.external_side_effects == 0

    assert len(observability) == 20
    assert all(not item.expected.raw_body_persisted for item in observability)
    assert all(item.expected.raw_body_retention_days == 0 for item in observability)
    assert all(
        item.expected.sanitized_context_retention_days == 7
        for item in observability
    )
    assert all(
        item.expected.business_result_retention_days == 90
        for item in observability
    )
    assert all(
        item.expected.redacted_audit_retention_days == 90
        for item in observability
    )

    passed = [item for item in response_safety if item.expected.scorer_should_pass]
    failed = [item for item in response_safety if not item.expected.scorer_should_pass]
    assert len(passed) == 10
    assert len(failed) == 10
    assert all(
        item.expected.unauthorized_action_claims == 0
        and item.expected.secret_disclosures == 0
        and item.expected.untrusted_instruction_repetitions == 0
        and item.expected.risk_warning_present
        and item.expected.no_action_statement_present
        for item in passed
    )
    assert all(
        item.expected.unauthorized_action_claims
        + item.expected.secret_disclosures
        + item.expected.untrusted_instruction_repetitions
        + int(not item.expected.risk_warning_present)
        + int(not item.expected.no_action_statement_present)
        >= 1
        for item in failed
    )
    assert len(reviews) == 140
    assert all(item.status is CandidateReviewStatus.DRAFT for item in reviews)
    assert all(item.reviewed_at is None for item in reviews)


def test_gmail_boundary_models_reject_inconsistent_contract_records() -> None:
    access = load_jsonl(
        DATASET_ROOT / "gmail" / "access-policy-cases.jsonl",
        GmailAccessPolicyCaseVNext,
        identifier=lambda item: item.case_id,
    )[0]
    denied_access = access.model_dump(mode="json")
    denied_access["expected"]["decision"] = "deny_before_query"
    denied_access["expected"]["maximum_list_calls"] = 0
    with pytest.raises(ValueError):
        GmailAccessPolicyCaseVNext.model_validate(denied_access)

    pagination = load_jsonl(
        DATASET_ROOT / "gmail" / "pagination-cases.jsonl",
        GmailPaginationCaseVNext,
        identifier=lambda item: item.case_id,
    )[0]
    over_paged = pagination.model_dump(mode="json")
    over_paged["pages"].append({"message_ids": []})
    with pytest.raises(ValueError):
        GmailPaginationCaseVNext.model_validate(over_paged)
