"""Tests for the retry loop: the AI gets to correct a failed proposal."""

import json
from datetime import date

import ai_workflow
import eval_ai
from pawpal_system import Owner, Pet, Task


TODAY = date(2026, 11, 21)


def make_owner():
    owner = Owner("O001", "Alex")
    owner.add_pet(Pet("P001", "Mochi", "dog"))
    return owner


def good_task(**overrides):
    task = {
        "pet_name": "Mochi",
        "title": "Morning Walk",
        "task_type": "Exercise",
        "duration": 30,
        "priority": "medium",
        "time": "07:00",
        "frequency": "daily",
        "due_date": "2026-11-22",
    }
    task.update(overrides)
    return task


def reply(*tasks):
    return {
        "needs_clarification": False,
        "clarification_question": "",
        "tasks": list(tasks),
    }


GOOD = reply(good_task())
BAD = reply(good_task(pet_name="Rex"))                 # unknown pet
CLARIFY = {
    "needs_clarification": True,
    "clarification_question": "Which pet do you mean?",
    "tasks": [],
}


def sequence_parser(monkeypatch, replies):
    """Return each reply in turn (the last one repeats). Records calls."""
    calls = []

    def parser(**kwargs):
        calls.append(kwargs)
        item = replies[min(len(calls) - 1, len(replies) - 1)]

        if isinstance(item, Exception):
            raise item

        return item

    monkeypatch.setattr(ai_workflow, "parse_task_request", parser)
    return calls


def run(owner=None, **kwargs):
    return ai_workflow.process_ai_task_request(
        "Walk Mochi", owner or make_owner(), TODAY, **kwargs
    )


# ---------- no retry needed ----------

def test_valid_first_attempt_makes_one_call(monkeypatch):
    calls = sequence_parser(monkeypatch, [GOOD])

    result = run()

    assert result["status"] == "success"
    assert result["attempts"] == 1
    assert result["retried"] is False
    assert result["retry_notes"] == []
    assert len(calls) == 1
    assert "extra_messages" not in calls[0]


def test_clarification_is_not_retried(monkeypatch):
    calls = sequence_parser(monkeypatch, [CLARIFY])

    result = run()

    assert result["status"] == "clarification"
    assert result["attempts"] == 1
    assert len(calls) == 1


# ---------- the AI corrects itself ----------

def test_second_attempt_can_fix_the_proposal(monkeypatch):
    calls = sequence_parser(monkeypatch, [BAD, GOOD])

    result = run()

    assert result["status"] == "success"
    assert result["attempts"] == 2
    assert result["retried"] is True
    assert result["tasks"][0]["pet_name"] == "Mochi"
    assert len(calls) == 2


def test_retry_is_flagged_so_the_user_reviews_it(monkeypatch):
    sequence_parser(monkeypatch, [BAD, GOOD])

    result = run()

    assert "corrected" in result["message"].lower()
    assert any("Unknown pet" in note for note in result["retry_notes"])


def test_third_attempt_can_fix_the_proposal(monkeypatch):
    calls = sequence_parser(monkeypatch, [BAD, BAD, GOOD])

    result = run(max_retries=2)

    assert result["status"] == "success"
    assert result["attempts"] == 3
    assert len(calls) == 3


def test_retry_can_end_in_a_clarifying_question(monkeypatch):
    sequence_parser(monkeypatch, [BAD, CLARIFY])

    result = run()

    assert result["status"] == "clarification"
    assert result["message"] == "Which pet do you mean?"
    assert result["attempts"] == 2
    assert result["tasks"] == []


# ---------- the AI cannot fix it ----------

def test_gives_up_after_max_retries(monkeypatch):
    calls = sequence_parser(monkeypatch, [BAD])

    result = run(max_retries=2)

    assert result["status"] == "invalid"
    assert result["tasks"] == []
    assert result["attempts"] == 3
    assert len(calls) == 3
    assert any("Unknown pet" in error for error in result["errors"])


def test_max_retries_zero_turns_the_loop_off(monkeypatch):
    calls = sequence_parser(monkeypatch, [BAD, GOOD])

    result = run(max_retries=0)

    assert result["status"] == "invalid"
    assert result["attempts"] == 1
    assert len(calls) == 1


def test_failure_during_retry_keeps_the_validation_errors(monkeypatch):
    sequence_parser(monkeypatch, [BAD, RuntimeError("API down")])

    result = run()

    assert result["status"] == "invalid"
    assert any("Unknown pet" in e for e in result["errors"])
    assert any("Retry failed: API down" in e for e in result["errors"])


