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


def test_cpp_beginner_hello_world_variants_are_complete() -> None:
    for source in (
        '#include <iostream>\nusing namespace std;\nint main() { cout << "Hello, World!" << endl; return 0; }',
        '#include <iostream>\nint main() { std::cout << "Hello" << std::endl; return 0; }',
    ):
        result = analyze_mini_cpp(source)
        assert result["parse_status"] == "valid_complete"
        assert result["tree_complete"] is True
        assert result["diagnostics"] == []


def test_cpp_declarations_input_and_control_flow_are_complete() -> None:
    result = analyze_mini_cpp(
        '#include <iostream>\n'
        'using namespace std;\n'
        'int main() {\n'
        '  int a = 10, b = 20;\n'
        '  int sum = a + b;\n'
        '  int age;\n'
        '  cin >> age;\n'
        '  for (int i = 0; i < 5; i++) { if (i % 2 == 0) { cout << i << endl; } }\n'
        '  return 0;\n'
        '}',
    )
    assert result["success"] is True
    assert result["parse_status"] == "valid_complete"
    assert result["tree_complete"] is True


def test_cpp_supported_types_arrays_and_using_declarations_are_complete() -> None:
    result = analyze_mini_cpp(
        '#include <string>\n'
        'using std::cout;\n'
        'using std::endl;\n'
        'int main() { long long count = 2; std::string text = "ok"; int values[2] = {1, 2}; cout << text << endl; return 0; }',
    )
    assert result["success"] is True
    assert result["tree_complete"] is True


def test_cpp_malformed_and_unsupported_syntax_is_not_accepted() -> None:
    cases = (
        "int main() { int value = 10 return 0; }",
        "int main() { int value = 10; return 0;",
        "int main() { int value = 5 + ; return 0; }",
        "template <typename T> class Box {};",
        "",
    )
    for source in cases:
        result = analyze_mini_cpp(source)
        assert result["success"] is False
        assert result["tree_complete"] is False
        assert result["diagnostics"]
        assert result["parse_status"] in {"invalid_partial", "invalid_no_tree"}


def test_cpp_comments_escaped_literals_and_multiple_headers_preserve_locations() -> None:
    result = analyze_mini_cpp(
        '#include <iostream>\n'
        '#include <vector>\n'
        '// comment\n'
        'int main() { std::cout << "escaped \\\"quote\\\"" << std::endl; return 0; }',
    )
    assert result["success"] is True
    assert result["tree_complete"] is True
    assert result["tokens"][0]["type"] == "PREPROCESSOR"

    invalid = analyze_mini_cpp("int value = 1 @ 2;")
    diagnostic = invalid["diagnostics"][0]
    assert diagnostic["code"] == "CPP_INVALID_CHARACTER"
    assert diagnostic["line"] == 1
    assert diagnostic["column"] == 15
