from datetime import date, datetime


# Supported values
VALID_TASK_TYPES = {
    "feeding",
    "exercise",
    "grooming",
    "medication",
    "other"
}

VALID_PRIORITIES = {
    "low",
    "medium",
    "high"
}

VALID_FREQUENCIES = {
    "daily",
    "weekly",
    "as needed"
}


def time_to_minutes(time_text):
    """Convert 'H:MM' or 'HH:MM' into minutes after midnight."""
    hours, minutes = time_text.split(":")
    return int(hours) * 60 + int(minutes)


def time_ranges_overlap(start_a, duration_a, start_b, duration_b):
    """
    Return True if two tasks on the same day overlap in time.

    A task runs from its start time for its duration. Tasks that
    only touch (one ends exactly when the next starts) do not
    overlap. Two tasks with the same start time always do.
    """
    a = time_to_minutes(start_a)
    b = time_to_minutes(start_b)

    if a == b:
        return True

    return a < b + duration_b and b < a + duration_a


def validate_task_proposals(proposals, pets, current_date):
    """
    Validate AI-generated task proposals before they
    can be added to PawPal+.

    Returns:
        A dictionary containing:
        - valid: whether all proposals passed
        - tasks: validated and normalized tasks
        - errors: validation errors
    """

    errors = []
    validated_tasks = []

    # Convert current_date into a date object if needed
    if isinstance(current_date, str):
        current_date = date.fromisoformat(current_date)

    # Get registered pet names
    pet_names = [pet.name for pet in pets]

    # Ensure proposals are a list
    if not isinstance(proposals, list):
        return {
            "valid": False,
            "tasks": [],
            "errors": ["Task proposals must be a list."]
        }

    # Do not accept an empty list
    if not proposals:
        return {
            "valid": False,
            "tasks": [],
            "errors": ["No task proposals were provided."]
        }

    # Validate each proposed task
    for index, task in enumerate(proposals, start=1):

        task_errors = []

        # Ensure each proposal is a dictionary
        if not isinstance(task, dict):
            errors.append(f"Task {index}: Invalid task format.")
            continue

        # --------------------------------
        # Validate pet name
        # --------------------------------

        pet_name = task.get("pet_name")

        if not isinstance(pet_name, str):
            task_errors.append("Pet name must be a string.")
        elif pet_name.strip().lower() not in [
            name.lower() for name in pet_names
        ]:
            task_errors.append(
                f"Unknown pet: {pet_name}. "
                "The pet must already exist in PawPal+."
            )
        else:
            # Match the registered pet's actual name
            pet_name = next(
                name for name in pet_names
                if name.lower() == pet_name.strip().lower()
            )

        # --------------------------------
        # Validate title
        # --------------------------------

        title = task.get("title")

        if not isinstance(title, str) or not title.strip():
            task_errors.append("Task title cannot be empty.")
        elif len(title.strip()) > 100:
            task_errors.append(
                "Task title cannot exceed 100 characters."
            )
        else:
            title = title.strip()

        # --------------------------------
        # Validate task type
        # --------------------------------

        task_type = task.get("task_type")

        if not isinstance(task_type, str):
            task_errors.append("Invalid task type.")
        elif task_type.strip().lower() not in VALID_TASK_TYPES:
            task_errors.append(
                f"Unsupported task type: {task_type}."
            )
        else:
            task_type = task_type.strip().capitalize()

        # --------------------------------
        # Validate duration
        # --------------------------------

        duration = task.get("duration")

        if isinstance(duration, bool) or not isinstance(duration, int):
            task_errors.append(
                "Duration must be a whole number of minutes."
            )
        elif not 1 <= duration <= 240:
            task_errors.append(
                "Duration must be between 1 and 240 minutes."
            )

        # --------------------------------
        # Validate priority
        # --------------------------------

        priority = task.get("priority")

        if not isinstance(priority, str):
            task_errors.append("Invalid priority.")
        elif priority.strip().lower() not in VALID_PRIORITIES:
            task_errors.append(
                f"Unsupported priority: {priority}."
            )
        else:
            priority = priority.strip().lower()

        # --------------------------------
        # Validate time
        # --------------------------------

        task_time = task.get("time")

        if not isinstance(task_time, str):
            task_errors.append("Time must be a string.")
        else:
            try:
                # Accept "7:00" and store it as "07:00"
                task_time = datetime.strptime(
                    task_time.strip(), "%H:%M"
                ).strftime("%H:%M")
            except ValueError:
                task_errors.append(
                    "Time must use 24-hour HH:MM format."
                )

        # --------------------------------
        # Validate frequency
        # --------------------------------

        frequency = task.get("frequency")

        if not isinstance(frequency, str):
            task_errors.append("Invalid frequency.")
        elif frequency.strip().lower() not in VALID_FREQUENCIES:
            task_errors.append(
                f"Unsupported frequency: {frequency}."
            )
        else:
            frequency = frequency.strip().lower()

        # --------------------------------
        # Validate due date
        # --------------------------------

        due_date = task.get("due_date")

        if not isinstance(due_date, str):
            task_errors.append(
                "Due date must use YYYY-MM-DD format."
            )
        else:
            try:
                parsed_date = date.fromisoformat(due_date)

                if parsed_date < current_date:
                    task_errors.append(
                        "Due date cannot be in the past."
                    )

            except ValueError:
                task_errors.append(
                    "Invalid due date. Use YYYY-MM-DD."
                )

        # --------------------------------
        # Collect errors or accept task
        # --------------------------------

        if task_errors:
            for error in task_errors:
                errors.append(f"Task {index}: {error}")

        else:
            validated_tasks.append({
                "pet_name": pet_name,
                "title": title,
                "task_type": task_type,
                "duration": duration,
                "priority": priority,
                "time": task_time,
                "frequency": frequency,
                "due_date": due_date
            })

    # --------------------------------
    # Final result
    # --------------------------------

    return {
        "valid": len(errors) == 0,
        "tasks": validated_tasks if not errors else [],
        "errors": errors
    }