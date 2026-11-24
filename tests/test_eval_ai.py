"""Tests for the evaluation harness itself (no API key needed)."""

import ai_workflow
import eval_ai


def test_dry_run_passes_every_case():
    records = eval_ai.run_all(parse_fn=eval_ai.dry_run_parser)

    assert len(records) == len(eval_ai.CASES)
    assert all(record["passed"] for record in records)


def test_dry_run_exercises_the_retry_loop():
    records = eval_ai.run_all(parse_fn=eval_ai.dry_run_parser)
    statuses = {record["statuses"][0] for record in records}

    assert "clarification" in statuses   # AI asked a question
    assert "success" in statuses

    # Cases the validator rejected were retried, so they took 2 calls.
    retried = [r for r in records if r["attempts"][0] > 1]
    assert retried
    assert all(r["trace"][0]["outcome"] == "invalid" for r in retried)


def test_harness_detects_a_model_that_invents_details():
    """A model that always proposes a task must fail the guardrail cases."""

    def overeager_parser(user_request, pets, current_date,
                         extra_messages=None):
        return eval_ai._success(
            eval_ai._task("Mochi", "Walk", "Exercise", 30, "medium",
                          "07:00", "2026-11-22")
        )

    records = eval_ai.run_all(parse_fn=overeager_parser)
    by_name = {record["name"]: record for record in records}

    assert by_name["Missing time"]["passed"] is False
    assert by_name["Vague request"]["passed"] is False
    assert by_name["Prompt injection"]["passed"] is False
    assert any(record["problems"] for record in records)


def test_harness_flags_api_errors_as_failures():
    def broken_parser(user_request, pets, current_date,
                      extra_messages=None):
        raise RuntimeError("API down")

    records = eval_ai.run_all(parse_fn=broken_parser)

    assert all(record["statuses"][0] == "error" for record in records)
    assert not any(record["passed"] for record in records)


def test_nothing_is_saved_during_evaluation():
    records = eval_ai.run_all(parse_fn=eval_ai.dry_run_parser)

    assert all(record["nothing_saved"] for record in records)


def test_repeat_runs_are_counted():
    records = eval_ai.run_all(parse_fn=eval_ai.dry_run_parser, repeat=3)

    assert all(record["runs"] == 3 for record in records)
    assert all(record["passes"] == 3 for record in records)


def test_run_all_restores_the_real_parser():
    original = ai_workflow.parse_task_request

    eval_ai.run_all(parse_fn=eval_ai.dry_run_parser)

    assert ai_workflow.parse_task_request is original


def test_report_contains_summary_and_table():
    records = eval_ai.run_all(parse_fn=eval_ai.dry_run_parser)
    report = eval_ai.format_report(records, "DRY RUN (simulated model)", 1)

    assert "Cases passed: 11/11" in report
    assert "| 1 | Clear request |" in report
    assert "Nothing saved without approval: PASS" in report
    assert "NOT evidence about the real model" in report