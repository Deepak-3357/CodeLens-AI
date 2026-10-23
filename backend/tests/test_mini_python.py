from app.languages.mini_python.analyzer import analyze_mini_python
from app.languages.mini_python.lexer import lex


def test_lexer_tracks_locations_and_keywords() -> None:
    tokens, diagnostics = lex("x = 10\nprint(x)\n")
    assert not diagnostics
    assert [(token.type, token.lexeme) for token in tokens[:6]] == [
        ("IDENTIFIER", "x"), ("OPERATOR", "="), ("NUMBER", "10"), ("NEWLINE", ""),
        ("KEYWORD", "print"), ("DELIMITER", "("),
    ]
    assert tokens[0].line == 1 and tokens[0].column == 1
    assert tokens[4].line == 2 and tokens[4].column == 1


def test_operator_precedence() -> None:
    result = analyze_mini_python("print(1 + 2 * 3)\n")
    assert result["success"]
    expression = result["tree"]["children"][0]["children"][0]
    assert expression["type"] == "BinaryExpression"
    assert expression["attributes"]["operator"] == "+"
    assert expression["children"][1]["attributes"]["operator"] == "*"


def test_parentheses_override_precedence() -> None:
    result = analyze_mini_python("x = (1 + 2) * 3\n")
    assert result["success"]
    expression = result["tree"]["children"][0]["children"][0]
    assert expression["attributes"]["operator"] == "*"
    assert expression["children"][0]["attributes"]["operator"] == "+"


def test_indented_if_block() -> None:
    result = analyze_mini_python("if True:\n    x = 1\n")
    assert result["success"]
    assert result["tree"]["children"][0]["type"] == "IfStatement"


def test_if_else_block() -> None:
    result = analyze_mini_python("if True:\n    x = 1\nelse:\n    x = 2\n")
    assert result["success"]
    assert result["tree"]["children"][0]["children"][-1]["type"] == "ElseStatement"


def test_invalid_program_has_diagnostic_and_no_success() -> None:
    result = analyze_mini_python("print(1 + 2\n")
    assert not result["success"]
    assert any(item["code"] == "PY_EXPECTED_TOKEN" for item in result["diagnostics"])


def test_lexical_errors_are_safe() -> None:
    result = analyze_mini_python("x = @\n")
    assert not result["lexical_valid"]
    assert any(item["code"] == "PY_INVALID_CHARACTER" for item in result["diagnostics"])


def test_empty_and_unsupported_input() -> None:
    empty = analyze_mini_python("")
    assert not empty["success"]
    assert any(item["code"] == "PY_EMPTY_SOURCE" for item in empty["diagnostics"])
    unsupported = analyze_mini_python("for x in y:\n    print(x)\n")
    assert not unsupported["success"]
