from app.languages.mini_cpp.analyzer import analyze_mini_cpp


def test_cpp_nested_control_flow_functions_and_output_are_complete() -> None:
    result = analyze_mini_cpp(
        '#include <iostream>\n'
        'int add(int a, int b) { return a + b; }\n'
        'int main() {\n'
        '  int total = 0;\n'
        '  for (int i = 0; i < 3; i++) {\n'
        '    if (i > 0) { total += i; } else { total = add(total, 1); }\n'
        '  }\n'
        '  std::cout << total << std::endl;\n'
        '}\n'
    )
    assert result["success"] is True
    assert result["parse_status"] == "valid_complete"
    assert result["tree_complete"] is True
    assert result["diagnostics"] == []
    assert result["tree"]["children"][1]["type"] == "FunctionDefinition"
    assert result["parse_tree"]["type"] == "Program"


def test_cpp_precedence_and_parentheses_are_structured() -> None:
    result = analyze_mini_cpp("int value = (2 + 3) * 4;\n")
    assert result["success"] is True
    declaration = result["tree"]["children"][0]
    expression = declaration["children"][0]["children"][0]
    assert expression["type"] == "BinaryExpression"
    assert expression["attributes"]["operator"] == "*"


def test_cpp_lexical_diagnostic_has_location() -> None:
    result = analyze_mini_cpp("int value = 1 @ 2;\n")
    assert result["success"] is False
    diagnostic = result["diagnostics"][0]
    assert diagnostic["code"] == "CPP_INVALID_CHARACTER"
    assert diagnostic["line"] == 1
    assert diagnostic["column"] == 15
    assert result["tree_complete"] is False


def test_cpp_missing_delimiter_is_partial() -> None:
    result = analyze_mini_cpp("int main() { std::cout << 1 << std::endl;\n")
    assert result["success"] is False
    assert result["parse_status"] == "invalid_partial"
    assert result["tree"] is not None
    assert result["tree_complete"] is False
    assert any(item["code"] == "CPP_EXPECTED_TOKEN" for item in result["diagnostics"])
