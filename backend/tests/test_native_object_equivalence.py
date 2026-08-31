"""Provider-free tests for native structured-object lossless comparison."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.normalization_parser import (
    NativeEquivalenceIneligibleError,
    compare_independent_native_payloads,
    parse_strict_json_payload,
)


def _reference(payload: str):
    return parse_strict_json_payload(payload.encode("utf-8"))


@pytest.mark.parametrize(
    ("payload", "candidate"),
    (
        ('{"risk":"HIGH","confidence_score":0.9}', {"risk": "HIGH"}),
        ('{"risk":"HIGH"}', {"risk": "high"}),
        ('{"score":"65.00"}', {"score": 65}),
        ('{"detail":null}', {}),
        ('{"name":"é"}', {"name": "é"}),
        ('{"items":["A","B"]}', {"items": ["B", "A"]}),
        ('{"nested":{"a":1}}', {"nested": {"a": 1, "extra": None}}),
    ),
)
def test_native_independent_comparison_rejects_semantic_loss(payload, candidate):
    assert (
        compare_independent_native_payloads(_reference(payload), candidate)
        == "proven_unequal"
    )


@pytest.mark.parametrize(
    ("payload", "candidate"),
    (
        (
            '{"risk":"HIGH","nullable":null,"items":["A","B"],"score":65}',
            {
                "risk": "HIGH",
                "nullable": None,
                "items": ["A", "B"],
                "score": 65,
            },
        ),
        ('{"score":1.0}', {"score": 1}),
        ('{"score":0.1}', {"score": 0.1}),
        ('{"score":1e+21}', {"score": Decimal("1e21")}),
        ('{"name":"é"}', {"name": "é"}),
        (
            '{"flag":true,"empty":[],"object":{}}',
            {"flag": True, "empty": [], "object": {}},
        ),
    ),
)
def test_native_independent_comparison_proves_exact_semantic_equality(
    payload, candidate
):
    assert (
        compare_independent_native_payloads(_reference(payload), candidate)
        == "proven_equal"
    )


@pytest.mark.parametrize(
    ("payload", "candidate"),
    (
        ('{"score":1e400}', {"score": 1}),
        ('{"score":1}', {"score": float("inf")}),
        ('{"score":0}', {"score": -0.0}),
        ('{"score":1}', {"score": 9007199254740993}),
    ),
)
def test_native_numeric_domain_ineligibility_is_not_misreported_as_inequality(
    payload, candidate
):
    with pytest.raises(NativeEquivalenceIneligibleError):
        compare_independent_native_payloads(_reference(payload), candidate)


@pytest.mark.parametrize(
    "candidate",
    (
        {1: "non-string-key"},
        {"value": object()},
        {"value": (1, 2)},
        {"value": "\ud800"},
    ),
)
def test_non_json_native_payload_is_ineligible(candidate):
    with pytest.raises(NativeEquivalenceIneligibleError):
        compare_independent_native_payloads(_reference("{}"), candidate)


def test_comparison_requires_an_independent_strict_reference():
    with pytest.raises(TypeError, match="StrictParsedJson"):
        compare_independent_native_payloads({"score": 1}, {"score": 1})


@pytest.mark.parametrize("cycle_kind", ("list", "dict", "list_dict", "deep"))
def test_cyclic_native_payload_is_ineligible(cycle_kind):
    if cycle_kind == "list":
        candidate = []
        candidate.append(candidate)
    elif cycle_kind == "dict":
        candidate = {}
        candidate["self"] = candidate
    elif cycle_kind == "list_dict":
        candidate = []
        child = {"parent": candidate}
        candidate.append(child)
    else:
        candidate = []
        cursor = candidate
        for _ in range(100):
            child = []
            cursor.append(child)
            cursor = child
        cursor.append(candidate)

    with pytest.raises(NativeEquivalenceIneligibleError, match="cycle"):
        compare_independent_native_payloads(_reference("[]"), candidate)


def test_shared_acyclic_native_child_is_materialized_as_json_tree():
    shared = {"value": 1}
    candidate = [shared, shared]

    assert (
        compare_independent_native_payloads(
            _reference('[{"value":1},{"value":1}]'),
            candidate,
        )
        == "proven_equal"
    )


def test_ordinary_deep_native_tree_remains_eligible():
    candidate = {"value": 1}
    for _ in range(100):
        candidate = {"child": candidate}

    payload = '{"value":1}'
    for _ in range(100):
        payload = '{"child":' + payload + "}"

    assert compare_independent_native_payloads(_reference(payload), candidate) == (
        "proven_equal"
    )
