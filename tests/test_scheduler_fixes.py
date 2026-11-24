from datetime import date

from pawpal_system import Owner, Pet, Task, Scheduler


DAY_ONE = date(2026, 11, 21)
DAY_TWO = date(2026, 11, 22)


def make_task(title, time, duration=10, priority="medium",
              due_date=DAY_ONE, completed=False):
    return Task(
        title, "Other", duration, priority, time,
        due_date=due_date, completed=completed
    )


# ---------- priority normalization ----------

def test_priority_is_normalized_to_lowercase():
    assert make_task("A", "08:00", priority="High").priority == "high"
    assert make_task("B", "08:00", priority="  MEDIUM ").priority == "medium"
    assert make_task("C", "08:00", priority="low").priority == "low"


def test_mixed_case_priorities_sort_together():
    scheduler = Scheduler(480)
    scheduler.schedule_task(make_task("Low one", "07:00", priority="Low"))
    scheduler.schedule_task(make_task("High one", "09:00", priority="HIGH"))
    scheduler.schedule_task(make_task("Mid one", "08:00", priority="medium"))

    result = scheduler.sort_by_priority()

    assert [t.title for t in result] == ["High one", "Mid one", "Low one"]


# ---------- daily plan date filter ----------

def test_daily_plan_filters_by_date():
    scheduler = Scheduler(480)
    scheduler.schedule_task(make_task("Today", "08:00", due_date=DAY_ONE))
    scheduler.schedule_task(make_task("Tomorrow", "08:00", due_date=DAY_TWO))

    plan = scheduler.generate_daily_plan(target_date=DAY_ONE)

    assert [t.title for t in plan] == ["Today"]


def test_daily_plan_without_date_includes_all_incomplete():
    scheduler = Scheduler(480)
    scheduler.schedule_task(make_task("Today", "08:00", due_date=DAY_ONE))
    scheduler.schedule_task(make_task("Tomorrow", "08:00", due_date=DAY_TWO))
    scheduler.schedule_task(
        make_task("Done", "09:00", due_date=DAY_ONE, completed=True)
    )

    plan = scheduler.generate_daily_plan()

    assert {t.title for t in plan} == {"Today", "Tomorrow"}


# ---------- budget check is per day ----------

def test_budget_check_is_per_day():
    """Two 40-minute tasks on different days fit a 60-minute budget."""
    scheduler = Scheduler(60)
    scheduler.schedule_task(
        make_task("A", "08:00", duration=40, due_date=DAY_ONE)
    )
    scheduler.schedule_task(
        make_task("B", "08:00", duration=40, due_date=DAY_TWO)
    )

    assert scheduler.detect_conflicts() == []


def test_budget_overrun_detected_within_one_day():
    scheduler = Scheduler(60)
    scheduler.schedule_task(make_task("A", "08:00", duration=40))
    scheduler.schedule_task(make_task("B", "09:00", duration=40))

    over_budget = scheduler.detect_conflicts()

    assert [t.title for t in over_budget] == ["B"]


def test_budget_check_can_target_one_date():
    scheduler = Scheduler(30)
    scheduler.schedule_task(
        make_task("Big", "08:00", duration=50, due_date=DAY_TWO)
    )

    assert scheduler.detect_conflicts(target_date=DAY_ONE) == []
    assert len(scheduler.detect_conflicts(target_date=DAY_TWO)) == 1


def test_budget_check_ignores_completed_tasks():
    scheduler = Scheduler(30)
    scheduler.schedule_task(
        make_task("Done", "08:00", duration=50, completed=True)
    )

    assert scheduler.detect_conflicts() == []


# ---------- pet IDs ----------

def test_next_pet_id_on_empty_owner():
    assert Owner("O001", "Alex").next_pet_id() == "P001"


def test_next_pet_id_does_not_collide_after_removal():
    owner = Owner("O001", "Alex")
    owner.add_pet(Pet("P001", "A", "Dog"))
    owner.add_pet(Pet("P002", "B", "Cat"))
    owner.add_pet(Pet("P003", "C", "Dog"))

    owner.remove_pet("P002")

    new_id = owner.next_pet_id()

    assert new_id == "P004"
    assert new_id not in [pet.pet_id for pet in owner.pets]


def test_next_pet_id_ignores_nonstandard_ids():
    owner = Owner("O001", "Alex")
    owner.add_pet(Pet("custom", "A", "Dog"))

    assert owner.next_pet_id() == "P001"