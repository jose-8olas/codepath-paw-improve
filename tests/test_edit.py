from datetime import date

import pytest

from pawpal_system import Owner, Pet, Task


DAY = date(2026, 11, 22)


def make_task(title="Walk", time="08:00", completed=False, due_date=DAY):
    return Task(
        title, "Exercise", 30, "high", time,
        frequency="daily", completed=completed, due_date=due_date
    )


def make_owner():
    owner = Owner("O001", "Alex")
    owner.add_pet(Pet("P001", "Mochi", "dog"))
    owner.add_pet(Pet("P002", "Whiskers", "cat"))
    return owner


# ---------- Task.update ----------

def test_update_changes_fields_and_reports_them():
    task = make_task()

    changes = task.update(title="Long walk", duration=45, priority="low")

    assert task.title == "Long walk"
    assert task.duration == 45
    assert task.priority == "low"
    assert changes == {
        "title": ("Walk", "Long walk"),
        "duration": (30, 45),
        "priority": ("high", "low"),
    }


def test_update_leaves_other_fields_alone():
    task = make_task()

    task.update(time="09:30")

    assert task.time == "09:30"
    assert task.title == "Walk"
    assert task.duration == 30
    assert task.due_date == DAY
    assert task.frequency == "daily"


def test_update_normalizes_values():
    task = make_task()

    task.update(
        title="  Brush fur  ", task_type="grooming",
        priority="HIGH ", frequency="Weekly"
    )

    assert task.title == "Brush fur"
    assert task.task_type == "Grooming"
    assert task.priority == "high"
    assert task.frequency == "weekly"


def test_update_with_same_values_reports_no_changes():
    task = make_task()

    assert task.update(title="Walk", duration=30, time="08:00") == {}


def test_update_with_nothing_given_changes_nothing():
    task = make_task()

    assert task.update() == {}
    assert task.title == "Walk"


def test_update_can_change_the_date():
    task = make_task()
    new_day = date(2026, 12, 1)

    changes = task.update(due_date=new_day)

    assert task.due_date == new_day
    assert changes == {"due_date": (DAY, new_day)}


@pytest.mark.parametrize("field_name, bad_value", [
    ("title", ""),
    ("title", "   "),
    ("title", "x" * 101),
    ("task_type", "Swimming"),
    ("duration", 0),
    ("duration", 241),
    ("duration", True),
    ("duration", "30"),
    ("duration", 12.5),
    ("priority", "urgent"),
    ("time", "25:00"),
    ("time", "7:00"),
    ("time", "8am"),
    ("time", "12:60"),
    ("frequency", "monthly"),
    ("due_date", "2026-11-22"),
])
def test_update_rejects_bad_values(field_name, bad_value):
    task = make_task()

    with pytest.raises(ValueError):
        task.update(**{field_name: bad_value})


def test_failed_update_changes_nothing():
    """One bad value means none of the other values are applied."""
    task = make_task()

    with pytest.raises(ValueError):
        task.update(title="New title", priority="high", duration=999)

    assert task.title == "Walk"
    assert task.duration == 30


def test_update_works_on_completed_tasks():
    task = make_task(completed=True)

    task.update(title="Renamed")

    assert task.title == "Renamed"
    assert task.completed is True


# ---------- Owner.update_pet ----------

def test_update_pet_renames_and_changes_species():
    owner = make_owner()

    assert owner.update_pet("P001", name="Mochi Jr", species="other") is True

    assert owner.pets[0].name == "Mochi Jr"
    assert owner.pets[0].species == "other"


def test_update_pet_unknown_id_returns_false():
    assert make_owner().update_pet("P999", name="Ghost") is False


def test_update_pet_rejects_duplicate_name_ignoring_case():
    owner = make_owner()

    with pytest.raises(ValueError):
        owner.update_pet("P001", name="whiskers")

    assert owner.pets[0].name == "Mochi"


def test_update_pet_allows_changing_own_name_case():
    owner = make_owner()

    owner.update_pet("P001", name="MOCHI")

    assert owner.pets[0].name == "MOCHI"


@pytest.mark.parametrize("kwargs", [
    {"name": ""},
    {"name": "   "},
    {"name": "x" * 51},
    {"species": ""},
])
def test_update_pet_rejects_empty_values(kwargs):
    owner = make_owner()

    with pytest.raises(ValueError):
        owner.update_pet("P001", **kwargs)

    assert owner.pets[0].name == "Mochi"
    assert owner.pets[0].species == "dog"


def test_failed_pet_update_changes_nothing():
    owner = make_owner()

    with pytest.raises(ValueError):
        owner.update_pet("P001", name="Rex", species="")

    assert owner.pets[0].name == "Mochi"


def test_renamed_pet_keeps_its_tasks():
    owner = make_owner()
    owner.pets[0].add_task(make_task("Walk"))

    owner.update_pet("P001", name="Buddy")

    assert [t.title for t in owner.pets[0].tasks] == ["Walk"]


# ---------- Owner.find_conflicting_tasks ----------

def test_conflicts_found_across_pets():
    owner = make_owner()
    walk = make_task("Walk", "08:00")
    feed = make_task("Feed cat", "08:00")
    owner.pets[0].add_task(walk)
    owner.pets[1].add_task(feed)

    conflicts = owner.find_conflicting_tasks(walk)

    assert [(pet.name, task.title) for pet, task in conflicts] == [
        ("Whiskers", "Feed cat")
    ]


def test_conflicts_ignore_the_task_itself():
    owner = make_owner()
    walk = make_task("Walk", "08:00")
    owner.pets[0].add_task(walk)

    assert owner.find_conflicting_tasks(walk) == []


def test_conflicts_ignore_completed_and_other_dates_and_times():
    owner = make_owner()
    walk = make_task("Walk", "08:00")
    owner.pets[0].add_task(walk)
    owner.pets[0].add_task(make_task("Done", "08:00", completed=True))
    owner.pets[0].add_task(make_task("Other day", "08:00",
                                     due_date=date(2026, 11, 23)))
    owner.pets[1].add_task(make_task("Other time", "09:00"))

    assert owner.find_conflicting_tasks(walk) == []


def test_completed_task_has_no_conflicts():
    owner = make_owner()
    done = make_task("Done", "08:00", completed=True)
    owner.pets[0].add_task(done)
    owner.pets[1].add_task(make_task("Feed cat", "08:00"))

    assert owner.find_conflicting_tasks(done) == []


def test_editing_a_time_creates_then_removes_a_conflict():
    owner = make_owner()
    walk = make_task("Walk", "07:00")
    feed = make_task("Feed cat", "08:00")
    owner.pets[0].add_task(walk)
    owner.pets[1].add_task(feed)

    assert owner.find_conflicting_tasks(walk) == []

    walk.update(time="08:00")
    assert len(owner.find_conflicting_tasks(walk)) == 1

    walk.update(time="07:30")
    assert owner.find_conflicting_tasks(walk) == []


# ---------- edits persist ----------

def test_edits_survive_save_and_load(tmp_path):
    filename = str(tmp_path / "data.json")

    owner = make_owner()
    task = make_task("Walk")
    owner.pets[0].add_task(task)

    task.update(title="Evening walk", time="18:30", priority="low")
    owner.update_pet("P001", name="Buddy")
    owner.save_to_json(filename)

    loaded = Owner("O002", "Temporary")
    loaded.load_from_json(filename)

    assert loaded.pets[0].name == "Buddy"
    loaded_task = loaded.pets[0].tasks[0]
    assert loaded_task.title == "Evening walk"
    assert loaded_task.time == "18:30"
    assert loaded_task.priority == "low"