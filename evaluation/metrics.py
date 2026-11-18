"""Metrics for answer, citation, abstention, and operational evaluation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import TypeVar

T = TypeVar("T")


def citation_accuracy(
    cited_chunk_ids: list[str],
    retrieved_chunk_ids: list[str],
    relevant_chunk_ids: set[str],
) -> float:
    """Return the fraction of citations that are retrieved and relevant."""
    if not cited_chunk_ids:
        return 0.0
    retrieved = set(retrieved_chunk_ids)
    return sum(
        chunk_id in retrieved and chunk_id in relevant_chunk_ids
        for chunk_id in cited_chunk_ids
    ) / len(cited_chunk_ids)


def groundedness_score(claims: list[bool]) -> float:
    """Return the fraction of manually reviewed claims supported by evidence."""
    if not claims:
        return 0.0
    return sum(claims) / len(claims)


def answer_correctness_score(labels: list[bool]) -> float:
    """Return the fraction of manually reviewed answers judged correct."""
    if not labels:
        return 0.0
    return sum(labels) / len(labels)


@dataclass(frozen=True)
class AbstentionMetrics:
    accuracy: float
    precision: float
    recall: float


def abstention_metrics(
    expected_unanswerable: list[bool],
    actual_abstained: list[bool],
) -> AbstentionMetrics:
    """Measure abstention as the positive class."""
    if len(expected_unanswerable) != len(actual_abstained):
        raise ValueError("Expected and actual abstention labels must have equal length.")
    if not expected_unanswerable:
        return AbstentionMetrics(accuracy=0.0, precision=0.0, recall=0.0)

    true_positive = sum(
        expected and actual
        for expected, actual in zip(expected_unanswerable, actual_abstained)
    )
    false_positive = sum(
        not expected and actual
        for expected, actual in zip(expected_unanswerable, actual_abstained)
    )
    false_negative = sum(
        expected and not actual
        for expected, actual in zip(expected_unanswerable, actual_abstained)
    )
    accuracy = sum(
        expected == actual
        for expected, actual in zip(expected_unanswerable, actual_abstained)
    )
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    return AbstentionMetrics(
        accuracy=accuracy / len(expected_unanswerable),
        precision=precision,
        recall=recall,
    )


def timed_call(function: Callable[[], T]) -> tuple[T, float]:
    """Run a callable and return its result with elapsed wall-clock seconds."""
    started = perf_counter()
    result = function()
    return result, perf_counter() - started
