"""
Metric definitions and statistical aggregation utilities for agent evaluation.
"""
import math
from typing import List, Dict, Any

# Standard pricing for gpt-4o-mini / gemini-flash
# Input: $0.15 / 1M tokens ($0.00015 / 1k tokens)
# Output: $0.60 / 1M tokens ($0.00060 / 1k tokens)
INPUT_PRICE_PER_TOKEN = 0.15 / 1_000_000
OUTPUT_PRICE_PER_TOKEN = 0.60 / 1_000_000

# Estimated average tokens per call if token usage is not explicitly tracked
ESTIMATED_PROMPT_TOKENS_PER_CALL = 650
ESTIMATED_COMPLETION_TOKENS_PER_CALL = 120


def calculate_cost(
    prompt_tokens: int, completion_tokens: int
) -> float:
    """Calculate USD cost from token counts."""
    return (prompt_tokens * INPUT_PRICE_PER_TOKEN) + (
        completion_tokens * OUTPUT_PRICE_PER_TOKEN
    )


def mean(numbers: List[float]) -> float:
    """Calculate mean of numbers."""
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def std_dev(numbers: List[float]) -> float:
    """Calculate sample standard deviation."""
    if len(numbers) < 2:
        return 0.0
    avg = mean(numbers)
    variance = sum((x - avg) ** 2 for x in numbers) / (len(numbers) - 1)
    return math.sqrt(variance)


def aggregate_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregate run results across metrics:
    - success_rate
    - latency (mean, std, min, max)
    - llm_invocations (mean, std)
    - tool_calls (mean, std)
    - estimated_cost (total, avg_per_run)
    """
    if not results:
        return {}

    total_runs = len(results)
    successes = sum(1 for r in results if r.get("success", False))
    success_rate = (successes / total_runs) * 100.0

    latencies = [r["latency_sec"] for r in results]
    llm_calls = [r["llm_invocations"] for r in results]
    tool_calls = [r["tool_calls"] for r in results]
    costs = [r.get("cost_usd", 0.0) for r in results]

    return {
        "total_runs": total_runs,
        "success_rate_percent": round(success_rate, 2),
        "latency_sec": {
            "mean": round(mean(latencies), 3),
            "std": round(std_dev(latencies), 3),
            "min": round(min(latencies), 3),
            "max": round(max(latencies), 3),
        },
        "llm_invocations": {
            "mean": round(mean(llm_calls), 2),
            "std": round(std_dev(llm_calls), 2),
            "min": min(llm_calls),
            "max": max(llm_calls),
        },
        "tool_calls": {
            "mean": round(mean(tool_calls), 2),
            "std": round(std_dev(tool_calls), 2),
            "min": min(tool_calls),
            "max": max(tool_calls),
        },
        "estimated_cost_usd": {
            "mean": round(mean(costs), 6),
            "total": round(sum(costs), 6),
        },
    }
