import pytest
from fastapi.testclient import TestClient

from app.automata import AUTOMATA, get_automaton, simulate
from app.main import app


client = TestClient(app)


@pytest.mark.parametrize("automaton_id, accepted, rejected", [
    ("identifier", ["x", "_count", "student2"], ["2student", "9value"]),
    ("integer", ["0", "123"], ["", "12a", "1.5"]),
    ("arithmetic_operator", ["+", "%"], ["++", "**"]),
    ("relational_operator", ["<", "<=", "==", "!="], ["!", "=>"]),
    ("whitespace", [" ", "\t"], ["a", ""]),
])
def test_supported_automata_examples(automaton_id: str, accepted: list[str], rejected: list[str]) -> None:
    automaton = get_automaton(automaton_id)
    assert automaton is not None
    for value in accepted:
        result = simulate(automaton, value)
        assert result["accepted"] is True, (automaton_id, value, result)
        assert result["final_state"] in automaton["accepting_states"]
        assert result["characters_processed"] == len(value)
    for value in rejected:
        assert simulate(automaton, value)["accepted"] is False


def test_trace_is_deterministic_and_records_transitions() -> None:
    result = simulate(AUTOMATA["identifier"], "x2")
    assert result["accepted"]
    assert [step["current_state"] for step in result["trace"]] == ["q0", "q_identifier"]
    assert [step["next_state"] for step in result["trace"]] == ["q_identifier", "q_identifier"]


def test_missing_transition_is_reported() -> None:
    result = simulate(AUTOMATA["integer"], "12a")
    assert not result["accepted"]
    assert result["failed_transition"]["index"] == 2
    assert result["trace"][-1]["next_state"] == "q_dead"


def test_automata_api_and_validation() -> None:
    listing = client.get("/api/automata")
    assert listing.status_code == 200
    assert {item["id"] for item in listing.json()["automata"]} == set(AUTOMATA)
    detail = client.get("/api/automata/relational_operator")
    assert detail.status_code == 200
    assert detail.json()["start_state"] == "q0"
    simulation = client.post("/api/automata/identifier/simulate", json={"input": "student2"})
    assert simulation.status_code == 200
    assert simulation.json()["accepted"] is True
    assert client.get("/api/automata/nope").status_code == 404


def test_automata_input_limit_and_malformed_request() -> None:
    assert client.post("/api/automata/integer/simulate", json={"input": "x" * 2001}).status_code == 422
    assert client.post("/api/automata/integer/simulate", json={}).status_code == 422
    assert client.post("/api/automata/integer/simulate", json={"input": 123}).status_code == 422
