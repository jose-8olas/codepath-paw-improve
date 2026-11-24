from datetime import date

import pytest

import ai_workflow
from pawpal_system import Owner, Pet, Scheduler, Task
from task_validator import time_ranges_overlap, validate_task_proposals


TODAY = date(2026, 11, 21)
TOMORROW = date(2026, 11, 22)


def make_task(title, time, duration, due=TOMORROW, completed=False):
    return Task(
        title, "Exercise", duration, "medium", time,
        due_date=due, completed=completed
    )


def make_owner(*tasks):
    owner = Owner("O001", "Alex")
    pet = Pet("P001", "Mochi", "Dog")
    for task in tasks:
        pet.add_task(task)
    owner.add_pet(pet)
    return owner


def proposal(time="07:15", duration=30, title="New"):
    return {
        "pet_name": "Mochi", "title": title, "task_type": "Exercise",
        "duration": duration, "priority": "medium", "time": time,
        "frequency": "daily", "due_date": "2026-11-22",
    }


@pytest.mark.parametrize("a,da,b,db,expected", [
    ("07:00", 60, "07:30", 15, True),    # second starts inside first
    ("07:30", 15, "07:00", 60, True),    # order does not matter
    ("07:00", 30, "07:00", 30, True),    # same start
    ("07:00", 30, "07:30", 30, False),   # back to back is fine
    ("07:00", 30, "08:00", 30, False),   # clear gap
    ("7:00", 60, "07:59", 5, True),      # single digit hour
])
def test_time_ranges_overlap(a, da, b, db, expected):
    assert time_ranges_overlap(a, da, b, db) is expected


def test_overlapping_durations_conflict_with_existing_task():
    owner = make_owner(make_task("Long walk", "07:00", 60))

    conflicts = ai_workflow.find_proposal_conflicts(
        owner, [proposal("07:30", 15)]
    )

    assert len(conflicts) == 1
    assert "overlaps" in conflicts[0]


def test_back_to_back_proposal_is_not_a_conflict():
    owner = make_owner(make_task("Walk", "07:00", 30))

    assert ai_workflow.find_proposal_conflicts(
        owner, [proposal("07:30", 30)]
    ) == []


def test_two_overlapping_proposals_conflict():
    owner = make_owner()

    conflicts = ai_workflow.find_proposal_conflicts(
        owner, [proposal("07:00", 60, "A"), proposal("07:30", 15, "B")]
    )

    assert len(conflicts) == 1


def test_overlap_on_a_different_day_is_ignored():
    owner = make_owner(make_task("Walk", "07:00", 60, due=TODAY))

    assert ai_workflow.find_proposal_conflicts(
        owner, [proposal("07:30", 15)]
    ) == []


def test_completed_task_does_not_conflict():
    owner = make_owner(make_task("Walk", "07:00", 60, completed=True))

    assert ai_workflow.find_proposal_conflicts(
        owner, [proposal("07:30", 15)]
    ) == []


def test_find_conflicting_tasks_uses_durations():
    long_walk = make_task("Long walk", "07:00", 60)
    short = make_task("Treat", "07:30", 5)
    later = make_task("Dinner", "08:00", 10)
    owner = make_owner(long_walk, short, later)

    names = [t.title for _, t in owner.find_conflicting_tasks(short)]

    assert names == ["Long walk"]


def test_scheduler_warns_about_overlaps_not_just_equal_times():
    owner = make_owner(
        make_task("Long walk", "07:00", 60),
        make_task("Treat", "07:30", 5),
        make_task("Dinner", "08:00", 10),
    )

    scheduler = Scheduler(480)
    scheduler.get_tasks_from_owner(owner)
    warnings = scheduler.detect_time_conflicts()

    assert len(warnings) == 1
    assert "Long walk" in warnings[0] and "Treat" in warnings[0]


def test_validator_accepts_and_normalizes_single_digit_hour():
    pets = [Pet("P001", "Mochi", "Dog")]
    item = proposal("7:00")

    result = validate_task_proposals([item], pets, TODAY)

    assert result["valid"] is True
    assert result["tasks"][0]["time"] == "07:00"


def test_normalized_time_can_be_used_to_update_a_task():
    task = make_task("Walk", "07:00", 30)
    pets = [Pet("P001", "Mochi", "Dog")]
    clean = validate_task_proposals([proposal("7:05")], pets, TODAY)

    task.update(time=clean["tasks"][0]["time"])

    assert task.time == "07:05"


def test_validator_still_rejects_bad_times():
    pets = [Pet("P001", "Mochi", "Dog")]

    for bad in ["25:00", "7am", "07:61", ""]:
        result = validate_task_proposals([proposal(bad)], pets, TODAY)
        assert result["valid"] is False