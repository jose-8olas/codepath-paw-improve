from datetime import date

from pawpal_system import Owner, Pet, Task
import ai_workflow


TODAY = date(2026, 11, 21)


def create_owner():
    owner = Owner("O001", "Alex")
    pet = Pet("P001", "Mochi", "Dog")
    owner.add_pet(pet)
    return owner


def create_valid_proposal():
    return {
        "pet_name": "Mochi",
        "title": "Morning Walk",
        "task_type": "Exercise",
        "duration": 30,
        "priority": "medium",
        "time": "07:00",
        "frequency": "daily",
        "due_date": "2026-11-22"
    }


def mock_parser(monkeypatch, tasks):
    monkeypatch.setattr(
        ai_workflow,
        "parse_task_request",
        lambda **kwargs: {
            "needs_clarification": False,
            "clarification_question": "",
            "tasks": tasks
        }
    )


def mock_successful_parser(monkeypatch):
    mock_parser(monkeypatch, [create_valid_proposal()])


def test_successful_workflow(monkeypatch):
    owner = create_owner()
    mock_successful_parser(monkeypatch)

    result = ai_workflow.process_ai_task_request(
        "Schedule a morning walk for Mochi", owner, TODAY
    )

    assert result["status"] == "success"
    assert len(result["tasks"]) == 1
    assert result["errors"] == []
    assert result["tasks"][0]["title"] == "Morning Walk"


def test_nothing_saved_without_approval(monkeypatch):
    """Core guardrail: the workflow only proposes, it never saves."""
    owner = create_owner()
    mock_successful_parser(monkeypatch)

    result = ai_workflow.process_ai_task_request(
        "Schedule a morning walk for Mochi", owner, TODAY
    )

    assert result["status"] == "success"
    assert owner.pets[0].tasks == []
    assert owner.get_all_tasks() == []


def test_clarification_request(monkeypatch):
    owner = create_owner()

    monkeypatch.setattr(
        ai_workflow,
        "parse_task_request",
        lambda **kwargs: {
            "needs_clarification": True,
            "clarification_question": "What time should the walk be?",
            "tasks": []
        }
    )

    result = ai_workflow.process_ai_task_request(
        "Schedule a walk for Mochi", owner, TODAY
    )

    assert result["status"] == "clarification"
    assert result["message"] == "What time should the walk be?"
    assert result["tasks"] == []
    assert owner.pets[0].tasks == []


def test_invalid_proposal_rejected(monkeypatch):
    owner = create_owner()

    invalid_proposal = create_valid_proposal()
    invalid_proposal["pet_name"] = "Unknown Pet"

    mock_parser(monkeypatch, [invalid_proposal])

    result = ai_workflow.process_ai_task_request(
        "Schedule a walk", owner, TODAY
    )

    assert result["status"] == "invalid"
    assert result["tasks"] == []
    assert len(result["errors"]) > 0
    assert owner.pets[0].tasks == []


def test_parser_error_handling(monkeypatch):
    owner = create_owner()

    def failing_parser(**kwargs):
        raise Exception("API connection failed")

    monkeypatch.setattr(
        ai_workflow, "parse_task_request", failing_parser
    )

    result = ai_workflow.process_ai_task_request(
        "Schedule a walk", owner, TODAY
    )

    assert result["status"] == "error"
    assert "API connection failed" in result["message"]
    assert result["tasks"] == []


def test_scheduling_conflict_detected(monkeypatch):
    owner = create_owner()

    existing_task = Task(
        title="Breakfast",
        task_type="Feeding",
        duration=10,
        priority="High",
        time="07:00",
        due_date=date(2026, 11, 22)
    )

    owner.pets[0].add_task(existing_task)

    mock_successful_parser(monkeypatch)

    result = ai_workflow.process_ai_task_request(
        "Schedule a morning walk for Mochi", owner, TODAY
    )

    assert result["status"] == "success"
    assert len(result["tasks"]) == 1
    assert len(result["conflicts"]) == 1

    warning = result["conflicts"][0]
    assert "Breakfast" in warning
    assert "Morning Walk" in warning
    assert "Mochi" in warning
    assert "07:00" in warning


def test_preexisting_conflicts_are_not_reported(monkeypatch):
    """Two old tasks share 09:00, but the proposal is at 07:00."""
    owner = create_owner()

    for title in ("Medication", "Grooming"):
        owner.pets[0].add_task(Task(
            title=title,
            task_type="Other",
            duration=10,
            priority="low",
            time="09:00",
            due_date=date(2026, 11, 22)
        ))

    mock_successful_parser(monkeypatch)

    result = ai_workflow.process_ai_task_request(
        "Schedule a morning walk for Mochi", owner, TODAY
    )

    assert result["status"] == "success"
    assert result["conflicts"] == []


def test_conflict_between_two_proposals(monkeypatch):
    owner = create_owner()

    second = create_valid_proposal()
    second["title"] = "Breakfast"

    mock_parser(monkeypatch, [create_valid_proposal(), second])

    result = ai_workflow.process_ai_task_request(
        "Walk and feed Mochi at 7", owner, TODAY
    )

    assert result["status"] == "success"
    assert len(result["conflicts"]) == 1
    assert "Morning Walk" in result["conflicts"][0]
    assert "Breakfast" in result["conflicts"][0]


def test_conflict_across_different_pets(monkeypatch):
    owner = create_owner()

    whiskers = Pet("P002", "Whiskers", "Cat")
    whiskers.add_task(Task(
        title="Feed cat",
        task_type="Feeding",
        duration=10,
        priority="high",
        time="07:00",
        due_date=date(2026, 11, 22)
    ))
    owner.add_pet(whiskers)

    mock_successful_parser(monkeypatch)

    result = ai_workflow.process_ai_task_request(
        "Schedule a morning walk for Mochi", owner, TODAY
    )

    assert len(result["conflicts"]) == 1
    assert "Whiskers" in result["conflicts"][0]
    assert "Mochi" in result["conflicts"][0]


def test_completed_tasks_do_not_conflict(monkeypatch):
    owner = create_owner()

    done = Task(
        title="Breakfast",
        task_type="Feeding",
        duration=10,
        priority="high",
        time="07:00",
        completed=True,
        due_date=date(2026, 11, 22)
    )
    owner.pets[0].add_task(done)

    mock_successful_parser(monkeypatch)

    result = ai_workflow.process_ai_task_request(
        "Schedule a morning walk for Mochi", owner, TODAY
    )

    assert result["conflicts"] == []


def test_different_date_does_not_conflict(monkeypatch):
    owner = create_owner()

    owner.pets[0].add_task(Task(
        title="Breakfast",
        task_type="Feeding",
        duration=10,
        priority="high",
        time="07:00",
        due_date=date(2026, 11, 23)
    ))

    mock_successful_parser(monkeypatch)

    result = ai_workflow.process_ai_task_request(
        "Schedule a morning walk for Mochi", owner, TODAY
    )

    assert result["conflicts"] == []