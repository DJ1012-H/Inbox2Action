"""PostgresStore-backed memory load/update boundary."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from langgraph.store.base import BaseStore

from inbox2action.memory.context import PreferenceContext
from inbox2action.memory.contracts import (
    CalendarPreferences,
    MemoryCategory,
    MemoryDocument,
    MemoryEvidence,
    MemoryPreferences,
    MemoryUpdateOutcome,
    ReplyPreferences,
    TaskPreferences,
    TriagePreferences,
    UserEditDiff,
    memory_owner_id,
)


class MemoryContractError(ValueError):
    """A bounded memory contract could not be validated."""


class AsyncMemoryStore(Protocol):
    async def aget(
        self, namespace: tuple[str, ...], key: str, **kwargs: Any
    ) -> Any: ...

    async def aput(
        self,
        namespace: tuple[str, ...],
        key: str,
        value: dict[str, Any],
        **kwargs: Any,
    ) -> None: ...

    async def asearch(self, namespace: tuple[str, ...], **kwargs: Any) -> list[Any]: ...


_MAX_EVIDENCE = 200
_MEMORY_KEY = "memory"
_EVIDENCE_PREFIX = "evidence:"
_UPDATE_LOCKS: dict[tuple[str, MemoryCategory], asyncio.Lock] = {}


class MemoryService:
    """Use the existing LangGraph Store; no second memory database is created."""

    def __init__(self, store: BaseStore | AsyncMemoryStore) -> None:
        self._store = store

    @staticmethod
    def namespace(owner_id: str, category: MemoryCategory) -> tuple[str, str]:
        return (memory_owner_id(owner_id), category.value)

    async def load(self, owner_id: str, category: MemoryCategory) -> MemoryDocument:
        owner = memory_owner_id(owner_id)
        namespace = self.namespace(owner, category)
        evidence = await self._load_evidence(namespace, category)
        if evidence:
            return _materialize(category, evidence)
        item = await self._store.aget(namespace, _MEMORY_KEY)
        if item is None:
            return _empty_document(category)
        try:
            return MemoryDocument.model_validate(item.value)
        except Exception:  # noqa: BLE001 - corrupted memory is ignored safely
            return _empty_document(category)

    async def load_context(self, owner_id: str) -> PreferenceContext:
        owner = memory_owner_id(owner_id)
        documents = {
            category: await self.load(owner, category) for category in MemoryCategory
        }
        return PreferenceContext(
            triage=cast(
                TriagePreferences, documents[MemoryCategory.TRIAGE].typed_preferences()
            ),
            reply=cast(
                ReplyPreferences, documents[MemoryCategory.REPLY].typed_preferences()
            ),
            task=cast(
                TaskPreferences, documents[MemoryCategory.TASK].typed_preferences()
            ),
            calendar=cast(
                CalendarPreferences,
                documents[MemoryCategory.CALENDAR].typed_preferences(),
            ),
            versions={
                category: document.version for category, document in documents.items()
            },
        )

    async def apply_user_edit(
        self, owner_id: str, diff: UserEditDiff
    ) -> tuple[MemoryUpdateOutcome, MemoryDocument]:
        owner = memory_owner_id(owner_id)
        if diff.is_no_op:
            return MemoryUpdateOutcome.NO_OP, await self.load(owner, diff.category)

        lock_key = (owner, diff.category)
        lock = _UPDATE_LOCKS.setdefault(lock_key, asyncio.Lock())
        async with lock:
            namespace = self.namespace(owner, diff.category)
            evidence_key = f"{_EVIDENCE_PREFIX}{diff.evidence_id}"
            existing = await self._store.aget(namespace, evidence_key)
            if existing is not None:
                return MemoryUpdateOutcome.ALREADY_APPLIED, await self.load(
                    owner, diff.category
                )

            current = await self.load(owner, diff.category)
            if current.version >= _MAX_EVIDENCE:
                raise MemoryContractError("memory evidence limit reached")
            next_version = current.version + 1
            evidence = MemoryEvidence(
                evidence_id=diff.evidence_id,
                category=diff.category,
                memory_version=next_version,
                thread_id=diff.thread_id,
                action_id=diff.action_id,
                approval_revision=diff.approval_revision,
                changed_fields=diff.changed_fields,
                before=diff.before,
                after=diff.after,
                preference_updates=diff.preference_updates,
                created_at=datetime.now(UTC),
            )
            await self._store.aput(
                namespace,
                evidence_key,
                evidence.model_dump(mode="json"),
                index=False,
            )
            updated_preferences = _apply_updates(
                diff.category, current.typed_preferences(), diff.preference_updates
            )
            updated = MemoryDocument(
                category=diff.category,
                version=next_version,
                preferences=updated_preferences.model_dump(mode="json"),
                evidence_count=next_version,
                updated_at=evidence.created_at,
            )
            await self._store.aput(
                namespace,
                _MEMORY_KEY,
                updated.model_dump(mode="json"),
                index=False,
            )
            return MemoryUpdateOutcome.APPLIED, updated

    async def _load_evidence(
        self, namespace: tuple[str, ...], category: MemoryCategory
    ) -> list[MemoryEvidence]:
        try:
            items = await self._store.asearch(
                namespace,
                filter={"record_type": "memory_evidence"},
                limit=_MAX_EVIDENCE,
            )
        except Exception:  # noqa: BLE001 - a store without search remains usable
            return []
        evidence: list[MemoryEvidence] = []
        for item in items:
            try:
                parsed = MemoryEvidence.model_validate(item.value)
            except Exception:  # noqa: BLE001, S112 - ignore corrupt records fail-closed
                continue
            if parsed.category is category:
                evidence.append(parsed)
        return sorted(evidence, key=lambda item: (item.created_at, item.evidence_id))


def _empty_document(category: MemoryCategory) -> MemoryDocument:
    return MemoryDocument(
        category=category,
        version=0,
        preferences={},
        evidence_count=0,
        updated_at=datetime.now(UTC),
    )


def _materialize(
    category: MemoryCategory, evidence: Iterable[MemoryEvidence]
) -> MemoryDocument:
    current: MemoryPreferences
    if category is MemoryCategory.TRIAGE:
        current = TriagePreferences()
    elif category is MemoryCategory.REPLY:
        current = ReplyPreferences()
    elif category is MemoryCategory.TASK:
        current = TaskPreferences()
    else:
        current = CalendarPreferences()
    records = list(evidence)
    for record in records:
        current = _apply_updates(category, current, record.preference_updates)
    updated_at = records[-1].created_at if records else datetime.now(UTC)
    return MemoryDocument(
        category=category,
        version=len(records),
        preferences=current.model_dump(mode="json"),
        evidence_count=len(records),
        updated_at=updated_at,
    )


def _apply_updates(
    category: MemoryCategory,
    current: MemoryPreferences,
    updates: dict[str, object],
) -> MemoryPreferences:
    if category is MemoryCategory.TRIAGE:
        if not {"decision", "message_type"}.issubset(updates):
            return current
        message_type = str(updates["message_type"]).strip().casefold()
        decision = str(updates["decision"]).strip().upper()
        values = current.model_dump()
        for field in ("ignored_types", "notify_types", "task_types"):
            values[field] = tuple(
                item for item in values[field] if item != message_type
            )
        target = {
            "IGNORE": "ignored_types",
            "NOTIFY": "notify_types",
            "ACTION_REQUIRED": "task_types",
        }.get(decision)
        if target is not None:
            values[target] = (*values[target], message_type)
        return TriagePreferences.model_validate(values)
    if category is MemoryCategory.REPLY:
        return ReplyPreferences.model_validate({**current.model_dump(), **updates})
    if category is MemoryCategory.TASK:
        return TaskPreferences.model_validate({**current.model_dump(), **updates})
    return CalendarPreferences.model_validate({**current.model_dump(), **updates})
