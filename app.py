import json
import logging
import os

import streamlit as st
from datetime import date, datetime, time

from pawpal_system import Owner, Pet, Task, Scheduler
from ai_workflow import process_ai_task_request, revise_proposal


# =======================================
# LOGGING
# =======================================
# Streamlit re-runs this script on every interaction, so only
# configure logging once. Logs go to the terminal and pawpal.log.

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("pawpal.log", encoding="utf-8")
        ]
    )

logger = logging.getLogger("pawpal.app")


# =======================================
# FORMATTING HELPER FUNCTIONS
# =======================================

def format_task_type(task_type):
    emojis = {
        "Exercise": "🐕",
        "Feeding": "🍖",
        "Medication": "💊",
        "Grooming": "🛁"
    }
    return f"{emojis.get(task_type, '🐾')} {task_type}"


def format_priority(priority):
    indicators = {
        "high": "🔴 High",
        "medium": "🟡 Medium",
        "low": "🟢 Low"
    }
    return indicators.get(priority.lower(), priority)


def format_status(completed):
    return "✅ Completed" if completed else "⏳ Pending"


# Dropdown options and helpers shared by the AI proposal editor
# and the task editor.

TASK_TYPE_OPTIONS = [
    "Feeding", "Exercise", "Grooming", "Medication", "Other"
]
PRIORITY_OPTIONS = ["low", "medium", "high"]
FREQUENCY_OPTIONS = ["daily", "weekly", "as needed"]


def option_index(options, value):
    """Position of value in options, or 0 if it is not there."""
    try:
        return options.index(value)
    except ValueError:
        return 0


def time_from_text(text):
    """Turn "HH:MM" into a time, falling back to 08:00."""
    try:
        return datetime.strptime(text, "%H:%M").time()
    except ValueError:
        return time(8, 0)


# =======================================
# CONFIGURATION
# =======================================

DATA_FILE = "data.json"

st.set_page_config(
    page_title="PawPal+",
    page_icon="🐾",
    layout="centered"
)

st.title("🐾 PawPal+")

st.markdown(
    """
Welcome to PawPal+!

Organize your pets' care tasks, manage recurring activities,
and generate a daily schedule with conflict warnings.
"""
)


# =======================================
# INFORMATION SECTIONS
# =======================================

with st.expander("Scenario", expanded=True):
    st.markdown(
        """
**PawPal+** is a pet care planning assistant. It helps pet owners
plan care tasks for their pets based on duration, priority, and
available time.

The app connects the Streamlit interface to the Owner, Pet, Task,
and Scheduler classes.
"""
    )


with st.expander("Features", expanded=False):
    st.markdown(
        """
- Add and manage pets.
- Create pet care tasks with duration, priority, and scheduled time.
- Choose a due date for each task.
- Mark tasks as completed.
- Automatically create the next daily or weekly recurring task.
- Preserve completed tasks and their original due dates.
- Sort tasks by priority and scheduled time.
- Filter tasks by completion status and pet.
- Detect tasks whose times overlap on the same date.
- Identify tasks that exceed the available time budget.
- Save and load pets and tasks using JSON persistence.
- Display task types using emojis.
- Show visual priority indicators.
- Display task completion status.
- Format task tables for improved readability.
- Use AI to generate pet-care task proposals from natural language.
- Validate AI-generated tasks before accepting them.
- Review and approve or reject AI task proposals.
- Edit any field of a task, or rename a pet and change its species.
- Delete a task, clear completed tasks, or delete a pet
  (each needs a confirmation).
"""
    )

st.divider()


# =======================================
# INITIALIZE OWNER AND LOAD DATA
# =======================================

