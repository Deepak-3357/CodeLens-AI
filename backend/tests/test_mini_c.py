from app.languages.mini_c.analyzer import analyze_mini_c
from app.languages.mini_c.lexer import lex


def test_declaration_and_locations() -> None:
    tokens, diagnostics = lex("int x = 10;")
    assert not diagnostics
    assert [(token.type, token.lexeme) for token in tokens[:5]] == [("KEYWORD", "int"), ("IDENTIFIER", "x"), ("OPERATOR", "="), ("NUMBER", "10"), ("DELIMITER", ";")]
    assert tokens[0].line == 1 and tokens[0].column == 1


def test_parse_tree_contains_c_terminals_and_lexemes() -> None:
    result = analyze_mini_c('int x = 10; printf("%d", x);')
    tree = result["parse_tree"]
    declaration = tree["children"][0]
    assert [child["attributes"]["lexeme"] for child in declaration["children"][:3]] == ["int", "x", "="]
    assert declaration["children"][3]["children"][0]["attributes"]["lexeme"] == "10"
    printf = tree["children"][1]
    assert printf["children"][0]["attributes"]["lexeme"] == "printf"
    assert printf["children"][2]["children"][0]["attributes"]["lexeme"] == '"%d"'


def test_multiple_declarations_assignment_and_printf() -> None:
    result = analyze_mini_c('int x = 10; int y = 20; x = x + y; printf("%d", x);')
    assert result["success"]
    assert [child["type"] for child in result["tree"]["children"]] == ["Declaration", "Declaration", "Assignment", "PrintfStatement"]


def test_operator_precedence() -> None:
    result = analyze_mini_c("int result = 1 + 2 * 3;")
    expression = result["tree"]["children"][0]["children"][0]
    assert result["success"]
    assert expression["attributes"]["operator"] == "+"
    assert expression["children"][1]["attributes"]["operator"] == "*"


def test_parentheses_override_precedence() -> None:
    result = analyze_mini_c("int result = (1 + 2) * 3;")
    expression = result["tree"]["children"][0]["children"][0]
    assert result["success"]
    assert expression["attributes"]["operator"] == "*"
    assert expression["children"][0]["attributes"]["operator"] == "+"


def test_comments_and_nested_if_block() -> None:
    result = analyze_mini_c('// comment\nint x = 10; /* initializer */ if (x > 0) { printf("%d", x); } else { x = 0; }')
    assert result["success"]
    assert result["tree"]["children"][-1]["type"] == "IfStatement"


def test_missing_semicolon_is_incomplete() -> None:
    result = analyze_mini_c("int x = 10\nint y = 20;")
    assert not result["success"]
    assert any(item["code"] == "C_EXPECTED_TOKEN" for item in result["diagnostics"])
    assert result["tree"]["children"][0]["attributes"]["incomplete"] is True
    assert result["parse_status"] == "invalid_partial"
    assert result["tree_complete"] is False


def test_missing_initializer_and_invalid_operator_recover() -> None:
    result = analyze_mini_c("int x =;\nint y = 2 + ;\nint z = 3;")
    assert not result["success"]
    assert any(item["code"] == "C_EXPECTED_EXPRESSION" for item in result["diagnostics"])
    assert result["tree"]["children"][-1]["attributes"]["name"] == "z"


def test_invalid_source_keeps_partial_parse_tree_terminals() -> None:
    result = analyze_mini_c("int x =;")
    assert result["parse_tree"]["children"][0]["type"] == "Declaration"
    assert result["parse_tree"]["children"][0]["children"][3]["type"] == "ErrorExpression"
    assert result["parse_tree"]["children"][0]["children"][3]["children"][0]["attributes"]["lexeme"] == ";"


def test_delimiters_and_literals_diagnose() -> None:
    cases = {
        'printf("x";': "C_EXPECTED_TOKEN",
        'int x = 1; }': "C_UNEXPECTED_CLOSING_BRACE",
        'int x = 1; { int y = 2;': "C_EXPECTED_TOKEN",
        'int x = @;': "C_INVALID_CHARACTER",
        'printf("unterminated);': "C_UNTERMINATED_STRING",
        "char c = 'x;": "C_UNTERMINATED_CHARACTER",
        "int x = 1; /* open": "C_UNTERMINATED_COMMENT",
    }
    for source, code in cases.items():
        result = analyze_mini_c(source)
        assert not result["success"]
        assert any(item["code"] == code for item in result["diagnostics"])


def test_empty_and_unsupported_input() -> None:
    empty = analyze_mini_c("")
    assert any(item["code"] == "C_EMPTY_SOURCE" for item in empty["diagnostics"])
    assert empty["parse_status"] == "invalid_no_tree"
    assert empty["tree_complete"] is False
    result = analyze_mini_c("for (int i = 0; i < 3; i = i + 1) { }")
    assert not result["success"]
