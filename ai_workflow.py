import json
import logging
from datetime import date

from ai_task_parser import parse_task_request
from task_validator import time_ranges_overlap, validate_task_proposals


logger = logging.getLogger(__name__)

# How many times the AI may be asked to correct a proposal that failed
# validation. 0 turns the retry loop off.
MAX_RETRIES = 2


def find_proposal_conflicts(owner, proposals):
    """
    Return warnings for proposed tasks whose time overlaps (same date)
    with an existing incomplete task or with another proposal.

    Only conflicts that involve a proposed task are reported, so
    pre-existing conflicts in the schedule do not show up here.

    The owner is one person, so tasks for different pets at the
    same time are also treated as conflicts.
    """

    existing = [
        (pet.name, task)
        for pet in owner.pets
        for task in pet.tasks
        if not task.completed
    ]

    conflicts = []
    earlier_proposals = []

    for proposal in proposals:

        label = f"'{proposal['title']}' ({proposal['pet_name']})"

        for pet_name, task in existing:
            if (
                task.due_date.isoformat() == proposal["due_date"]
                and time_ranges_overlap(
                    task.time, task.duration,
                    proposal["time"], proposal["duration"]
                )
            ):
                conflicts.append(
                    f"Conflict: {label} "
                    f"({proposal['time']}, {proposal['duration']} min) "
                    f"overlaps existing '{task.title}' ({pet_name}) "
                    f"({task.time}, {task.duration} min) "
                    f"on {proposal['due_date']}."
                )

        for other in earlier_proposals:
            if (
                other["due_date"] == proposal["due_date"]
                and time_ranges_overlap(
                    other["time"], other["duration"],
                    proposal["time"], proposal["duration"]
                )
            ):
                conflicts.append(
                    f"Conflict: {label} "
                    f"({proposal['time']}, {proposal['duration']} min) "
                    f"overlaps proposed '{other['title']}' "
                    f"({other['pet_name']}) "
                    f"({other['time']}, {other['duration']} min) "
                    f"on {proposal['due_date']}."
                )

        earlier_proposals.append(proposal)

    return conflicts


def build_retry_messages(previous_output, errors):
    """
    Build the feedback sent to the AI after a failed validation.

    The AI sees its own previous answer and the exact problems found.
    It is told to ask a question rather than change the request or
    guess, so a retry cannot quietly alter what the user asked for.
    """
    error_text = "\n".join(f"- {str(error)[:200]}" for error in errors)

    return [
        {
            "role": "assistant",
            "content": json.dumps(previous_output)
        },
        {
            "role": "user",
            "content": (
                "Your previous response failed validation:\n"
                f"{error_text}\n\n"
                "Return a corrected response as JSON in the same "
                "format. Only fix the listed problems and do not "
                "change what I asked for. If fixing a problem would "
                "mean changing my request (for example a date in the "
                "past, a duration over 240 minutes, or a pet that is "
                "not registered) or guessing missing details, do not "
                "guess. Set needs_clarification to true and ask me a "
                "question instead."
            )
        }
    ]


def _response(
    status,
    message,
    *,
    tasks=None,
    errors=None,
    conflicts=None,
    trace=None,
    attempts=1,
    retry_notes=None
):
    """Build the result dictionary every workflow path returns."""
    return {
        "status": status,
        "message": message,
        "tasks": tasks or [],
        "errors": errors or [],
        "conflicts": conflicts or [],
        "attempts": attempts,
        "retried": attempts > 1,
        "retry_notes": retry_notes or [],
        "trace": trace or [],
    }


def revise_proposal(owner, edited_tasks, current_date=None):
    """
    Re-check a proposal after the user edited it by hand.

    Edited tasks go through the same validator as the AI's output, and
    conflicts are recalculated, so a manual edit cannot bypass any
    guardrail. Nothing is saved here either.

    Returns the same shape as process_ai_task_request: status is
    "success" or "invalid".
    """

    if current_date is None:
        current_date = date.today()

    validation_result = validate_task_proposals(
        proposals=edited_tasks,
        pets=owner.pets,
        current_date=current_date
    )

    if not validation_result["valid"]:
        logger.warning(
            "Edited proposal rejected by validation: %s",
            validation_result["errors"]
        )

        return _response(
            "invalid",
            "Your edits were not valid.",
            errors=validation_result["errors"]
        )

    revised_tasks = validation_result["tasks"]
    conflicts = find_proposal_conflicts(owner, revised_tasks)

    logger.info(
        "Edited proposal accepted: %d task(s), %d conflict(s). "
        "Nothing saved yet.",
        len(revised_tasks), len(conflicts)
    )

    return _response(
        "success",
        "Proposal updated with your edits.",
        tasks=revised_tasks,
        conflicts=conflicts
    )


