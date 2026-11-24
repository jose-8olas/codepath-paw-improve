import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta, datetime

from task_validator import (
    time_ranges_overlap,
    VALID_FREQUENCIES,
    VALID_PRIORITIES,
    VALID_TASK_TYPES
)


@dataclass
class Task:
    """Represent a pet-care activity."""
    title: str
    task_type: str
    duration: int
    priority: str
    time: str
    frequency: str = "daily"
    completed: bool = False
    due_date: date = field(default_factory=date.today)

    def __post_init__(self) -> None:
        """Normalize priority so "High" and "high" are stored the same."""
        if isinstance(self.priority, str):
            self.priority = self.priority.strip().lower()

    def mark_completed(self) -> None:
        """Mark the task as completed."""
        self.completed = True

    def update(
        self,
        *,
        title: str | None = None,
        task_type: str | None = None,
        duration: int | None = None,
        priority: str | None = None,
        time: str | None = None,
        frequency: str | None = None,
        due_date: date | None = None
    ) -> dict:
        """
        Change one or more fields of this task.

        Every new value is validated first, so a bad value leaves the
        task completely unchanged. Raises ValueError for bad values.
        Returns {field: (old, new)} for the fields that changed.
        """
        new_values = {}

        if title is not None:
            if not isinstance(title, str) or not title.strip():
                raise ValueError("Task title cannot be empty.")
            if len(title.strip()) > 100:
                raise ValueError(
                    "Task title cannot exceed 100 characters."
                )
            new_values["title"] = title.strip()

        if task_type is not None:
            if (
                not isinstance(task_type, str)
                or task_type.strip().lower() not in VALID_TASK_TYPES
            ):
                raise ValueError(f"Unsupported task type: {task_type}.")
            new_values["task_type"] = task_type.strip().capitalize()

        if duration is not None:
            if (
                isinstance(duration, bool)
                or not isinstance(duration, int)
                or not 1 <= duration <= 240
            ):
                raise ValueError(
                    "Duration must be a whole number between "
                    "1 and 240 minutes."
                )
            new_values["duration"] = duration

        if priority is not None:
            if (
                not isinstance(priority, str)
                or priority.strip().lower() not in VALID_PRIORITIES
            ):
                raise ValueError(f"Unsupported priority: {priority}.")
            new_values["priority"] = priority.strip().lower()

        if time is not None:
            if not isinstance(time, str) or not re.fullmatch(
                r"\d{2}:\d{2}", time
            ):
                raise ValueError("Time must use 24-hour HH:MM format.")

            try:
                datetime.strptime(time, "%H:%M")
            except ValueError:
                raise ValueError(
                    "Time must use 24-hour HH:MM format."
                ) from None

            new_values["time"] = time

        if frequency is not None:
            if (
                not isinstance(frequency, str)
                or frequency.strip().lower() not in VALID_FREQUENCIES
            ):
                raise ValueError(f"Unsupported frequency: {frequency}.")
            new_values["frequency"] = frequency.strip().lower()

        if due_date is not None:
            if not isinstance(due_date, date):
                raise ValueError("Due date must be a date.")
            new_values["due_date"] = due_date

        changes = {}

        for field_name, new_value in new_values.items():
            old_value = getattr(self, field_name)

            if old_value != new_value:
                changes[field_name] = (old_value, new_value)
                setattr(self, field_name, new_value)

        return changes


@dataclass
class Pet:
    """Store pet details and assigned care tasks."""
    pet_id: str
    name: str
    species: str
    tasks: list[Task] = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        """Add a care task to this pet."""
        self.tasks.append(task)

    def get_tasks(self) -> list[Task]:
        """Return this pet's care tasks."""
        return self.tasks.copy()

    def remove_task(self, task: Task) -> bool:
        """
        Remove one specific task from this pet.

        Matches by identity, not equality, so deleting one of two
        identical-looking tasks never removes the other one.
        Returns True if the task was found and removed.
        """
        for index, existing in enumerate(self.tasks):
            if existing is task:
                del self.tasks[index]
                return True

        return False


