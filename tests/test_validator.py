
from datetime import date

from pawpal_system import Pet
from task_validator import validate_task_proposals


def create_pet():
    return Pet("P001", "Mochi", "Dog")


def create_valid_task():
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


def test_valid_task():
    result = validate_task_proposals(
        [create_valid_task()],
        [create_pet()],
        date(2026, 11, 21)
    )

    assert result["valid"] is True
    assert len(result["tasks"]) == 1
    assert result["errors"] == []


def test_unknown_pet():
    task = create_valid_task()
    task["pet_name"] = "Max"

    result = validate_task_proposals(
        [task],
        [create_pet()],
        date(2026, 11, 21)
    )

    assert result["valid"] is False
    assert result["tasks"] == []
    assert any("Unknown pet" in error for error in result["errors"])


def test_invalid_duration():
    task = create_valid_task()
    task["duration"] = 300

    result = validate_task_proposals(
        [task],
        [create_pet()],
        date(2026, 11, 21)
    )

    assert result["valid"] is False
    assert any("Duration must be between" in error for error in result["errors"])


def test_invalid_task_type():
    task = create_valid_task()
    task["task_type"] = "Swimming"

    result = validate_task_proposals(
        [task],
        [create_pet()],
        date(2026, 11, 21)
    )

    assert result["valid"] is False
    assert any("Unsupported task type" in error for error in result["errors"])


def test_invalid_time():
    task = create_valid_task()
    task["time"] = "25:99"

    result = validate_task_proposals(
        [task],
        [create_pet()],
        date(2026, 11, 21)
    )

    assert result["valid"] is False
    assert any("24-hour" in error for error in result["errors"])


def test_past_due_date():
    task = create_valid_task()
    task["due_date"] = "2026-11-20"

    result = validate_task_proposals(
        [task],
        [create_pet()],
        date(2026, 11, 21)
    )

    assert result["valid"] is False
    assert any("past" in error for error in result["errors"])


def test_empty_proposals():
    result = validate_task_proposals(
        [],
        [create_pet()],
        date(2026, 11, 21)
    )

    assert result["valid"] is False
    assert result["tasks"] == []
    assert len(result["errors"]) > 0
