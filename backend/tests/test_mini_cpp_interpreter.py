import pytest

from app.languages.mini_cpp.analyzer import analyze_mini_cpp
from app.languages.mini_cpp.interpreter import execute_mini_cpp


def run(source: str, stdin: str = ""):
    analysis = analyze_mini_cpp(source)
    assert analysis["success"] is True
    return execute_mini_cpp(analysis["tree"], stdin)


def test_interprets_arithmetic_and_variable_assignment() -> None:
    result = run("int a = 10; int b = 20; int total = a + b; total = total + 1; cout << total;")
    assert result.status == "Success"
    assert result.stdout == "31"


def test_interprets_chained_output_and_strings() -> None:
    result = run('std::cout << "Result: " << 10 + 20 << std::endl;')
    assert result.status == "Success"
    assert result.stdout == "Result: 30\n"


def test_interprets_main_function_and_cin() -> None:
    result = run('int main() { int age; cin >> age; cout << "Age: " << age << endl; return 0; }', "21")
    assert result.status == "Success"
    assert result.stdout == "Age: 21\n"


def test_rejects_invalid_syntax_before_interpreter() -> None:
    analysis = analyze_mini_cpp("int value = 10")
    assert analysis["success"] is False
    assert analysis["diagnostics"]


def test_reports_division_by_zero() -> None:
    result = run("int value = 10 / 0; cout << value;")
    assert result.status == "Error"
    assert result.error_category == "runtime"
    assert "Division by zero" in result.stderr


def test_reports_unsupported_statement() -> None:
    result = run("int main() { for (int i = 0; i < 2; i++) { cout << i; } return 0; }")
    assert result.status == "Error"
    assert result.error_category == "unsupported"
    assert "does not support statement" in result.stderr


def test_enforces_step_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODELENS_MINI_CPP_MAX_STEPS", "3")
    result = run("int value = 10; cout << value;")
    assert result.status == "Error"
    assert result.error_category == "resource_limit"
    assert "step limit" in result.stderr


def test_enforces_output_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODELENS_MINI_CPP_MAX_OUTPUT_LENGTH", "3")
    result = run('cout << "abcd";')
    assert result.status == "Error"
    assert result.error_category == "resource_limit"
    assert "output limit" in result.stderr
