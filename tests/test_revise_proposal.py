from datetime import date

import pytest

from pawpal_system import Owner, Pet, Task
from ai_workflow import revise_proposal


TODAY = date(2026, 11, 21)


def make_owner():
    owner = Owner("O001", "Alex")
    owner.add_pet(Pet("P001", "Mochi", "dog"))
    owner.add_pet(Pet("P002", "Whiskers", "cat"))
    return owner


def proposal(**overrides):
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


def test_valid_edit_is_accepted():
    owner = make_owner()

    result = revise_proposal(
        owner, [proposal(title="Long walk", time="07:30")], TODAY
    )

    assert result["status"] == "success"
    assert result["errors"] == []
    assert result["tasks"][0]["title"] == "Long walk"
    assert result["tasks"][0]["time"] == "07:30"


def test_edits_are_normalized_like_ai_output():
    owner = make_owner()

    result = revise_proposal(
        owner,
        [proposal(pet_name="whiskers", priority="HIGH",
                  task_type="grooming", title="  Brush  ")],
        TODAY
    )

    task = result["tasks"][0]

    assert result["status"] == "success"
    assert task["pet_name"] == "Whiskers"
    assert task["priority"] == "high"
    assert task["task_type"] == "Grooming"
    assert task["title"] == "Brush"


@pytest.mark.parametrize("bad_fields", [
    {"pet_name": "Rex"},
    {"title": ""},
    {"title": "x" * 101},
    {"task_type": "Swimming"},
    {"duration": 0},
    {"duration": 300},
    {"priority": "urgent"},
    {"time": "25:99"},
    {"frequency": "monthly"},
    {"due_date": "2026-11-20"},
    {"due_date": "not a date"},
])
def test_invalid_edits_are_rejected(bad_fields):
    owner = make_owner()

    result = revise_proposal(owner, [proposal(**bad_fields)], TODAY)

    assert result["status"] == "invalid"
    assert result["tasks"] == []
    assert result["errors"]


def test_one_bad_task_rejects_the_whole_edit():
    owner = make_owner()

    result = revise_proposal(
        owner, [proposal(), proposal(title="Bad", duration=999)], TODAY
    )

    assert result["status"] == "invalid"
    assert result["tasks"] == []


def test_empty_edit_is_rejected():
    result = revise_proposal(make_owner(), [], TODAY)

    assert result["status"] == "invalid"


def test_revising_never_saves_anything():
    owner = make_owner()

    revise_proposal(owner, [proposal()], TODAY)

    assert owner.get_all_tasks() == []


def test_editing_into_a_conflict_is_reported():
    owner = make_owner()
    owner.pets[1].add_task(Task(
        "Feed cat", "Feeding", 10, "high", "08:00",
        due_date=date(2026, 11, 22)
    ))

    clear = revise_proposal(owner, [proposal(time="07:00")], TODAY)
    clashing = revise_proposal(owner, [proposal(time="08:00")], TODAY)

    assert clear["conflicts"] == []
    assert len(clashing["conflicts"]) == 1
    assert "Feed cat" in clashing["conflicts"][0]
    assert "Whiskers" in clashing["conflicts"][0]


def test_conflict_between_two_edited_proposals():
    owner = make_owner()

    result = revise_proposal(
        owner,
        [proposal(title="Walk"), proposal(title="Breakfast")],
        TODAY
    )

    assert result["status"] == "success"
    assert len(result["conflicts"]) == 1


def test_reassigning_to_another_pet_changes_conflicts():
    owner = make_owner()
    owner.pets[0].add_task(Task(
        "Breakfast", "Feeding", 10, "high", "07:00",
        due_date=date(2026, 11, 22)
    ))

    result = revise_proposal(
        owner, [proposal(pet_name="Whiskers")], TODAY
    )

    # Still a conflict: one owner cannot do both at once.
    assert len(result["conflicts"]) == 1
    assert "Whiskers" in result["conflicts"][0]
    assert "Mochi" in result["conflicts"][0]