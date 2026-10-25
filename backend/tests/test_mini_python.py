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


def test_parse_tree_contains_grammar_nodes_terminal_lexemes_and_locations() -> None:
    result = analyze_mini_python("x = 10\nprint(x)\n")
    tree = result["parse_tree"]
    assert tree["type"] == "Program"
    assignment = tree["children"][0]
    assert assignment["type"] == "Assignment"
    assert [(child["attributes"]["token_type"], child["attributes"]["lexeme"]) for child in assignment["children"][:2]] == [("IDENTIFIER", "x"), ("OPERATOR", "=")]
    number = assignment["children"][2]
    assert number["type"] == "NumberLiteral"
    assert number["children"][0]["attributes"]["lexeme"] == "10"
    assert number["children"][0]["attributes"]["line"] == 1
    assert tree["children"][1]["children"][0]["attributes"]["lexeme"] == "print"


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
    assert result["parse_status"] == "invalid_partial"
    assert result["tree_complete"] is False


def test_missing_assignment_expression_is_explicitly_incomplete() -> None:
    result = analyze_mini_python("x =\n")
    assert not result["success"]
    assert [(item["code"], item["line"], item["column"]) for item in result["diagnostics"]] == [("PY_EXPECTED_EXPRESSION", 1, 4)]
    assignment = result["tree"]["children"][0]
    assert assignment["attributes"]["incomplete"] is True
    assert assignment["children"][0]["type"] == "ErrorExpression"
    assert result["parse_tree"]["children"][0]["children"][2]["type"] == "ErrorExpression"
    assert result["parse_tree"]["children"][0]["children"][2]["children"][0]["attributes"]["token_type"] == "EOF"


def test_invalid_print_does_not_cascade_missing_close() -> None:
    result = analyze_mini_python("print(1 + )\n")
    assert not result["success"]
    assert [(item["code"], item["line"], item["column"]) for item in result["diagnostics"]] == [("PY_INVALID_EXPRESSION", 1, 11)]
    statement = result["tree"]["children"][0]
    assert statement["attributes"]["incomplete"] is True
    assert statement["children"][0]["children"][1]["type"] == "ErrorExpression"


def test_combined_malformed_program_keeps_both_partial_statements() -> None:
    result = analyze_mini_python("x =\nprint(1 + )\n")
    assert not result["success"]
    assert [item["code"] for item in result["diagnostics"]] == ["PY_EXPECTED_EXPRESSION", "PY_INVALID_EXPRESSION"]
    assert len(result["tree"]["children"]) == 2


def test_recovery_preserves_valid_sibling_statement() -> None:
    result = analyze_mini_python("x =\nprint(1 + )\ny = 20\n")
    assert not result["success"]
    assert len(result["tree"]["children"]) == 3
    assert result["tree"]["children"][2]["attributes"]["target"] == "y"
    assert "incomplete" not in result["tree"]["children"][2]["attributes"]


def test_genuinely_missing_closing_parenthesis_is_reported() -> None:
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
    assert empty["parse_status"] == "invalid_no_tree"
    assert empty["tree_complete"] is False
    unsupported = analyze_mini_python("for x in y:\n    print(x)\n")
    assert not unsupported["success"]