def process_ai_task_request(
    user_request,
    owner,
    current_date=None,
    max_retries=MAX_RETRIES
):
    """
    Process a natural-language task request through the AI workflow.

    Workflow:
    1. Parse the user's request with AI.
    2. Handle clarification requests.
    3. Validate the generated proposals.
    4. If validation fails, show the AI its errors and let it correct
       its answer (up to max_retries times), or ask a question.
    5. Check scheduling conflicts.
    6. Return results for human approval.

    This function does not save or add tasks to the owner.

    The result includes "attempts" (model calls made), "retried",
    "retry_notes" (what failed on the first attempt), and "trace"
    (every attempt's raw output and validation outcome).
    """

    if current_date is None:
        current_date = date.today()

    pets = owner.pets

    logger.info("AI request received: %r", user_request[:200])

    trace = []
    retry_notes = []
    last_errors = []
    extra_messages = None
    attempts = 0

    while True:

        attempts += 1

        # --------------------------------
        # Step 1: AI parsing
        # --------------------------------

        call_arguments = {
            "user_request": user_request,
            "pets": pets,
            "current_date": current_date
        }

        if extra_messages:
            call_arguments["extra_messages"] = extra_messages

        try:
            ai_result = parse_task_request(**call_arguments)

        except Exception as error:
            logger.error(
                "AI parsing failed on attempt %d: %s", attempts, error
            )

            if attempts == 1:
                return _response(
                    "error",
                    f"AI parsing failed: {error}",
                    trace=trace,
                    attempts=attempts
                )

            # The retry call itself failed. Keep the real validation
            # problems visible instead of hiding them behind an error.
            return _response(
                "invalid",
                "The AI-generated tasks failed validation.",
                errors=last_errors + [f"Retry failed: {error}"],
                trace=trace,
                attempts=attempts,
                retry_notes=retry_notes
            )

        if not isinstance(ai_result, dict):
            logger.warning("AI response was not a JSON object.")
            ai_result = {}

        logger.info("AI parsing succeeded (attempt %d).", attempts)

        # --------------------------------
        # Step 2: Clarification handling
        # --------------------------------

        if ai_result.get("needs_clarification", False):
            question = ai_result.get(
                "clarification_question",
                "Please provide more information."
            )

            logger.info("AI asked for clarification: %s", question)

            trace.append({
                "attempt": attempts,
                "ai_output": ai_result,
                "outcome": "clarification",
                "errors": []
            })

            return _response(
                "clarification",
                question,
                trace=trace,
                attempts=attempts,
                retry_notes=retry_notes
            )

        # --------------------------------
        # Step 3: Validate proposals
        # --------------------------------

        validation_result = validate_task_proposals(
            proposals=ai_result.get("tasks", []),
            pets=pets,
            current_date=current_date
        )

        if validation_result["valid"]:
            trace.append({
                "attempt": attempts,
                "ai_output": ai_result,
                "outcome": "valid",
                "errors": []
            })

            break

        last_errors = validation_result["errors"]

        trace.append({
            "attempt": attempts,
            "ai_output": ai_result,
            "outcome": "invalid",
            "errors": last_errors
        })

        logger.warning(
            "Validation rejected attempt %d: %s", attempts, last_errors
        )

        if attempts == 1:
            retry_notes = list(last_errors)

        # --------------------------------
        # Step 4: Ask the AI to correct itself
        # --------------------------------

        if attempts > max_retries:
            logger.warning(
                "Giving up after %d attempt(s).", attempts
            )

            return _response(
                "invalid",
                "The AI-generated tasks failed validation.",
                errors=last_errors,
                trace=trace,
                attempts=attempts,
                retry_notes=retry_notes
            )

        logger.info(
            "Asking the AI to correct its answer (retry %d of %d).",
            attempts, max_retries
        )

        extra_messages = build_retry_messages(ai_result, last_errors)

    validated_tasks = validation_result["tasks"]

    logger.info("Validation passed for %d task(s).", len(validated_tasks))

    # --------------------------------
    # Step 5: Check scheduling conflicts
    # --------------------------------

    conflicts = find_proposal_conflicts(owner, validated_tasks)

    if conflicts:
        logger.warning("Found %d scheduling conflict(s).", len(conflicts))
    else:
        logger.info("No scheduling conflicts found.")

    # --------------------------------
    # Step 6: Return for approval
    # --------------------------------

    logger.info("Proposal ready for human approval. Nothing saved yet.")

    if attempts > 1:
        message = (
            "The AI's first attempt failed validation and was "
            "corrected. Review the details before approving."
        )
    else:
        message = "Tasks were parsed and validated successfully."

    return _response(
        "success",
        message,
        tasks=validated_tasks,
        conflicts=conflicts,
        trace=trace,
        attempts=attempts,
        retry_notes=retry_notes
    )