class Owner:
    """Manage an owner's pets and their care tasks."""

    def __init__(
        self,
        owner_id: str,
        name: str,
        preferences: dict | None = None
    ) -> None:
        """Initialize the owner and their preferences."""
        self.owner_id = owner_id
        self.name = name
        self.preferences = (
            preferences if preferences is not None else {}
        )
        self.pets: list[Pet] = []

    def add_pet(self, pet: Pet) -> None:
        """Add a pet to the owner."""
        self.pets.append(pet)

    def remove_pet(self, pet_id: str) -> bool:
        """
        Remove a pet, and all of its tasks, using its ID.

        Returns True if a pet was removed.
        """
        count_before = len(self.pets)

        self.pets = [
            pet for pet in self.pets
            if pet.pet_id != pet_id
        ]

        return len(self.pets) < count_before

    def remove_task(self, task: Task) -> bool:
        """
        Remove a task from whichever pet owns it.

        Returns True if the task was found and removed.
        """
        for pet in self.pets:
            if pet.remove_task(task):
                return True

        return False

    def clear_completed_tasks(self) -> int:
        """Remove every completed task and return how many were removed."""
        removed = 0

        for pet in self.pets:
            count_before = len(pet.tasks)

            pet.tasks = [
                task for task in pet.tasks
                if not task.completed
            ]

            removed += count_before - len(pet.tasks)

        return removed

    def next_pet_id(self) -> str:
        """
        Return an unused pet ID such as "P003".

        Uses the highest existing number plus one, so IDs never
        collide after a pet has been removed.
        """
        highest = 0

        for pet in self.pets:
            match = re.fullmatch(r"P(\d+)", pet.pet_id)

            if match:
                highest = max(highest, int(match.group(1)))

        return f"P{highest + 1:03d}"

    def update_pet(
        self,
        pet_id: str,
        *,
        name: str | None = None,
        species: str | None = None
    ) -> bool:
        """
        Rename a pet or change its species.

        Returns False if no pet has that ID. Raises ValueError for an
        empty value or a name another pet already uses (compared
        ignoring case), because the AI planner finds pets by name.
        """
        pet = next(
            (pet for pet in self.pets if pet.pet_id == pet_id),
            None
        )

        if pet is None:
            return False

        new_name = pet.name
        new_species = pet.species

        if name is not None:
            cleaned_name = name.strip() if isinstance(name, str) else ""

            if not cleaned_name:
                raise ValueError("Pet name cannot be empty.")

            if len(cleaned_name) > 50:
                raise ValueError("Pet name cannot exceed 50 characters.")

            if any(
                other.pet_id != pet_id
                and other.name.lower() == cleaned_name.lower()
                for other in self.pets
            ):
                raise ValueError(
                    f"Another pet is already named {cleaned_name}."
                )

            new_name = cleaned_name

        if species is not None:
            cleaned_species = (
                species.strip() if isinstance(species, str) else ""
            )

            if not cleaned_species:
                raise ValueError("Species cannot be empty.")

            new_species = cleaned_species

        pet.name = new_name
        pet.species = new_species

        return True

    def find_conflicting_tasks(
        self, task: Task
    ) -> list[tuple[Pet, Task]]:
        """
        Return (pet, task) pairs for other incomplete tasks that share
        this task's time on the same date (the durations overlap).
        A completed task has no conflicts.
        """
        if task.completed:
            return []

        return [
            (pet, other)
            for pet in self.pets
            for other in pet.tasks
            if other is not task
            and not other.completed
            and other.due_date == task.due_date
            and time_ranges_overlap(
                task.time, task.duration, other.time, other.duration
            )
        ]

    def get_all_tasks(self) -> list[Task]:
        """Return tasks belonging to all of the owner's pets."""
        return [
            task
            for pet in self.pets
            for task in pet.get_tasks()
        ]

    def save_to_json(self, filename: str = "data.json") -> None:
        """Save owner, pets, and tasks to a JSON file."""

        data = {
            "owner_id": self.owner_id,
            "name": self.name,
            "preferences": self.preferences,
            "pets": []
        }

        for pet in self.pets:
            pet_data = {
                "pet_id": pet.pet_id,
                "name": pet.name,
                "species": pet.species,
                "tasks": []
            }

            for task in pet.tasks:
                task_data = {
                    "title": task.title,
                    "task_type": task.task_type,
                    "duration": task.duration,
                    "priority": task.priority,
                    "time": task.time,
                    "frequency": task.frequency,
                    "completed": task.completed,
                    "due_date": task.due_date.isoformat()
                }

                pet_data["tasks"].append(task_data)

            data["pets"].append(pet_data)

        with open(filename, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

    def load_from_json(self, filename: str = "data.json") -> None:
        """Load owner, pets, and tasks from a JSON file."""

        with open(filename, "r", encoding="utf-8") as file:
            data = json.load(file)

        self.owner_id = data["owner_id"]
        self.name = data["name"]
        self.preferences = data.get("preferences", {})
        self.pets = []

        for pet_data in data["pets"]:
            pet = Pet(
                pet_id=pet_data["pet_id"],
                name=pet_data["name"],
                species=pet_data["species"]
            )

            for task_data in pet_data["tasks"]:
                task = Task(
                    title=task_data["title"],
                    task_type=task_data["task_type"],
                    duration=task_data["duration"],
                    priority=task_data["priority"],
                    time=task_data["time"],
                    frequency=task_data["frequency"],
                    completed=task_data["completed"],
                    due_date=date.fromisoformat(task_data["due_date"])
                )

                pet.add_task(task)

            self.add_pet(pet)


class Scheduler:
    """Organize tasks into a daily care schedule."""

    def __init__(self, available_time: int) -> None:
        """Initialize the scheduler with a time budget."""
        self.available_time = available_time
        self.tasks: list[Task] = []

    def schedule_task(self, task: Task) -> None:
        """Add a task to the scheduler."""
        self.tasks.append(task)

    def get_tasks_from_owner(self, owner: Owner) -> list[Task]:
        """Retrieve tasks from all pets belonging to an owner."""
        self.tasks = owner.get_all_tasks()
        return self.tasks.copy()

    def sort_by_time(self) -> list[Task]:
        """Return tasks sorted by scheduled time."""
        return sorted(
            self.tasks,
            key=lambda task: task.time
        )

    def sort_by_priority(self) -> list[Task]:
        """Sort tasks by priority first, then by time."""
        priority_order = {
            "high": 1,
            "medium": 2,
            "low": 3
        }

        return sorted(
            self.tasks,
            key=lambda task: (
                priority_order.get(task.priority.lower(), 4),
                task.time
            )
        )

    def filter_by_status(self, completed: bool) -> list[Task]:
        """Return tasks matching the requested completion status."""
        return [
            task for task in self.tasks
            if task.completed == completed
        ]

    def filter_by_pet(
        self, owner: Owner, pet_id: str
    ) -> list[Task]:
        """Return tasks belonging to a specific pet."""
        for pet in owner.pets:
            if pet.pet_id == pet_id:
                return pet.get_tasks()

        return []

    def complete_task(
        self, owner: Owner, task: Task
    ) -> Task | None:
        """Complete a task and create its next recurring occurrence."""

        pet_found = None

        # Find the pet that owns the task.
        for pet in owner.pets:
            if task in pet.tasks:
                pet_found = pet
                break

        # Make sure the task belongs to this owner.
        if pet_found is None:
            return None

        # Prevent duplicate recurring tasks.
        if task.completed:
            return None

        # Mark the original task as completed.
        task.mark_completed()

        # Calculate the next occurrence.
        if task.frequency.lower() == "daily":
            next_date = task.due_date + timedelta(days=1)

        elif task.frequency.lower() == "weekly":
            next_date = task.due_date + timedelta(days=7)

        else:
            return None

        # Create a separate task with the original details.
        next_task = Task(
            title=task.title,
            task_type=task.task_type,
            duration=task.duration,
            priority=task.priority,
            time=task.time,
            frequency=task.frequency,
            completed=False,
            due_date=next_date
        )

        # Add the new task to the pet and scheduler.
        pet_found.add_task(next_task)
        self.tasks.append(next_task)

        return next_task

    def detect_conflicts(
        self, target_date: date | None = None
    ) -> list[Task]:
        """
        Return tasks that exceed the available time budget.

        The budget applies to each day separately. If target_date is
        given, only that day is checked. Completed tasks are ignored.
        """
        tasks_by_date: dict[date, list[Task]] = {}

        for task in self.sort_by_time():
            if task.completed:
                continue

            if target_date is not None and task.due_date != target_date:
                continue

            tasks_by_date.setdefault(task.due_date, []).append(task)

        conflicts = []

        for day_tasks in tasks_by_date.values():
            total_duration = 0

            for task in day_tasks:
                total_duration += task.duration

                if total_duration > self.available_time:
                    conflicts.append(task)

        return conflicts

    def detect_time_conflicts(self) -> list[str]:
        """
        Return warnings for incomplete tasks whose times overlap
        on the same day.
        """
        warnings = []
        tasks = [task for task in self.tasks if not task.completed]

        for index, task in enumerate(tasks):
            for other_task in tasks[:index]:
                if (
                    other_task.due_date == task.due_date
                    and time_ranges_overlap(
                        other_task.time, other_task.duration,
                        task.time, task.duration
                    )
                ):
                    warnings.append(
                        f"Conflict: '{other_task.title}' "
                        f"({other_task.time}, {other_task.duration} min) "
                        f"and '{task.title}' "
                        f"({task.time}, {task.duration} min) overlap "
                        f"on {task.due_date}."
                    )

        return warnings

    def generate_daily_plan(
        self, target_date: date | None = None
    ) -> list[Task]:
        """
        Generate a plan sorted by priority and time.

        If target_date is given, only incomplete tasks due on that
        date are included. Otherwise all incomplete tasks are.
        """
        return [
            task for task in self.sort_by_priority()
            if not task.completed
            and (target_date is None or task.due_date == target_date)
        ]

    def find_next_available_slot(
        self,
        requested_date: date,
        start_time: str,
        duration: int
    ) -> str | None:
        """Find the earliest available time slot for a task."""

        if duration <= 0:
            raise ValueError("Duration must be greater than zero.")

        current_time = datetime.strptime(
            start_time, "%H:%M"
        )

        daily_tasks = sorted(
            [
                task for task in self.tasks
                if task.due_date == requested_date
                and not task.completed
            ],
            key=lambda task: task.time
        )

        for task in daily_tasks:
            task_start = datetime.strptime(
                task.time, "%H:%M"
            )

            task_end = task_start + timedelta(
                minutes=task.duration
            )

            requested_end = current_time + timedelta(
                minutes=duration
            )

            if current_time < task_end and requested_end > task_start:
                current_time = task_end

        if current_time + timedelta(minutes=duration) > datetime.strptime(
            "23:59", "%H:%M"
        ):
            return None

        return current_time.strftime("%H:%M")