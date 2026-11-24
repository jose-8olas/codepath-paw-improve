from datetime import date

from pawpal_system import Owner, Pet, Task


DAY = date(2026, 11, 22)


def make_task(title="Walk", time="08:00", completed=False):
    return Task(
        title, "Exercise", 30, "high", time,
        completed=completed, due_date=DAY
    )


def make_owner():
    owner = Owner("O001", "Alex")
    owner.add_pet(Pet("P001", "Mochi", "dog"))
    owner.add_pet(Pet("P002", "Whiskers", "cat"))
    return owner


# ---------- Pet.remove_task ----------

def test_remove_task_removes_it():
    pet = Pet("P001", "Mochi", "dog")
    task = make_task()
    pet.add_task(task)

    assert pet.remove_task(task) is True
    assert pet.tasks == []


def test_remove_task_only_removes_the_exact_task():
    """Two identical-looking tasks: deleting one keeps the other."""
    pet = Pet("P001", "Mochi", "dog")
    first = make_task()
    second = make_task()
    assert first == second            # equal by value...
    assert first is not second        # ...but different objects

    pet.add_task(first)
    pet.add_task(second)

    assert pet.remove_task(second) is True

    assert len(pet.tasks) == 1
    assert pet.tasks[0] is first


def test_remove_task_returns_false_when_not_found():
    pet = Pet("P001", "Mochi", "dog")
    pet.add_task(make_task("Walk"))

    assert pet.remove_task(make_task("Other")) is False
    assert len(pet.tasks) == 1


# ---------- Owner.remove_task ----------

def test_owner_removes_task_from_the_right_pet():
    owner = make_owner()
    mochi, whiskers = owner.pets

    mochi_task = make_task("Walk")
    cat_task = make_task("Feed cat")
    mochi.add_task(mochi_task)
    whiskers.add_task(cat_task)

    assert owner.remove_task(cat_task) is True

    assert mochi.tasks == [mochi_task]
    assert whiskers.tasks == []


def test_owner_remove_task_returns_false_for_unknown_task():
    owner = make_owner()
    owner.pets[0].add_task(make_task("Walk"))

    assert owner.remove_task(make_task("Walk")) is False
    assert len(owner.get_all_tasks()) == 1


# ---------- Owner.remove_pet ----------

def test_remove_pet_deletes_the_pet_and_its_tasks():
    owner = make_owner()
    owner.pets[0].add_task(make_task("Walk"))
    owner.pets[1].add_task(make_task("Feed cat"))

    assert owner.remove_pet("P001") is True

    assert [pet.name for pet in owner.pets] == ["Whiskers"]
    assert [task.title for task in owner.get_all_tasks()] == ["Feed cat"]


def test_remove_pet_returns_false_for_unknown_id():
    owner = make_owner()

    assert owner.remove_pet("P999") is False
    assert len(owner.pets) == 2


# ---------- Owner.clear_completed_tasks ----------

def test_clear_completed_removes_only_completed_tasks():
    owner = make_owner()
    owner.pets[0].add_task(make_task("Done walk", completed=True))
    owner.pets[0].add_task(make_task("Pending walk", "09:00"))
    owner.pets[1].add_task(make_task("Done feed", completed=True))

    removed = owner.clear_completed_tasks()

    assert removed == 2
    assert [t.title for t in owner.get_all_tasks()] == ["Pending walk"]


def test_clear_completed_with_nothing_to_clear():
    owner = make_owner()
    owner.pets[0].add_task(make_task("Pending"))

    assert owner.clear_completed_tasks() == 0
    assert len(owner.get_all_tasks()) == 1


# ---------- deletions persist ----------

def test_deletions_survive_save_and_load(tmp_path):
    filename = str(tmp_path / "data.json")

    owner = make_owner()
    keep = make_task("Keep")
    drop = make_task("Drop", "09:00")
    owner.pets[0].add_task(keep)
    owner.pets[0].add_task(drop)
    owner.pets[1].add_task(make_task("Cat task"))

    owner.remove_task(drop)
    owner.remove_pet("P002")
    owner.save_to_json(filename)

    loaded = Owner("O002", "Temporary")
    loaded.load_from_json(filename)

    assert [pet.name for pet in loaded.pets] == ["Mochi"]
    assert [t.title for t in loaded.get_all_tasks()] == ["Keep"]