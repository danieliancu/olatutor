"""Stable feedback codes and fixed British English text. See docs/PEDAGOGY_SPEC.md.

Texts hold no values from any exercise, so they cannot reveal an answer. Only the line number
is filled in, by the caller. `explanation` is shown on request. No text names a misconception,
because a wrong value does not prove why it was written.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Feedback:
    checked: str
    problem: str | None
    hint: str | None
    explanation: str


_CHECKED_VALUE = "We compared the exact value of each line with the line before it."
_ASK_READ = "We could not read this line in only one way, so we have not marked it."
_ASK_UNSUPPORTED = "This check cannot read that yet, so we have not marked it."

FEEDBACK: dict[str, Feedback] = {
    "SOLUTION_COMPLETE": Feedback(
        _CHECKED_VALUE + " We also checked your final answer and its form.",
        None,
        None,
        "Every line keeps the same value, and the final answer is in the form asked for.",
    ),
    "VALUE_RIGHT_NOT_SIMPLIFIED": Feedback(
        "We checked the value and the form of your final answer.",
        "The value is right, but the fraction is not in its simplest form.",
        "Is there a number that divides both the top and the bottom?",
        "A fraction is in its simplest form when only 1 divides both the top and the bottom.",
    ),
    "VALUE_RIGHT_FORM_WRONG": Feedback(
        "We checked the value and the form of your final answer.",
        "The value is right, but it is not written in the form the question asks for.",
        "Read the question again and look at how it wants the answer written.",
        "Two forms can have the same value. This question also asks for one particular form.",
    ),
    "NOT_ROUNDED_AS_ASKED": Feedback(
        "We checked the value and the form of your final answer.",
        "The value is exact, but the question asks for a rounded answer.",
        "How many decimal places does the question ask for?",
        "Round by looking at the next digit: 5 or more rounds up, and less than 5 stays the same.",
    ),
    "ANSWER_NOT_FINAL": Feedback(
        _CHECKED_VALUE,
        "Your lines are consistent, but the last one still has a calculation to finish.",
        "Can you finish the last line so that it is just one number?",
        "The final answer should be a single number, with no operations left to do.",
    ),
    "STEPS_REQUIRED": Feedback(
        "We checked your answer and looked for your working.",
        "This question asks you to show your working, and only the answer is here.",
        "Add the lines you used to get to your answer.",
        "Your working lets someone follow each thing you did.",
    ),
    "STEP_VALUE_CHANGED": Feedback(
        _CHECKED_VALUE,
        "Line {line} does not have the same value as what it follows.",
        "Work out line {line} again, slowly.",
        "Each line should have the same value as the one before. On line {line} they differ.",
    ),
    "TRANSFORMATION_CHANGED_VALUE": Feedback(
        _CHECKED_VALUE,
        "Line {line} changes the value of the calculation.",
        "Compare line {line} with what comes just before it. What did you change?",
        "Rewriting a calculation should keep its value. On line {line} the value is different.",
    ),
    "ANSWER_VALUE_MISMATCH": Feedback(
        "We compared the exact value of your answer with the calculation in the question.",
        "This answer does not have the same value as the calculation.",
        "Try writing out your working one line at a time, so that each part can be checked.",
        "We can only see the answer here, so we cannot tell which part of the working to look at.",
    ),
    "FINAL_RIGHT_AFTER_STEP_ERROR": Feedback(
        _CHECKED_VALUE,
        "The final value is right, but line {line} does not follow from the line before it.",
        "Look again at line {line}.",
        "Each line should keep the same value, even when the final answer turns out right.",
    ),
    "ROUNDING_WRONG": Feedback(
        "We rounded the exact value using the rule in the question, and compared your answer.",
        "This is not the value rounded in the way the question asks.",
        "Check how many decimal places you need, and look at the digit just after them.",
        "Round by looking at the next digit: 5 or more rounds up, and less than 5 stays the same.",
    ),
    "DIVISION_BY_ZERO": Feedback(
        "We checked each calculation on line {line}.",
        "Line {line} divides by zero, and that has no value.",
        "Look at what you are dividing by on line {line}.",
        "Dividing by zero is not defined, so the line cannot have a value.",
    ),
    "STEP_VALUE_KEPT": Feedback(
        _CHECKED_VALUE,
        None,
        None,
        "This line has the same value as what it follows. This does not check how you got there.",
    ),
    "STEP_ROUNDED": Feedback(
        "We compared this line with the value before it, rounded by the rule in the question.",
        None,
        None,
        "This line is a correctly rounded form of the line before it.",
    ),
    "STEP_NOT_CHECKED": Feedback(
        "We could not compare this line, because a line next to it could not be read.",
        None,
        "Correct the line next to it, and check again.",
        "A line can only be compared when the lines on both sides of it can be read.",
    ),
    "EMPTY_EXPRESSION": Feedback(
        _ASK_READ,
        None,
        "Line {line} looks empty. Please type it, or remove it.",
        "Nothing was entered for this line.",
    ),
    "INCOMPLETE_EXPRESSION": Feedback(
        _ASK_READ,
        None,
        "Line {line} looks unfinished. Is something missing, such as a number or a bracket?",
        "This line stops before the calculation is complete.",
    ),
    "MISSING_OPERATOR": Feedback(
        _ASK_READ,
        None,
        "On line {line}, two numbers or brackets sit side by side. Which operation joins them?",
        "We do not assume that numbers side by side are multiplied.",
    ),
    "AMBIGUOUS_FRACTION_CHAIN": Feedback(
        _ASK_READ,
        None,
        "Line {line} can be read in two ways. Please use brackets to show what you mean.",
        "A division next to a fraction, typed on one line, can give two different values.",
    ),
    "AMBIGUOUS_MIXED_NUMBER": Feedback(
        _ASK_READ,
        None,
        "On line {line}, is this a mixed number? Its fraction part is not less than one.",
        "A mixed number is a whole number with a fraction smaller than one.",
    ),
    "AMBIGUOUS_NUMBER_FORMAT": Feedback(
        _ASK_READ,
        None,
        "Please check how a number is written on line {line}. A point needs a digit each side.",
        "Commas, and points with no digit on one side, can mean different things.",
    ),
    "AMBIGUOUS_MULTIPLY_X": Feedback(
        _ASK_READ,
        None,
        "On line {line}, did you mean a times sign? Please use × or *.",
        "The letter x could be a times sign or an unknown number.",
    ),
    "AMBIGUOUS_REPEATED_SIGN": Feedback(
        _ASK_READ,
        None,
        "Line {line} has two signs together. Please use brackets, or keep just one.",
        "Signs side by side are easy to misread, so we ask rather than guess.",
    ),
    "UNSUPPORTED_SYMBOL": Feedback(
        _ASK_UNSUPPORTED,
        None,
        "Line {line} has a word, letter or symbol this check cannot read. Please use numbers.",
        "This check reads numbers, brackets and the signs for add, subtract, multiply and divide.",
    ),
    "UNSUPPORTED_OPERATOR": Feedback(
        _ASK_UNSUPPORTED,
        None,
        "Line {line} uses an operation this check cannot read yet.",
        "This check reads numbers, brackets and the signs for add, subtract, multiply and divide.",
    ),
    "APPROX_NOT_SUPPORTED": Feedback(
        _ASK_UNSUPPORTED,
        None,
        "Line {line} uses the approximately-equal sign. This question expects an exact value.",
        "The approximately-equal sign can only be checked in a question about rounding.",
    ),
    "RESOURCE_LIMIT_EXCEEDED": Feedback(
        "This work is too long for the check to finish, so we have not marked it.",
        None,
        "Try fewer lines, or shorter ones.",
        "The check has a fixed limit on size, so it always gives an answer quickly.",
    ),
}


def render_feedback(code: str, line: int | None) -> dict[str, str | None]:
    """Without a line number, a text that needs one falls back to a neutral wording."""
    feedback = FEEDBACK[code]
    label = str(line) if line is not None else "this"

    def fill(text: str | None) -> str | None:
        return None if text is None else text.replace("{line}", label)

    return {
        "code": code,
        "checked": fill(feedback.checked),
        "problem": fill(feedback.problem),
        "hint": fill(feedback.hint),
    }


def render_explanation(code: str, line: int | None) -> str:
    label = str(line) if line is not None else "this"
    return FEEDBACK[code].explanation.replace("{line}", label)
