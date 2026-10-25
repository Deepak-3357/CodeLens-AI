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


def test_nested_while_pattern_subset_is_complete() -> None:
    result = analyze_mini_c(
        'int n = 4; int i = 0; '
        'while (i < n) { '
        'int j = 0; '
        'while (j <= i) { printf("*"); j = j + 1; } '
        'i = i + 1; '
        '}'
    )

    assert result["success"]
    assert result["diagnostics"] == []
    assert result["parse_status"] == "valid_complete"
    assert result["tree_complete"] is True
    outer_loop = result["tree"]["children"][2]
    assert outer_loop["type"] == "WhileStatement"
    assert outer_loop["children"][1]["type"] == "BlockStatement"
    inner_loop = outer_loop["children"][1]["children"][1]
    assert inner_loop["type"] == "WhileStatement"
    assert inner_loop["children"][1]["children"][0]["type"] == "PrintfStatement"
    assert result["parse_tree"]["children"][2]["children"][0]["attributes"]["lexeme"] == "while"


def test_c_pattern_program_with_include_main_and_nested_for_is_complete() -> None:
    source = '''#include <stdio.h>

int main(void) {
    int n = 4;
    for (int i = 0; i < n; i++) {
        for (int j = 0; j <= i; j++) {
            printf("*");
        }
        printf("\\n");
    }
    return 0;
}
'''
    result = analyze_mini_c(source)

    assert result["success"]
    assert result["diagnostics"] == []
    assert result["parse_status"] == "valid_complete"
    assert result["tree_complete"] is True
    function = result["tree"]["children"][1]
    assert function["type"] == "FunctionDefinition"
    outer = function["children"][0]["children"][1]
    assert outer["type"] == "ForStatement"
    assert outer["children"][3]["children"][0]["type"] == "ForStatement"
    assert result["parse_tree"]["children"][0]["children"][0]["attributes"]["lexeme"] == "#include <stdio.h>"


def test_c_arrays_indexing_and_basic_pointers_are_structured() -> None:
    result = analyze_mini_c("int values[3]; values[0] = 1; int *pointer; int value = 2; pointer = &value;")

    assert result["success"]
    assert result["diagnostics"] == []
    assert result["tree"]["children"][0]["attributes"]["array"] is True
    assert result["tree"]["children"][1]["children"][0]["type"] == "IndexExpression"
    assert result["tree"]["children"][2]["attributes"]["pointer"] is True
    assert result["tree"]["children"][4]["children"][0]["attributes"]["operator"] == "&"


def test_c_do_while_switch_and_control_statements() -> None:
    result = analyze_mini_c(
        "int value = 1; do { switch (value) { case 1: value = 2; break; default: continue; } } while (value < 2);"
    )

    assert result["success"]
    assert result["diagnostics"] == []
    assert result["tree"]["children"][1]["type"] == "DoWhileStatement"
    switch = result["tree"]["children"][1]["children"][0]["children"][0]
    assert switch["type"] == "SwitchStatement"
    assert switch["children"][1]["type"] == "CaseStatement"
    assert switch["children"][2]["attributes"]["default"] is True


def test_c_function_prototype_and_indented_include_are_supported() -> None:
    result = analyze_mini_c('  #include "myheader.h"\nint add(int left, int right); int value = add(1, 2);')

    assert result["success"]
    assert result["diagnostics"] == []
    assert result["tree"]["children"][0]["type"] == "IncludeDirective"
    assert result["tree"]["children"][1]["type"] == "FunctionPrototype"
    assert result["tree"]["children"][2]["children"][0]["type"] == "CallExpression"


def test_c_logical_and_compound_assignment_expressions() -> None:
    result = analyze_mini_c("int x = 1; int y = 2; if (x < y && y > 0 || x == 0) { x += y; }")

    assert result["success"]
    assert result["diagnostics"] == []
    condition = result["tree"]["children"][2]["children"][0]
    assert condition["attributes"]["operator"] == "||"
    assert result["tree"]["children"][2]["children"][1]["children"][0]["attributes"]["operator"] == "+="


def test_c_const_declaration_is_structured() -> None:
    result = analyze_mini_c("const int limit = 4;")
    assert result["success"]
    assert result["tree"]["children"][0]["attributes"]["const"] is True


def test_c_struct_enum_and_typedef_declarations_are_structured() -> None:
    result = analyze_mini_c("typedef int Count; struct Point { int x; int y; }; enum Color { RED, BLUE }; Count total;")

    assert result["success"]
    assert result["diagnostics"] == []
    assert [child["type"] for child in result["tree"]["children"][:3]] == ["TypedefDeclaration", "StructDeclaration", "EnumDeclaration"]
    assert result["tree"]["children"][1]["children"][0]["attributes"]["name"] == "x"


def test_c_multiple_declarators_named_struct_variables_and_array_initializers() -> None:
    result = analyze_mini_c(
        "struct Point { int x; int y; }; "
        "struct Point first, second; "
        "int values[3] = {1, 2, 3}; "
        "int left = 1, right = 2;"
    )

    assert result["success"]
    assert result["diagnostics"] == []
    assert result["tree"]["children"][1]["attributes"]["type_name"] == "Point"
    assert len(result["tree"]["children"][3]["attributes"]["additional_declarators"]) == 1
    assert result["tree"]["children"][2]["children"][-1]["type"] == "InitializerList"
    assert any(child["type"] == "InitializerList" for child in result["parse_tree"]["children"][2]["children"])


def test_c_struct_typedef_and_enum_value_initializers() -> None:
    result = analyze_mini_c(
        "typedef struct Point Point; "
        "enum Color { RED = 1, BLUE = 2 }; "
        "Point point;"
    )

    assert result["success"]
    assert result["diagnostics"] == []
    assert result["tree"]["children"][0]["attributes"]["type_name"] == "Point"
    assert result["tree"]["children"][1]["children"][0]["children"][0]["attributes"]["value"] == "1"
    assert result["tree"]["children"][2]["attributes"]["declared_type"] == "Point"


def test_c_shift_member_update_and_malformed_include_diagnostics() -> None:
    valid = analyze_mini_c(
        '#include <stdio.h>\n'
        'struct Point { int x; };\n'
        'struct Point point;\n'
        'struct Point *pointer;\n'
        'int value = point.x;\n'
        'value = (value << 1) | 1;\n'
        'value++;\n'
        '--value;\n'
        'int other = pointer->x;\n'
    )
    invalid = analyze_mini_c('#include\nint value = 1;')

    assert valid["success"]
    assert valid["diagnostics"] == []
    assert [child["type"] for child in valid["tree"]["children"]].count("UpdateStatement") == 2
    assert invalid["success"] is False
    assert invalid["parse_status"] == "invalid_partial"
    assert invalid["tree_complete"] is False
    assert invalid["diagnostics"][0]["code"] == "C_MALFORMED_INCLUDE"


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
    malformed = analyze_mini_c("for (int i = 0; i < 3 i = i + 1) { }")
    assert not malformed["success"]
    assert any(item["code"] == "C_EXPECTED_TOKEN" for item in malformed["diagnostics"])


def test_function_for_and_return_pattern_is_supported() -> None:
    source = "int main() { for (int i = 0; i < 3; i = i + 1) { printf(\"*\"); } return 0; }"
    result = analyze_mini_c(source)

    assert result["lexical_valid"]
    assert result["success"]
    assert result["diagnostics"] == []
    assert result["parse_status"] == "valid_complete"
    assert result["tree_complete"] is True
