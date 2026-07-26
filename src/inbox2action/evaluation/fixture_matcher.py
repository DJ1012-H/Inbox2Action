"""Deterministic exact matching for formal ToolFixtureV1 observations."""

from __future__ import annotations

import copy
from collections.abc import Mapping

from pydantic import JsonValue

from inbox2action.evaluation.asset_bundle import EvaluationAssetBundleV1, canonical_json
from inbox2action.evaluation.assets import ToolFixtureV1


class ToolFixtureMatchError(ValueError):
    """Base class for safe fixture matching errors."""


class UnknownEvaluationCaseError(ToolFixtureMatchError):
    """The requested formal case is not in the provided bundle."""


class ToolFixtureNotFoundError(ToolFixtureMatchError):
    """No explicitly referenced fixture exactly matched the request."""


class ToolFixtureAmbiguousError(ToolFixtureMatchError):
    """More than one fixture exactly matched the request."""


class ToolFixtureMatcherV1:
    """Look up only exact, explicitly referenced fixture observations."""

    def __init__(self, bundle: EvaluationAssetBundleV1) -> None:
        self._bundle = bundle

    def match(
        self,
        *,
        case_id: str,
        tool_name: str,
        arguments: Mapping[str, JsonValue],
    ) -> ToolFixtureV1:
        case = next((item for item in self._bundle.cases if item.case_id == case_id), None)
        if case is None:
            raise UnknownEvaluationCaseError(f"unknown_case: case_id={case_id}")
        try:
            requested_arguments = canonical_json(arguments)
        except (TypeError, ValueError) as exc:
            raise ToolFixtureMatchError(
                f"invalid_arguments: case_id={case_id}; tool_name={tool_name}"
            ) from exc

        matches = [
            fixture
            for fixture in self._bundle.fixtures
            if fixture.fixture_id in case.tool_fixture_ids
            and fixture.case_id == case_id
            and fixture.tool_name == tool_name
            and canonical_json(fixture.arguments_match) == requested_arguments
        ]
        if not matches:
            raise ToolFixtureNotFoundError(
                f"fixture_not_found: case_id={case_id}; tool_name={tool_name}"
            )
        if len(matches) > 1:
            raise ToolFixtureAmbiguousError(
                f"fixture_ambiguous: case_id={case_id}; tool_name={tool_name}"
            )
        return matches[0]

    def get_observation(
        self,
        *,
        case_id: str,
        tool_name: str,
        arguments: Mapping[str, JsonValue],
    ) -> dict[str, JsonValue]:
        fixture = self.match(
            case_id=case_id,
            tool_name=tool_name,
            arguments=arguments,
        )
        return copy.deepcopy(fixture.observation)