if "owner" not in st.session_state:

    owner = Owner(
        owner_id="O001",
        name="Jordan",
        preferences={"preferred_start": "08:00"}
    )

    try:
        owner.load_from_json(DATA_FILE)
        logger.info("Loaded data from %s", DATA_FILE)

    except FileNotFoundError:
        logger.info("No %s found. Starting fresh.", DATA_FILE)

    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        # The file is unreadable. Keep a copy instead of overwriting it
        # the next time the app saves, and start with an empty owner.
        logger.error("Could not read %s: %s", DATA_FILE, error)

        backup_name = f"{DATA_FILE}.corrupt"
        os.replace(DATA_FILE, backup_name)

        owner = Owner(
            owner_id="O001",
            name="Jordan",
            preferences={"preferred_start": "08:00"}
        )

        st.session_state["load_warning"] = (
            f"Your saved data could not be read, so PawPal+ started "
            f"fresh. The old file was kept as {backup_name}."
        )

    st.session_state["owner"] = owner
    st.session_state["data_loaded"] = True

owner = st.session_state["owner"]

if "load_warning" in st.session_state:
    st.warning(st.session_state["load_warning"])


# =======================================
# ADD A PET
# =======================================

st.subheader("Add a Pet")

owner.name = st.text_input(
    "Owner name",
    value=owner.name,
    key="owner_name"
)

pet_name = st.text_input(
    "Pet name",
    value="Mochi",
    key="pet_name"
)

species = st.selectbox(
    "Species",
    ["dog", "cat", "other"],
    key="species"
)

if st.button("Add pet"):

    if pet_name.strip() and any(
        existing.name.lower() == pet_name.strip().lower()
        for existing in owner.pets
    ):
        # The AI planner finds pets by name, so names must be unique.
        st.error(f"A pet named {pet_name.strip()} already exists.")

    elif pet_name.strip():

        pet = Pet(
            pet_id=owner.next_pet_id(),
            name=pet_name.strip(),
            species=species
        )

        owner.add_pet(pet)
        owner.save_to_json(DATA_FILE)

        st.success(f"{pet.name} was added!")
        st.rerun()

    else:
        st.error("Please enter a pet name.")


# =======================================
# DISPLAY PETS
# =======================================

st.subheader("Your Pets")

if owner.pets:

    for pet in owner.pets:
        st.write(f"🐾 **{pet.name}** — {pet.species.title()}")

else:
    st.info("No pets yet. Add one above.")


st.divider()


# =======================================
# AI TASK PLANNER
# =======================================

st.subheader("🤖 AI Task Planner")

st.caption(
    "Describe a pet-care task in natural language. "
    "The AI will generate a proposal for you to review."
)

