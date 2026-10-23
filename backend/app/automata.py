from typing import Any, Callable


MAX_AUTOMATA_INPUT = 2_000


def _matches(kind: str, character: str) -> bool:
    if kind == "letter_or_underscore":
        return character.isalpha() or character == "_"
    if kind == "identifier_continue":
        return character.isalnum() or character == "_"
    if kind == "digit":
        return character.isdigit()
    if kind == "space_or_tab":
        return character in {" ", "\t"}
    if kind == "arithmetic_operator":
        return character in {"+", "-", "*", "/", "%"}
    return character == kind.removeprefix("exact:")


def _rule(from_state: str, to_state: str, label: str, matcher: str) -> dict[str, str]:
    return {"from": from_state, "to": to_state, "label": label, "matcher": matcher}


AUTOMATA: dict[str, dict[str, Any]] = {
    "identifier": {
        "id": "identifier", "name": "Identifier", "description": "Educational recognizer for letter_or_underscore (letter_or_underscore | digit)*.",
        "pattern": "letter_or_underscore (letter_or_underscore | digit)*", "start_state": "q0", "accepting_states": ["q_identifier"],
        "states": [{"id": "q0", "label": "Start"}, {"id": "q_identifier", "label": "Identifier"}, {"id": "q_dead", "label": "Dead"}],
        "transitions": [_rule("q0", "q_identifier", "letter or _", "letter_or_underscore"), _rule("q_identifier", "q_identifier", "letter, _, or digit", "identifier_continue")],
        "examples": {"accepted": ["x", "_count", "student2"], "rejected": ["2student", "9value"]},
    },
    "integer": {
        "id": "integer", "name": "Integer", "description": "Recognizer for one or more decimal digits.", "pattern": "digit+", "start_state": "q0", "accepting_states": ["q_integer"],
        "states": [{"id": "q0", "label": "Start"}, {"id": "q_integer", "label": "Integer"}, {"id": "q_dead", "label": "Dead"}],
        "transitions": [_rule("q0", "q_integer", "digit", "digit"), _rule("q_integer", "q_integer", "digit", "digit")], "examples": {"accepted": ["0", "123"], "rejected": ["", "12a", "1.5"]},
    },
    "arithmetic_operator": {
        "id": "arithmetic_operator", "name": "Arithmetic operator", "description": "Recognizes exactly one operator from +, -, *, /, %.", "pattern": "one of + - * / %", "start_state": "q0", "accepting_states": ["q_accept"],
        "states": [{"id": "q0", "label": "Start"}, {"id": "q_accept", "label": "Accept"}, {"id": "q_dead", "label": "Dead"}],
        "transitions": [_rule("q0", "q_accept", "+ - * / %", "arithmetic_operator")], "examples": {"accepted": ["+", "%"], "rejected": ["++", "**"]},
    },
    "relational_operator": {
        "id": "relational_operator", "name": "Relational operator", "description": "Recognizes <, >, <=, >=, ==, or != with deterministic prefix states.", "pattern": "< | > | <= | >= | == | !=", "start_state": "q0", "accepting_states": ["q_lt", "q_gt", "q_equal", "q_not_equal"],
        "states": [{"id": "q0", "label": "Start"}, {"id": "q_lt", "label": "<"}, {"id": "q_gt", "label": ">"}, {"id": "q_equal_prefix", "label": "="}, {"id": "q_bang_prefix", "label": "!"}, {"id": "q_equal", "label": "== / !="}, {"id": "q_not_equal", "label": "<="}, {"id": "q_dead", "label": "Dead"}],
        "transitions": [_rule("q0", "q_lt", "<", "exact:<"), _rule("q0", "q_gt", ">", "exact:>"), _rule("q0", "q_equal_prefix", "=", "exact:="), _rule("q0", "q_bang_prefix", "!", "exact:!"), _rule("q_lt", "q_equal", "=", "exact:="), _rule("q_gt", "q_equal", "=", "exact:="), _rule("q_equal_prefix", "q_equal", "=", "exact:="), _rule("q_bang_prefix", "q_not_equal", "=", "exact:=")], "examples": {"accepted": ["<", "<=", "=="], "rejected": ["!", "=>"]},
    },
    "whitespace": {
        "id": "whitespace", "name": "Whitespace", "description": "Simplified recognizer for one or more spaces or tabs.", "pattern": "(space | tab)+", "start_state": "q0", "accepting_states": ["q_whitespace"],
        "states": [{"id": "q0", "label": "Start"}, {"id": "q_whitespace", "label": "Whitespace"}, {"id": "q_dead", "label": "Dead"}],
        "transitions": [_rule("q0", "q_whitespace", "space or tab", "space_or_tab"), _rule("q_whitespace", "q_whitespace", "space or tab", "space_or_tab")], "examples": {"accepted": [" ", "\t"], "rejected": ["a", ""]},
    },
}


def list_automata() -> list[dict[str, Any]]:
    return [{key: value for key, value in definition.items() if key not in {"states", "transitions"}} for definition in AUTOMATA.values()]


def get_automaton(automaton_id: str) -> dict[str, Any] | None:
    return AUTOMATA.get(automaton_id)


def simulate(automaton: dict[str, Any], input_text: str) -> dict[str, Any]:
    current = automaton["start_state"]
    trace: list[dict[str, Any]] = []
    failed_transition: dict[str, Any] | None = None
    for index, character in enumerate(input_text):
        rule = next((candidate for candidate in automaton["transitions"] if candidate["from"] == current and _matches(candidate["matcher"], character)), None)
        if rule is None:
            failed_transition = {"index": index, "character": character, "from_state": current, "to_state": "q_dead", "transition": "No valid transition"}
            trace.append({"step": len(trace) + 1, "index": index, "character": character, "current_state": current, "transition": "No valid transition", "next_state": "q_dead", "accepted": False})
            current = "q_dead"
            break
        trace.append({"step": len(trace) + 1, "index": index, "character": character, "current_state": current, "transition": rule["label"], "next_state": rule["to"], "accepted": True})
        current = rule["to"]
    accepted = current in automaton["accepting_states"] and failed_transition is None
    if failed_transition is not None:
        explanation = f"Input rejected at character {failed_transition['index']}: no transition from {failed_transition['from_state']} accepts {failed_transition['character']!r}."
    elif accepted:
        explanation = f"All {len(input_text)} character(s) were consumed and the automaton finished in accepting state {current}."
    else:
        explanation = f"All {len(input_text)} character(s) were consumed, but final state {current} is not accepting."
    return {"automaton_id": automaton["id"], "input": input_text, "trace": trace, "final_state": current, "accepted": accepted, "characters_processed": len(trace), "failed_transition": failed_transition, "explanation": explanation}
