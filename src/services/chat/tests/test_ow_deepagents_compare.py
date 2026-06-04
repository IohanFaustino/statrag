"""CI unit tests for the Plan C deepagents comparison (pure helpers only)."""
from src.services.chat.agents import ow_deepagents as DA


def test_sum_usage_totals():
    meta = {"gpt-5.4-nano-2026-03-17": {"input_tokens": 100, "output_tokens": 40, "total_tokens": 140},
            "other": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}
    assert DA._sum_usage(meta) == (110, 45)


def test_sum_usage_empty():
    assert DA._sum_usage({}) == (0, 0)
    assert DA._sum_usage(None) == (0, 0)