if owner.pets:

    ai_request = st.text_area(
        "Describe the task you want to schedule",
        placeholder=(
            "Example: Schedule a 30-minute walk "
            "for Mochi tomorrow at 7 AM."
        ),
        key="ai_task_request"
    )

    if st.button(
        "Generate AI Task Proposal",
        key="generate_ai_task"
    ):

        if ai_request.strip():

            result = process_ai_task_request(
                user_request=ai_request,
                owner=owner,
                current_date=date.today()
            )

            # Each proposal gets its own id so the editor's widgets
            # start fresh whenever the proposal changes.
            st.session_state["proposal_counter"] = (
                st.session_state.get("proposal_counter", 0) + 1
            )
            result["proposal_id"] = st.session_state["proposal_counter"]

            st.session_state["ai_pending"] = result

        else:
            st.warning("Please enter a task request.")

    # Display pending AI results
    if "ai_pending" in st.session_state:

        result = st.session_state["ai_pending"]

        # --------------------------------
        # Clarification
        # --------------------------------

        if result["status"] == "clarification":

            st.info(result["message"])

        # --------------------------------
        # Errors
        # --------------------------------

        elif result["status"] == "error":

            st.error(result["message"])

        elif result["status"] == "invalid":

            st.error(result["message"])

            for error in result["errors"]:
                st.write(f"❌ {error}")

        # --------------------------------
        # Successful proposal
        # --------------------------------

        elif result["status"] == "success":

            st.success(result["message"])

            # If the AI had to correct itself, make that visible so
            # the user checks the result before approving it.
            if result.get("retried"):

                st.warning(
                    "The AI's first attempt failed validation and was "
                    "corrected automatically. Check every detail "
                    "against what you asked for before approving."
                )

                for note in result.get("retry_notes", []):
                    st.write(f"↩️ First attempt problem: {note}")

            st.markdown("### Proposed Tasks")

            st.table(result["tasks"])

            # Scheduling conflicts
            if result["conflicts"]:

                st.warning(
                    "Scheduling conflicts were detected. "
                    "Review them before approving."
                )

                for conflict in result["conflicts"]:
                    st.write(f"⚠️ {conflict}")

            else:

                st.success(
                    "No overlapping tasks detected."
                )

            # --------------------------------
            # Edit the proposal before approving
            # --------------------------------

            with st.expander("✏️ Edit proposed tasks"):

                st.caption(
                    "Change any detail, or remove a task. Your edits "
                    "are checked by the same rules as the AI's output."
                )

                proposal_id = result.get("proposal_id", 0)
                available_pet_names = [pet.name for pet in owner.pets]

                with st.form(f"edit_proposal_form_{proposal_id}"):

                    edited_proposals = []

                    for number, proposal in enumerate(
                        result["tasks"], start=1
                    ):

                        field_key = f"{proposal_id}_{number}"

                        st.markdown(f"**Task {number}**")

                        drop_task = st.checkbox(
                            "Remove this task from the proposal",
                            key=f"prop_drop_{field_key}"
                        )

                        prop_pet = st.selectbox(
                            "Pet",
                            available_pet_names,
                            index=option_index(
                                available_pet_names,
                                proposal["pet_name"]
                            ),
                            key=f"prop_pet_{field_key}"
                        )

                        prop_title = st.text_input(
                            "Task title",
                            value=proposal["title"],
                            key=f"prop_title_{field_key}"
                        )

                        prop_duration = st.number_input(
                            "Duration (minutes)",
                            min_value=1,
                            max_value=240,
                            value=min(max(proposal["duration"], 1), 240),
                            key=f"prop_duration_{field_key}"
                        )

                        prop_priority = st.selectbox(
                            "Priority",
                            PRIORITY_OPTIONS,
                            index=option_index(
                                PRIORITY_OPTIONS, proposal["priority"]
                            ),
                            key=f"prop_priority_{field_key}"
                        )

                        prop_type = st.selectbox(
                            "Task type",
                            TASK_TYPE_OPTIONS,
                            index=option_index(
                                TASK_TYPE_OPTIONS, proposal["task_type"]
                            ),
                            key=f"prop_type_{field_key}"
                        )

                        prop_time = st.time_input(
                            "Task time",
                            value=time_from_text(proposal["time"]),
                            key=f"prop_time_{field_key}"
                        )

                        prop_date = st.date_input(
                            "Due date",
                            value=date.fromisoformat(
                                proposal["due_date"]
                            ),
                            key=f"prop_date_{field_key}"
                        )

                        prop_frequency = st.selectbox(
                            "Frequency",
                            FREQUENCY_OPTIONS,
                            index=option_index(
                                FREQUENCY_OPTIONS, proposal["frequency"]
                            ),
                            key=f"prop_frequency_{field_key}"
                        )

                        if not drop_task:
                            edited_proposals.append({
                                "pet_name": prop_pet,
                                "title": prop_title,
                                "task_type": prop_type,
                                "duration": int(prop_duration),
                                "priority": prop_priority,
                                "time": prop_time.strftime("%H:%M"),
                                "frequency": prop_frequency,
                                "due_date": prop_date.isoformat()
                            })

                    proposal_edited = st.form_submit_button(
                        "Apply edits to proposal"
                    )

                if proposal_edited:

                    if not edited_proposals:

                        st.error(
                            "Keep at least one task, or use "
                            "Reject Proposal."
                        )

                    else:

                        revised = revise_proposal(
                            owner,
                            edited_proposals,
                            current_date=date.today()
                        )

                        if revised["status"] == "success":

                            logger.info(
                                "User EDITED the AI proposal: "
                                "%d task(s) before, %d after.",
                                len(result["tasks"]),
                                len(revised["tasks"])
                            )

                            st.session_state["proposal_counter"] += 1
                            revised["proposal_id"] = (
                                st.session_state["proposal_counter"]
                            )

                            st.session_state["ai_pending"] = revised

                            st.rerun()

                        else:

                            for edit_error in revised["errors"]:
                                st.error(edit_error)

            st.warning(
                "These tasks have NOT been saved yet. "
                "Review the proposal before approving."
            )

            col1, col2 = st.columns(2)

            # --------------------------------
            # Approve proposal
            # --------------------------------

            with col1:

                if st.button(
                    "Approve and Save Tasks",
                    key="approve_ai_tasks"
                ):

                    tasks_to_add = []
                    approval_error = None

                    # Verify pets and prepare task objects
                    for proposal in result["tasks"]:

                        selected_pet = next(
                            (
                                pet for pet in owner.pets
                                if pet.name.lower()
                                == proposal["pet_name"].lower()
                            ),
                            None
                        )

                        if selected_pet is None:

                            approval_error = (
                                f"Pet '{proposal['pet_name']}' "
                                "could not be found."
                            )

                            break

                        task = Task(
                            title=proposal["title"],
                            task_type=proposal["task_type"],
                            duration=proposal["duration"],
                            priority=proposal["priority"],
                            time=proposal["time"],
                            frequency=proposal["frequency"],
                            completed=False,
                            due_date=date.fromisoformat(
                                proposal["due_date"]
                            )
                        )

                        tasks_to_add.append(
                            (selected_pet, task)
                        )

                    # Add tasks only if every pet was found
                    if approval_error is None:

                        for selected_pet, task in tasks_to_add:
                            selected_pet.add_task(task)

                        owner.save_to_json(DATA_FILE)

                        logger.info(
                            "User APPROVED %d AI task(s): %s",
                            len(tasks_to_add),
                            [t.title for _, t in tasks_to_add]
                        )

                        st.session_state.pop("ai_pending", None)

                        st.success(
                            "AI-generated tasks approved and saved!"
                        )

                        st.rerun()

                    else:

                        st.error(approval_error)

            # --------------------------------
            # Reject proposal
            # --------------------------------

            with col2:

                if st.button(
                    "Reject Proposal",
                    key="reject_ai_tasks"
                ):

                    logger.info(
                        "User REJECTED AI proposal of %d task(s).",
                        len(result["tasks"])
                    )

                    st.session_state.pop("ai_pending", None)

                    st.info("AI task proposal rejected.")

                    st.rerun()

