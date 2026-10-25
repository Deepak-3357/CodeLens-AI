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
    malformed = analyze_mini_python("for x range(3):\n    print(x)\n")
    assert not malformed["success"]
    assert any(item["code"] == "PY_EXPECTED_TOKEN" for item in malformed["diagnostics"])


def test_nested_for_range_pattern_tokens_are_classified_as_keywords() -> None:
    source = 'n = 4\nfor i in range(n):\n    for j in range(i + 1):\n        print("*")\n'
    tokens, lexical_diagnostics = lex(source)
    result = analyze_mini_python(source)

    assert not lexical_diagnostics
    assert [(token.type, token.lexeme) for token in tokens[4:8]] == [
        ("KEYWORD", "for"),
        ("IDENTIFIER", "i"),
        ("KEYWORD", "in"),
        ("IDENTIFIER", "range"),
    ]
    assert result["diagnostics"] == []
    assert result["parse_status"] == "valid_complete"
    assert result["tree_complete"] is True


def test_nested_for_range_pattern_is_supported() -> None:
    result = analyze_mini_python('n = 4\nfor i in range(n):\n    for j in range(i + 1):\n        print("*")\n')

    assert result["success"]
    assert result["diagnostics"] == []
    assert result["parse_status"] == "valid_complete"
    assert result["tree_complete"] is True
    outer = result["tree"]["children"][1]
    assert outer["type"] == "ForStatement"
    assert outer["children"][2]["type"] == "ForStatement"
    assert outer["children"][2]["children"][2]["type"] == "PrintStatement"
    assert result["parse_tree"]["children"][1]["children"][0]["attributes"]["lexeme"] == "for"


def test_python_imports_and_function_syntax_are_static_only() -> None:
    result = analyze_mini_python('import math as m\nfrom math import sqrt\ndef area(x):\n    return sqrt(x)\n')
    assert result["success"]
    assert result["parse_status"] == "valid_complete"


def test_python_collections_indexing_slicing_and_member_calls() -> None:
    result = analyze_mini_python(
        'items = [1, 2, 3]\n'
        'mapping = {"first": items[0]}\n'
        'pair = (items[0], items[1])\n'
        'print(items[0:2])\n'
        'print(pair.count(1))\n'
    )

    assert result["success"]
    assert result["diagnostics"] == []
    assert result["tree"]["children"][0]["children"][0]["type"] == "ListLiteral"
    assert result["tree"]["children"][1]["children"][0]["type"] == "DictLiteral"
    assert result["tree"]["children"][3]["children"][0]["type"] == "SliceExpression"
    assert result["tree"]["children"][4]["children"][0]["type"] == "CallExpression"
    assert result["parse_tree"]["children"][0]["children"][2]["children"][0]["attributes"]["lexeme"] == "["


def test_python_try_except_finally_raise_and_with_syntax() -> None:
    result = analyze_mini_python(
        'try:\n'
        '    raise error\n'
        'except Error as caught:\n'
        '    print(caught)\n'
        'finally:\n'
        '    pass\n'
        'with resource as handle:\n'
        '    print(handle)\n'
    )

    assert result["success"]
    assert result["diagnostics"] == []
    assert result["tree"]["children"][0]["type"] == "TryStatement"
    assert result["tree"]["children"][1]["type"] == "WithStatement"


def test_python_multiple_assignment_and_keyword_arguments() -> None:
    result = analyze_mini_python('left = right = 1\nprint(round(number=left))\n')

    assert result["success"]
    assert result["diagnostics"] == []
    assert result["tree"]["children"][0]["attributes"]["targets"] == ["left", "right"]
    assert result["tree"]["children"][1]["children"][0]["children"][1]["type"] == "KeywordArgument"


def test_python_bitwise_expressions_and_chained_elif() -> None:
    result = analyze_mini_python('value = 3 & 1\nif value == 0:\n    print(0)\nelif value == 1:\n    print(1)\nelif value == 2:\n    print(2)\nelse:\n    print(3)\n')

    assert result["success"]
    assert result["diagnostics"] == []
    condition = result["tree"]["children"][0]["children"][0]
    assert condition["attributes"]["operator"] == "&"
    branch = result["tree"]["children"][1]
    while branch["children"][-1]["type"] == "ElifStatement":
        branch = branch["children"][-1]
    assert branch["children"][-1]["type"] == "ElseStatement"


def test_python_conditional_lambda_scope_and_parenthesized_imports() -> None:
    result = analyze_mini_python(
        'from math import (sqrt, sin)\n'
        'def choose(value):\n'
        '    global selected\n'
        '    selected = (lambda x: x + 1)(value) if value > 0 else 0\n'
        '    return selected\n'
    )

    assert result["success"]
    assert result["diagnostics"] == []
    assert result["tree"]["children"][0]["attributes"]["parenthesized"] is True
    function_body = result["tree"]["children"][1]["children"]
    assert function_body[1]["type"] == "ScopeStatement"
    assert function_body[2]["children"][0]["type"] == "ConditionalExpression"


def test_python_membership_identity_floor_power_shift_none_and_loop_else() -> None:
    result = analyze_mini_python(
        'values = [1, 2, 3]\n'
        'if 2 in values and 4 not in values and None is not values:\n'
        '    total = 2 ** 3 // 2\n'
        'else:\n'
        '    total = 0\n'
        'while total > 0:\n'
        '    total -= 1\n'
        'else:\n'
        '    pass\n'
    )

    assert result["success"]
    assert result["diagnostics"] == []
    assert result["tree"]["children"][1]["children"][0]["attributes"]["operator"] == "and"
    assert result["tree"]["children"][2]["children"][-1]["type"] == "ElseStatement"
    assert result["parse_tree"]["children"][0]["children"][0]["attributes"]["lexeme"] == "values"


def test_python_indexed_and_member_assignment_targets() -> None:
    result = analyze_mini_python('items = [0]\nitems[0] += 1\nrecord.value = items[0]\n')

    assert result["success"]
    assert result["diagnostics"] == []
    assert result["tree"]["children"][1]["children"][0]["type"] == "IndexExpression"
    assert result["tree"]["children"][2]["children"][0]["type"] == "MemberExpression"


def test_python_tuple_unpacking_default_parameters_and_starred_arguments() -> None:
    result = analyze_mini_python(
        'first, second = (1, 2)\n'
        'def show(value=0):\n'
        '    print(*value)\n'
        'show(first)\n'
    )

    assert result["success"]
    assert result["diagnostics"] == []
    assert result["tree"]["children"][0]["attributes"]["targets"] == ["first", "second"]
    assert result["tree"]["children"][1]["children"][0]["type"] == "Parameter"


def test_python_print_keywords_expression_statements_and_import_aliases() -> None:
    result = analyze_mini_python(
        'import math\n'
        'from math import sqrt as root, sin\n'
        'items = [1, 2]\n'
        'print(*items, sep=", ")\n'
        'items[0]\n'
    )

    assert result["success"]
    assert result["diagnostics"] == []
    assert result["tree"]["children"][3]["children"][0]["type"] == "StarArgument"
    assert result["tree"]["children"][3]["children"][1]["type"] == "KeywordArgument"
    assert result["tree"]["children"][4]["type"] == "ExpressionStatement"