def test_failure_on_first_call_is_still_an_error(monkeypatch):
    sequence_parser(monkeypatch, [RuntimeError("API down")])

    result = run()

    assert result["status"] == "error"
    assert result["attempts"] == 1


def test_non_object_response_is_treated_as_invalid(monkeypatch):
    sequence_parser(monkeypatch, [["not", "an", "object"]])

    result = run(max_retries=0)

    assert result["status"] == "invalid"


# ---------- what the AI is told ----------

def test_retry_sends_the_errors_and_the_previous_answer(monkeypatch):
    calls = sequence_parser(monkeypatch, [BAD, GOOD])

    run()

    messages = calls[1]["extra_messages"]

    assert [m["role"] for m in messages] == ["assistant", "user"]
    assert json.loads(messages[0]["content"]) == BAD
    assert "Unknown pet" in messages[1]["content"]


def test_retry_tells_the_ai_not_to_change_the_request(monkeypatch):
    calls = sequence_parser(monkeypatch, [BAD, GOOD])

    run()

    feedback = calls[1]["extra_messages"][1]["content"]

    assert "do not change what i asked for" in feedback.lower()
    assert "needs_clarification to true" in feedback


def test_each_retry_shows_the_latest_errors(monkeypatch):
    other_bad = reply(good_task(duration=999))
    calls = sequence_parser(monkeypatch, [BAD, other_bad, GOOD])

    run(max_retries=2)

    assert "Unknown pet" in calls[1]["extra_messages"][1]["content"]
    assert "Duration" in calls[2]["extra_messages"][1]["content"]


def test_retry_feedback_truncates_long_errors():
    messages = ai_workflow.build_retry_messages(BAD, ["x" * 1000])

    assert len(messages[1]["content"]) < 900


# ---------- safety still holds ----------

def test_nothing_is_saved_even_after_a_retry(monkeypatch):
    owner = make_owner()
    sequence_parser(monkeypatch, [BAD, GOOD])

    result = run(owner)

    assert result["status"] == "success"
    assert owner.get_all_tasks() == []


def test_a_corrected_proposal_still_gets_a_conflict_check(monkeypatch):
    owner = make_owner()
    owner.pets[0].add_task(Task(
        "Breakfast", "Feeding", 10, "high", "07:00",
        due_date=date(2026, 11, 22)
    ))
    sequence_parser(monkeypatch, [BAD, GOOD])

    result = run(owner)

    assert result["status"] == "success"
    assert len(result["conflicts"]) == 1
    assert "Breakfast" in result["conflicts"][0]


def test_a_retry_cannot_sneak_in_an_invalid_task(monkeypatch):
    """If the retry is still invalid, it is rejected like any other."""
    still_bad = reply(good_task(duration=999))
    sequence_parser(monkeypatch, [BAD, still_bad])

    result = run(max_retries=1)

    assert result["status"] == "invalid"
    assert result["tasks"] == []


# ---------- trace ----------

def test_trace_records_every_attempt(monkeypatch):
    sequence_parser(monkeypatch, [BAD, GOOD])

    result = run()
    trace = result["trace"]

    assert [step["attempt"] for step in trace] == [1, 2]
    assert [step["outcome"] for step in trace] == ["invalid", "valid"]
    assert trace[0]["ai_output"] == BAD
    assert any("Unknown pet" in e for e in trace[0]["errors"])
    assert trace[1]["errors"] == []


def test_trace_is_recorded_for_a_clarification(monkeypatch):
    sequence_parser(monkeypatch, [CLARIFY])

    trace = run()["trace"]

    assert len(trace) == 1
    assert trace[0]["outcome"] == "clarification"


# ---------- eval harness integration ----------

def test_eval_traces_are_written_as_markdown(tmp_path):
    records = eval_ai.run_all(parse_fn=eval_ai.dry_run_parser)
    path = str(tmp_path / "ai_interactions.md")

    eval_ai.write_traces(path, records, "DRY RUN (simulated model)")

    text = open(path, encoding="utf-8").read()

    assert text.startswith("# AI Interaction Traces")
    assert "### Attempt 1: invalid" in text
    assert "### Attempt 2: clarification" in text
    assert "```json" in text
    assert "Feed Rex for 10 minutes tomorrow at 6 PM." in text
    assert "Simulated model replies" in text


def test_eval_report_shows_retried_cases():
    records = eval_ai.run_all(parse_fn=eval_ai.dry_run_parser)
    report = eval_ai.format_report(records, "DRY RUN (simulated model)", 1)

    assert "Model calls" in report
    assert "Validator, then AI asked a question" in report
    assert "validation failed and the AI was asked to retry" in report