else:

    st.info("Add a pet before using the AI Task Planner.")


st.divider()


# =======================================
# MANUAL TASK INPUT
# =======================================

st.subheader("Tasks")

st.caption(
    "Add care tasks and associate each task with a pet."
)

if owner.pets:

    selected_pet_id = st.selectbox(
        "Choose a pet for this task",
        options=[pet.pet_id for pet in owner.pets],
        format_func=lambda pet_id: next(
            pet.name for pet in owner.pets
            if pet.pet_id == pet_id
        ),
        key="selected_pet_id"
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        task_title = st.text_input(
            "Task title",
            value="Morning walk",
            key="task_title"
        )

    with col2:

        duration = st.number_input(
            "Duration (minutes)",
            min_value=1,
            max_value=240,
            value=20,
            key="task_duration"
        )

    with col3:

        priority = st.selectbox(
            "Priority",
            ["low", "medium", "high"],
            index=2,
            key="task_priority"
        )

    task_type = st.selectbox(
        "Task type",
        ["Feeding", "Exercise", "Grooming", "Medication", "Other"],
        key="task_type"
    )

    task_time = st.time_input(
        "Task time",
        value=time(8, 0),
        key="task_time"
    )

    task_date = st.date_input(
        "Due date",
        value=date.today(),
        key="task_date"
    )

    frequency = st.selectbox(
        "Frequency",
        ["daily", "weekly", "as needed"],
        key="task_frequency"
    )

    if st.button("Add task"):

        if task_title.strip():

            selected_pet = next(
                pet for pet in owner.pets
                if pet.pet_id == selected_pet_id
            )

            task = Task(
                title=task_title.strip(),
                task_type=task_type,
                duration=int(duration),
                priority=priority,
                time=task_time.strftime("%H:%M"),
                frequency=frequency,
                due_date=task_date
            )

            selected_pet.add_task(task)
            owner.save_to_json(DATA_FILE)

            st.success(
                f"Added '{task.title}' to {selected_pet.name}."
            )

            st.rerun()

        else:
            st.error("Please enter a task title.")

else:

    st.info("Add a pet before adding tasks.")


# =======================================
# DISPLAY ALL TASKS
# =======================================

st.subheader("All Tasks")

task_rows = []

for pet in owner.pets:

    for task in pet.get_tasks():

        task_rows.append({
            "Pet": pet.name,
            "Task": task.title,
            "Due Date": task.due_date,
            "Duration (min)": task.duration,
            "Priority": format_priority(task.priority),
            "Time": task.time,
            "Type": format_task_type(task.task_type),
            "Frequency": task.frequency,
            "Status": format_status(task.completed)
        })

if task_rows:

    st.table(task_rows)

else:

    st.info("No tasks yet. Add a task above.")


# =======================================
# UPDATE TASK COMPLETION STATUS
# =======================================

st.divider()

st.subheader("Update Task Status")

incomplete_tasks = [
    (pet, task)
    for pet in owner.pets
    for task in pet.get_tasks()
    if not task.completed
]

if incomplete_tasks:

    selected_index = st.selectbox(
        "Select a task to mark as completed",
        options=range(len(incomplete_tasks)),
        format_func=lambda index: (
            f"{incomplete_tasks[index][0].name} - "
            f"{incomplete_tasks[index][1].title} "
            f"({incomplete_tasks[index][1].due_date}, "
            f"{incomplete_tasks[index][1].time})"
        ),
        key="task_to_complete"
    )

    if st.button("Mark as Completed"):

        selected_task = incomplete_tasks[selected_index][1]

        scheduler = Scheduler(available_time=1440)
        scheduler.get_tasks_from_owner(owner)

        next_task = scheduler.complete_task(owner, selected_task)

        # Save the completed task and recurring occurrence
        owner.save_to_json(DATA_FILE)

        st.success(
            f"'{selected_task.title}' marked as completed!"
        )

        if next_task is not None:

            st.info(
                f"Next {next_task.frequency} occurrence scheduled "
                f"for {next_task.due_date} at {next_task.time}."
            )

        elif selected_task.frequency.lower() == "as needed":

            st.caption(
                "As-needed tasks do not repeat, so no next "
                "occurrence was created."
            )

        else:

            st.caption(
                "No recurring occurrence was created."
            )

        st.rerun()

else:

    st.info("There are no incomplete tasks to update.")


st.divider()


# =======================================
# EDIT TASKS AND PETS
# =======================================

st.subheader("Edit")

edit_message = st.session_state.pop("edit_message", None)

if edit_message:
    st.success(edit_message)

for edit_warning in st.session_state.pop("edit_warnings", []):
    st.warning(edit_warning)

edit_entries = [
    (task_pet, task_item)
    for task_pet in owner.pets
    for task_item in task_pet.get_tasks()
]


def describe_edit_entry(index):
    entry_pet, entry_task = edit_entries[index]
    state = "done" if entry_task.completed else "pending"

    return (
        f"{entry_pet.name} - {entry_task.title} "
        f"({entry_task.due_date}, {entry_task.time}, {state})"
    )


def describe_pet_entry(pet_id):
    for entry_pet in owner.pets:
        if entry_pet.pet_id == pet_id:
            return f"{entry_pet.name} ({len(entry_pet.tasks)} task(s))"

    return pet_id


# ---------- Edit a task ----------

st.markdown("#### Edit a task")

if edit_entries:

    edit_index = st.selectbox(
        "Select a task to edit",
        options=range(len(edit_entries)),
        format_func=describe_edit_entry,
        key="task_to_edit"
    )

    edit_pet, edit_task = edit_entries[edit_index]

    # Keying the widgets by the task object makes each task keep
    # its own form values, so switching tasks shows the right ones.
    task_key = id(edit_task)

    with st.form(f"edit_task_form_{task_key}"):

        new_title = st.text_input(
            "Task title",
            value=edit_task.title,
            key=f"edit_title_{task_key}"
        )

        new_duration = st.number_input(
            "Duration (minutes)",
            min_value=1,
            max_value=240,
            value=min(max(edit_task.duration, 1), 240),
            key=f"edit_duration_{task_key}"
        )

        new_priority = st.selectbox(
            "Priority",
            PRIORITY_OPTIONS,
            index=option_index(PRIORITY_OPTIONS, edit_task.priority),
            key=f"edit_priority_{task_key}"
        )

        new_type = st.selectbox(
            "Task type",
            TASK_TYPE_OPTIONS,
            index=option_index(TASK_TYPE_OPTIONS, edit_task.task_type),
            key=f"edit_type_{task_key}"
        )

        new_time = st.time_input(
            "Task time",
            value=time_from_text(edit_task.time),
            key=f"edit_time_{task_key}"
        )

        new_date = st.date_input(
            "Due date",
            value=edit_task.due_date,
            key=f"edit_date_{task_key}"
        )

        new_frequency = st.selectbox(
            "Frequency",
            FREQUENCY_OPTIONS,
            index=option_index(FREQUENCY_OPTIONS, edit_task.frequency),
            key=f"edit_frequency_{task_key}"
        )

        task_submitted = st.form_submit_button("Save task changes")

    if task_submitted:

        old_title = edit_task.title

        try:
            task_changes = edit_task.update(
                title=new_title,
                task_type=new_type,
                duration=int(new_duration),
                priority=new_priority,
                time=new_time.strftime("%H:%M"),
                frequency=new_frequency,
                due_date=new_date
            )

        except ValueError as error:

            st.error(str(error))

        else:

            if not task_changes:

                st.info("No changes to save.")

            else:

                owner.save_to_json(DATA_FILE)

                logger.info(
                    "User EDITED task '%s' for %s: %s",
                    old_title, edit_pet.name, task_changes
                )

                st.session_state["edit_message"] = (
                    f"Saved changes to '{edit_task.title}' "
                    f"for {edit_pet.name}."
                )

                st.session_state["edit_warnings"] = [
                    f"'{edit_task.title}' ({edit_pet.name}) at "
                    f"{edit_task.time} now overlaps on "
                    f"{edit_task.due_date} with "
                    f"'{other_task.title}' ({other_pet.name}) at "
                    f"{other_task.time}."
                    for other_pet, other_task
                    in owner.find_conflicting_tasks(edit_task)
                ]

                st.rerun()

else:

    st.info("There are no tasks to edit.")


# ---------- Edit a pet ----------

st.markdown("#### Edit a pet")

if owner.pets:

    edit_pet_id = st.selectbox(
        "Select a pet to edit",
        options=[pet.pet_id for pet in owner.pets],
        format_func=describe_pet_entry,
        key="pet_to_edit"
    )

    pet_being_edited = next(
        pet for pet in owner.pets if pet.pet_id == edit_pet_id
    )

    species_options = ["dog", "cat", "other"]

    if pet_being_edited.species not in species_options:
        species_options.append(pet_being_edited.species)

    with st.form(f"edit_pet_form_{edit_pet_id}"):

        new_pet_name = st.text_input(
            "Pet name",
            value=pet_being_edited.name,
            key=f"edit_pet_name_{edit_pet_id}"
        )

        new_species = st.selectbox(
            "Species",
            species_options,
            index=species_options.index(pet_being_edited.species),
            key=f"edit_pet_species_{edit_pet_id}"
        )

        pet_submitted = st.form_submit_button("Save pet changes")

    if pet_submitted:

        old_name = pet_being_edited.name
        old_species = pet_being_edited.species

        try:
            owner.update_pet(
                edit_pet_id,
                name=new_pet_name,
                species=new_species
            )

        except ValueError as error:

            st.error(str(error))

        else:

            if (
                pet_being_edited.name == old_name
                and pet_being_edited.species == old_species
            ):

                st.info("No changes to save.")

            else:

                owner.save_to_json(DATA_FILE)

                logger.info(
                    "User EDITED pet %s: name %r -> %r, "
                    "species %r -> %r",
                    edit_pet_id, old_name, pet_being_edited.name,
                    old_species, pet_being_edited.species
                )

                st.session_state["edit_message"] = (
                    f"Saved changes to {pet_being_edited.name}."
                )

                # A pending AI proposal may use the old name.
                st.session_state.pop("ai_pending", None)

                st.rerun()

else:

    st.info("There are no pets to edit.")


st.divider()


# =======================================
# DELETE TASKS AND PETS
# =======================================

st.subheader("Delete")

st.caption(
    "Deleting cannot be undone. Each delete needs a confirmation."
)

delete_message = st.session_state.pop("delete_message", None)

if delete_message:
    st.success(delete_message)


def reset_delete_widgets():
    """Clear widget state that may point at deleted items."""
    for key in (
        "task_to_delete", "confirm_task_delete",
        "pet_to_delete", "confirm_pet_delete",
        "confirm_clear_completed",
        "task_to_complete", "selected_pet_id"
    ):
        st.session_state.pop(key, None)


all_task_entries = [
    (task_pet, task_item)
    for task_pet in owner.pets
    for task_item in task_pet.get_tasks()
]


def describe_task_entry(index):
    entry_pet, entry_task = all_task_entries[index]
    state = "done" if entry_task.completed else "pending"

    return (
        f"{entry_pet.name} - {entry_task.title} "
        f"({entry_task.due_date}, {entry_task.time}, {state})"
    )


# ---------- Delete one task ----------

st.markdown("#### Delete a task")

if all_task_entries:

    delete_task_index = st.selectbox(
        "Select a task to delete",
        options=range(len(all_task_entries)),
        format_func=describe_task_entry,
        key="task_to_delete"
    )

    confirm_task_delete = st.checkbox(
        "Yes, delete this task",
        key="confirm_task_delete"
    )

    if st.button(
        "Delete task",
        disabled=not confirm_task_delete,
        key="delete_task_button"
    ):

        pet_of_task, task_to_delete = all_task_entries[delete_task_index]

        if owner.remove_task(task_to_delete):

            owner.save_to_json(DATA_FILE)

            logger.info(
                "User DELETED task '%s' (%s, %s) from %s",
                task_to_delete.title,
                task_to_delete.due_date,
                task_to_delete.time,
                pet_of_task.name
            )

            st.session_state["delete_message"] = (
                f"Deleted '{task_to_delete.title}' "
                f"from {pet_of_task.name}."
            )

            reset_delete_widgets()
            st.rerun()

        else:

            st.error("That task could not be found.")

else:

    st.info("There are no tasks to delete.")


# ---------- Clear completed tasks ----------

st.markdown("#### Clear completed tasks")

completed_count = sum(
    1 for _, task_item in all_task_entries if task_item.completed
)

if completed_count:

    confirm_clear = st.checkbox(
        f"Yes, delete all {completed_count} completed task(s)",
        key="confirm_clear_completed"
    )

    if st.button(
        "Clear completed tasks",
        disabled=not confirm_clear,
        key="clear_completed_button"
    ):

        removed_count = owner.clear_completed_tasks()

        owner.save_to_json(DATA_FILE)

        logger.info(
            "User CLEARED %d completed task(s).", removed_count
        )

        st.session_state["delete_message"] = (
            f"Cleared {removed_count} completed task(s)."
        )

        reset_delete_widgets()
        st.rerun()

else:

    st.caption("No completed tasks to clear.")


# ---------- Delete a pet ----------

st.markdown("#### Delete a pet")

if owner.pets:

    delete_pet_id = st.selectbox(
        "Select a pet to delete",
        options=[pet.pet_id for pet in owner.pets],
        format_func=describe_pet_entry,
        key="pet_to_delete"
    )

    confirm_pet_delete = st.checkbox(
        "Yes, delete this pet and all of its tasks",
        key="confirm_pet_delete"
    )

    if st.button(
        "Delete pet",
        disabled=not confirm_pet_delete,
        key="delete_pet_button"
    ):

        pet_to_delete = next(
            (
                pet for pet in owner.pets
                if pet.pet_id == delete_pet_id
            ),
            None
        )

        if pet_to_delete is not None and owner.remove_pet(delete_pet_id):

            owner.save_to_json(DATA_FILE)

            logger.info(
                "User DELETED pet %s (%s) and its %d task(s).",
                pet_to_delete.name,
                pet_to_delete.pet_id,
                len(pet_to_delete.tasks)
            )

            st.session_state["delete_message"] = (
                f"Deleted {pet_to_delete.name} and "
                f"{len(pet_to_delete.tasks)} task(s)."
            )

            # A pending AI proposal may mention the deleted pet.
            st.session_state.pop("ai_pending", None)

            reset_delete_widgets()
            st.rerun()

        else:

            st.error("That pet could not be found.")

else:

    st.info("There are no pets to delete.")


st.divider()


# =======================================
# BUILD DAILY SCHEDULE
# =======================================

st.subheader("Build Schedule")

st.caption(
    "Generate a priority-based daily plan and check for scheduling conflicts."
)

available_time = st.number_input(
    "Available time (minutes)",
    min_value=1,
    max_value=1440,
    value=60,
    key="available_time"
)

if st.button("Generate schedule"):

    scheduler = Scheduler(
        available_time=int(available_time)
    )

    scheduler.get_tasks_from_owner(owner)

    today = date.today()

    daily_plan = scheduler.generate_daily_plan(target_date=today)

    if daily_plan:

        st.markdown(f"### Today's Schedule ({today})")

        schedule_rows = []

        for task in daily_plan:

            pet_name_for_task = next(
                (
                    pet.name
                    for pet in owner.pets
                    if task in pet.get_tasks()
                ),
                "Unknown"
            )

            schedule_rows.append({
                "Due Date": task.due_date,
                "Time": task.time,
                "Pet": pet_name_for_task,
                "Task": task.title,
                "Duration (min)": task.duration,
                "Priority": format_priority(task.priority),
                "Type": format_task_type(task.task_type),
                "Status": format_status(task.completed)
            })

        st.table(schedule_rows)

    else:

        st.info("There are no incomplete tasks due today.")

    # --------------------------------
    # Time overlap check
    # --------------------------------

    time_conflicts = scheduler.detect_time_conflicts()

    st.markdown("### Time Overlap Check")

    if time_conflicts:

        st.warning(
            "Scheduling conflicts found. Review the tasks below "
            "to avoid care activities that overlap in time."
        )

        for conflict in time_conflicts:
            st.write(f"⚠️ {conflict}")

    else:

        st.success("No overlapping tasks detected.")

    # --------------------------------
    # Available-time check
    # --------------------------------

    budget_conflicts = scheduler.detect_conflicts(target_date=today)

    st.markdown("### Available-Time Check (today)")

    if budget_conflicts:

        st.warning(
            "Some tasks exceed today's available time budget. "
            "Consider adjusting your schedule."
        )

        for task in budget_conflicts:
            st.write(f"- {task.title}")

    else:

        st.success(
            "All of today's tasks fit within the available time budget."
        )