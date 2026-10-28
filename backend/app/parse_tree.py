from __future__ import annotations

from typing import Any


LAYOUT_TOKENS = {"NEWLINE", "INDENT", "DEDENT"}


def terminal(token: Any) -> dict[str, Any]:
    return {
        "type": "Terminal",
        "attributes": {
            "token_type": token.type,
            "lexeme": token.lexeme,
            "line": token.line,
            "column": token.column,
            "end_line": token.end_line,
            "end_column": token.end_column,
        },
    }


class TokenCursor:
    def __init__(self, tokens: list[Any]) -> None:
        self.tokens = tokens
        self.index = 0

    def _skip_layout(self) -> None:
        while self.index < len(self.tokens) and self.tokens[self.index].type in LAYOUT_TOKENS:
            self.index += 1

    def take(self, token_type: str | None = None, lexeme: str | None = None) -> dict[str, Any] | None:
        self._skip_layout()
        for index in range(self.index, len(self.tokens)):
            token = self.tokens[index]
            if token.type in LAYOUT_TOKENS:
                continue
            if (token_type is None or token.type == token_type) and (lexeme is None or token.lexeme == lexeme):
                self.index = index + 1
                return terminal(token)
            if index - self.index > 3:
                break
        return None


def node(node_type: str, children: list[dict[str, Any]] | None = None, **attributes: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"type": node_type}
    if attributes:
        result["attributes"] = attributes
    if children is not None:
        result["children"] = children
    return result


def build_parse_tree(ast: dict[str, Any] | None, tokens: list[Any], language: str) -> dict[str, Any] | None:
    if ast is None:
        return None
    cursor = TokenCursor(tokens)

    def expression(ast_node: dict[str, Any] | None) -> dict[str, Any] | None:
        return build(ast_node) if ast_node else None

    def build(ast_node: dict[str, Any] | None) -> dict[str, Any] | None:
        if not ast_node or not isinstance(ast_node, dict):
            return None
        node_type = ast_node.get("type", "Unknown")
        attributes = ast_node.get("attributes", {}) if isinstance(ast_node.get("attributes", {}), dict) else {}
        ast_children = ast_node.get("children", []) if isinstance(ast_node.get("children", []), list) else []
        children: list[dict[str, Any]] = []

        def add(value: dict[str, Any] | None) -> None:
            if value is not None:
                children.append(value)

        if node_type == "Program":
            for child in ast_children:
                add(build(child))
        elif node_type == "Assignment":
            complex_target = bool(ast_children and ast_children[0].get("type") in {"IndexExpression", "MemberExpression"} and len(ast_children) > 1)
            if complex_target:
                add(build(ast_children[0]))
                add(cursor.take("OPERATOR", "="))
                add(expression(ast_children[1]))
            elif isinstance(attributes.get("targets"), list):
                targets = attributes["targets"]
                for index, target in enumerate(targets):
                    add(cursor.take("IDENTIFIER", target))
                    add(cursor.take("OPERATOR", "=")) if index < len(targets) - 1 else None
                add(cursor.take("OPERATOR", "="))
                add(expression(ast_children[0] if ast_children else None))
            else:
                add(cursor.take("IDENTIFIER", attributes.get("target")))
                add(cursor.take("OPERATOR", attributes.get("operator", "=")))
                add(expression(ast_children[0] if ast_children else None))
            if language == "mini_c":
                add(cursor.take("DELIMITER", ";"))
        elif node_type == "AssignmentExpression":
            add(cursor.take("IDENTIFIER", attributes.get("target")))
            add(cursor.take("OPERATOR", attributes.get("operator", "=")))
            add(build(ast_children[0]) if ast_children else None)
        elif node_type == "KeywordArgument":
            add(cursor.take("IDENTIFIER", attributes.get("name")))
            add(cursor.take("OPERATOR", "="))
            add(build(ast_children[0]) if ast_children else None)
        elif node_type == "Declaration":
            if attributes.get("const"):
                add(cursor.take("KEYWORD", "const"))
            if attributes.get("type_name"):
                add(cursor.take("KEYWORD", attributes.get("declared_type")))
                add(cursor.take("IDENTIFIER", attributes.get("type_name")))
            else:
                add(cursor.take("KEYWORD", attributes.get("declared_type")))
            if attributes.get("pointer"):
                add(cursor.take("OPERATOR", "*"))
            add(cursor.take("IDENTIFIER", attributes.get("name")))
            dimension_count = 0
            while dimension_count < len(ast_children) and ast_children[dimension_count].get("type") == "ArrayDimension":
                add(cursor.take("DELIMITER", "["))
                dimension = ast_children[dimension_count].get("children", [])
                add(build(dimension[0]) if dimension else None)
                add(cursor.take("DELIMITER", "]"))
                dimension_count += 1
            if len(ast_children) > dimension_count:
                add(cursor.take("OPERATOR", "="))
                add(expression(ast_children[dimension_count]))
            for additional in attributes.get("additional_declarators", []):
                add(cursor.take("DELIMITER", ","))
                if additional.get("pointer"):
                    add(cursor.take("OPERATOR", "*"))
                add(cursor.take("IDENTIFIER", additional.get("name")))
                if additional.get("expression") is not None:
                    add(cursor.take("OPERATOR", "="))
                    add(expression(additional.get("expression")))
            add(cursor.take("DELIMITER", ";"))
        elif node_type == "TypedefDeclaration":
            add(cursor.take("KEYWORD", "typedef"))
            add(cursor.take("KEYWORD", attributes.get("declared_type")))
            if attributes.get("type_name"):
                add(cursor.take("IDENTIFIER", attributes.get("type_name")))
            add(cursor.take("IDENTIFIER", attributes.get("name")))
            add(cursor.take("DELIMITER", ";"))
        elif node_type == "StructDeclaration":
            add(cursor.take("KEYWORD", "struct"))
            add(cursor.take("IDENTIFIER", attributes.get("name")))
            if ast_children:
                add(cursor.take("DELIMITER", "{"))
                for child in ast_children:
                    add(build(child))
                add(cursor.take("DELIMITER", "}"))
            add(cursor.take("DELIMITER", ";"))
        elif node_type == "EnumDeclaration":
            add(cursor.take("KEYWORD", "enum"))
            add(cursor.take("IDENTIFIER", attributes.get("name")))
            add(cursor.take("DELIMITER", "{"))
            for index, child in enumerate(ast_children):
                add(cursor.take("IDENTIFIER", child.get("attributes", {}).get("name")))
                if child.get("children"):
                    add(cursor.take("OPERATOR", "="))
                    add(expression(child["children"][0]))
                if index < len(ast_children) - 1:
                    add(cursor.take("DELIMITER", ","))
            add(cursor.take("DELIMITER", "}")); add(cursor.take("DELIMITER", ";"))
        elif node_type == "IncludeDirective":
            value = attributes.get("value")
            add(cursor.take("PREPROCESSOR", value))
        elif node_type in {"FunctionDefinition", "FunctionPrototype"}:
            add(cursor.take("KEYWORD", attributes.get("return_type")))
            add(cursor.take("IDENTIFIER", attributes.get("name")))
            add(cursor.take("DELIMITER", "("))
            parameter_count = 0
            while parameter_count < len(ast_children) and ast_children[parameter_count].get("type") == "Parameter":
                child = ast_children[parameter_count]
                parameter_type = child.get("attributes", {}).get("declared_type")
                parameter_name = child.get("attributes", {}).get("name")
                add(cursor.take("KEYWORD", parameter_type))
                add(cursor.take("IDENTIFIER", parameter_name))
                parameter_count += 1
                if parameter_count < len(ast_children) and ast_children[parameter_count].get("type") == "Parameter":
                    add(cursor.take("DELIMITER", ","))
            if not parameter_count and language == "mini_c":
                add(cursor.take("KEYWORD", "void"))
            add(cursor.take("DELIMITER", ")"))
            for child in ast_children[parameter_count:]:
                add(build(child))
            if node_type == "FunctionPrototype":
                add(cursor.take("DELIMITER", ";"))
        elif node_type == "Parameter":
            if language == "mini_c":
                add(cursor.take("KEYWORD", attributes.get("declared_type")))
            add(cursor.take("IDENTIFIER", attributes.get("name")))
            if ast_children:
                add(cursor.take("OPERATOR", "="))
                add(build(ast_children[0]))
        elif node_type == "StarArgument":
            add(cursor.take("OPERATOR", attributes.get("operator", "*")))
            add(build(ast_children[0]) if ast_children else None)
        elif node_type == "ReturnStatement":
            add(cursor.take("KEYWORD", "return"))
            if ast_children:
                add(build(ast_children[0]))
            add(cursor.take("DELIMITER", ";"))
        elif node_type == "ReturnStatementPython":
            add(cursor.take("KEYWORD", "return"))
            add(build(ast_children[0]) if ast_children else None)
        elif node_type == "RaiseStatement":
            add(cursor.take("KEYWORD", "raise"))
            add(build(ast_children[0]) if ast_children else None)
        elif node_type == "TryStatement":
            add(cursor.take("KEYWORD", "try")); add(cursor.take("DELIMITER", ":"))
            for child in ast_children:
                add(build(child))
        elif node_type == "ExceptClause":
            add(cursor.take("KEYWORD", "except"))
            if attributes.get("has_exception") and ast_children:
                add(build(ast_children[0])); ast_children = ast_children[1:]
            if attributes.get("has_alias") and ast_children:
                add(cursor.take("KEYWORD", "as")); add(build(ast_children[0])); ast_children = ast_children[1:]
            add(cursor.take("DELIMITER", ":"))
            for child in ast_children:
                add(build(child))
        elif node_type == "FinallyClause":
            add(cursor.take("KEYWORD", "finally")); add(cursor.take("DELIMITER", ":"))
            for child in ast_children:
                add(build(child))
        elif node_type == "WithStatement":
            add(cursor.take("KEYWORD", "with"))
            add(build(ast_children[0]) if ast_children else None)
            if len(ast_children) > 1 and ast_children[1].get("type") == "Identifier":
                add(cursor.take("KEYWORD", "as")); add(build(ast_children[1])); body_start = 2
            else:
                body_start = 1
            add(cursor.take("DELIMITER", ":"))
            for child in ast_children[body_start:]:
                add(build(child))
        elif node_type in {"PassStatement", "BreakStatement", "ContinueStatement"}:
            add(cursor.take("KEYWORD", node_type.replace("Statement", "").lower()))
        elif node_type == "ScopeStatement":
            add(cursor.take("KEYWORD", attributes.get("keyword")))
            for index, child in enumerate(ast_children):
                add(build(child))
                if index < len(ast_children) - 1:
                    add(cursor.take("DELIMITER", ","))
        elif node_type == "ConditionalExpression":
            add(build(ast_children[0]) if ast_children else None)
            add(cursor.take("KEYWORD", "if"))
            add(build(ast_children[1]) if len(ast_children) > 1 else None)
            add(cursor.take("KEYWORD", "else"))
            add(build(ast_children[2]) if len(ast_children) > 2 else None)
        elif node_type == "LambdaExpression":
            add(cursor.take("KEYWORD", "lambda"))
            parameter_count = max(len(ast_children) - 1, 0)
            for index, child in enumerate(ast_children[:parameter_count]):
                add(build(child))
                if index < parameter_count - 1:
                    add(cursor.take("DELIMITER", ","))
            add(cursor.take("DELIMITER", ":"))
            add(build(ast_children[-1]) if ast_children else None)
        elif node_type == "CallStatement":
            add(cursor.take("IDENTIFIER", attributes.get("callee")))
            add(cursor.take("DELIMITER", "("))
            for index, child in enumerate(ast_children):
                add(build(child))
                if index < len(ast_children) - 1:
                    add(cursor.take("DELIMITER", ","))
            add(cursor.take("DELIMITER", ")"))
            add(cursor.take("DELIMITER", ";"))
        elif node_type in {"PrintStatement", "PrintfStatement"}:
            keyword = "print" if node_type == "PrintStatement" else "printf"
            add(cursor.take("KEYWORD", keyword))
            add(cursor.take("DELIMITER", "("))
            for index, child in enumerate(ast_children):
                add(build(child))
                if index < len(ast_children) - 1:
                    add(cursor.take("DELIMITER", ","))
            add(cursor.take("DELIMITER", ")"))
            if node_type == "PrintfStatement":
                add(cursor.take("DELIMITER", ";"))
        elif node_type in {"IfStatement", "WhileStatement"}:
            add(cursor.take("KEYWORD", node_type[:-9].lower()))
            if language == "mini_c":
                add(cursor.take("DELIMITER", "("))
            add(build(ast_children[0]) if ast_children else None)
            if language == "mini_c":
                add(cursor.take("DELIMITER", ")"))
            else:
                add(cursor.take("DELIMITER", ":"))
            for child in ast_children[1:]:
                add(build(child))
        elif node_type == "DoWhileStatement":
            add(cursor.take("KEYWORD", "do"))
            add(build(ast_children[0]) if ast_children else None)
            add(cursor.take("KEYWORD", "while"))
            add(cursor.take("DELIMITER", "("))
            add(build(ast_children[1]) if len(ast_children) > 1 else None)
            add(cursor.take("DELIMITER", ")"))
            add(cursor.take("DELIMITER", ";"))
        elif node_type == "SwitchStatement":
            add(cursor.take("KEYWORD", "switch"))
            add(cursor.take("DELIMITER", "("))
            add(build(ast_children[0]) if ast_children else None)
            add(cursor.take("DELIMITER", ")"))
            add(cursor.take("DELIMITER", "{"))
            for child in ast_children[1:]:
                add(build(child))
            add(cursor.take("DELIMITER", "}"))
        elif node_type == "CaseStatement":
            if attributes.get("default"):
                add(cursor.take("KEYWORD", "default"))
            else:
                add(cursor.take("KEYWORD", "case"))
                add(build(ast_children[0]) if ast_children else None)
            add(cursor.take("DELIMITER", ":"))
            for child in ast_children[1:] if not attributes.get("default") else ast_children:
                add(build(child))
        elif node_type == "ElifStatement":
            add(cursor.take("KEYWORD", "elif"))
            add(build(ast_children[0]) if ast_children else None)
            add(cursor.take("DELIMITER", ":"))
            for child in ast_children[1:]:
                add(build(child))
        elif node_type == "ForStatement" and language == "mini_python":
            add(cursor.take("KEYWORD", "for"))
            add(build(ast_children[0]) if ast_children else None)
            add(cursor.take("KEYWORD", "in"))
            add(build(ast_children[1]) if len(ast_children) > 1 else None)
            add(cursor.take("DELIMITER", ":"))
            for child in ast_children[2:]:
                add(build(child))
        elif node_type == "ForStatement" and language == "mini_c":
            add(cursor.take("KEYWORD", "for"))
            add(cursor.take("DELIMITER", "("))
            add(build(ast_children[0]) if ast_children else None)
            add(build(ast_children[1]) if len(ast_children) > 1 else None)
            add(cursor.take("DELIMITER", ";"))
            add(build(ast_children[2]) if len(ast_children) > 2 else None)
            add(cursor.take("DELIMITER", ")"))
            add(build(ast_children[3]) if len(ast_children) > 3 else None)
        elif node_type == "UpdateExpression":
            add(build(ast_children[0] if ast_children else None))
            add(cursor.take("OPERATOR", attributes.get("operator")))
        elif node_type == "UpdateStatement":
            if attributes.get("prefix"):
                add(cursor.take("OPERATOR", attributes.get("operator")))
            add(build(ast_children[0]) if ast_children else None)
            if not attributes.get("prefix"):
                add(cursor.take("OPERATOR", attributes.get("operator")))
            add(cursor.take("DELIMITER", ";"))
        elif node_type in {"ListLiteral", "TupleLiteral", "SetLiteral", "DictLiteral"}:
            opening, closing = ("[", "]") if node_type == "ListLiteral" else ("(", ")") if node_type == "TupleLiteral" else ("{", "}")
            add(cursor.take("DELIMITER", opening))
            for index, child in enumerate(ast_children):
                add(build(child))
                if index < len(ast_children) - 1:
                    add(cursor.take("DELIMITER", ","))
            add(cursor.take("DELIMITER", closing))
        elif node_type == "InitializerList":
            add(cursor.take("DELIMITER", "{"))
            for index, child in enumerate(ast_children):
                add(expression(child))
                if index < len(ast_children) - 1:
                    add(cursor.take("DELIMITER", ","))
            add(cursor.take("DELIMITER", "}"))
        elif node_type == "KeyValue":
            add(build(ast_children[0]) if ast_children else None)
            add(cursor.take("DELIMITER", ":"))
            add(build(ast_children[1]) if len(ast_children) > 1 else None)
        elif node_type == "IndexExpression":
            add(build(ast_children[0]) if ast_children else None)
            add(cursor.take("DELIMITER", "["))
            add(build(ast_children[1]) if len(ast_children) > 1 else None)
            add(cursor.take("DELIMITER", "]"))
        elif node_type == "SliceExpression":
            add(build(ast_children[0]) if ast_children else None)
            add(cursor.take("DELIMITER", "["))
            if len(ast_children) > 1:
                add(build(ast_children[1]))
            add(cursor.take("DELIMITER", ":"))
            if len(ast_children) > 2:
                add(build(ast_children[2]))
            if len(ast_children) > 3:
                add(cursor.take("DELIMITER", ":")); add(build(ast_children[3]))
            add(cursor.take("DELIMITER", "]"))
        elif node_type == "MemberExpression":
            add(build(ast_children[0]) if ast_children else None)
            add(cursor.take("OPERATOR", "->") if language == "mini_c" else cursor.take("DELIMITER", "."))
            add(build(ast_children[1]) if len(ast_children) > 1 else None)
        elif node_type == "CallExpression":
            add(build(ast_children[0]) if ast_children else None)
            add(cursor.take("DELIMITER", "("))
            for index, child in enumerate(ast_children[1:]):
                add(build(child))
                if index < len(ast_children) - 2:
                    add(cursor.take("DELIMITER", ","))
            add(cursor.take("DELIMITER", ")"))
        elif node_type == "ExpressionStatement":
            add(build(ast_children[0]) if ast_children else None)
        elif node_type == "VariableDeclaration":
            if attributes.get("const"):
                add(cursor.take("KEYWORD", "const"))
            add(cursor.take("KEYWORD", attributes.get("declared_type")))
            for index, child in enumerate(ast_children):
                if index:
                    add(cursor.take("DELIMITER", ","))
                child_attributes = child.get("attributes", {})
                add(cursor.take("IDENTIFIER", child_attributes.get("name")))
                if child.get("children"):
                    add(cursor.take("OPERATOR", "="))
                    add(build(child["children"][0]))
            add(cursor.take("DELIMITER", ";"))
        elif node_type == "ParenthesizedExpression":
            add(cursor.take("DELIMITER", "("))
            add(build(ast_children[0]) if ast_children else None)
            add(cursor.take("DELIMITER", ")"))
        elif node_type == "OutputStatement":
            add(cursor.take("KEYWORD", "std"))
            add(cursor.take("OPERATOR", "::"))
            add(cursor.take("KEYWORD", "cout"))
            for child in ast_children:
                add(cursor.take("OPERATOR", "<<"))
                add(build(child))
            add(cursor.take("DELIMITER", ";"))
        elif node_type == "EndlLiteral":
            add(cursor.take("KEYWORD", "std"))
            add(cursor.take("OPERATOR", "::"))
            add(cursor.take("KEYWORD", "endl"))
        elif node_type == "FunctionDefinitionPython":
            add(cursor.take("KEYWORD", "def"))
            add(cursor.take("IDENTIFIER", attributes.get("name")))
            add(cursor.take("DELIMITER", "("))
            parameter_count = 0
            for child in ast_children:
                if child.get("type") != "Parameter":
                    break
                add(build(child)); parameter_count += 1
                if parameter_count < sum(1 for item in ast_children if item.get("type") == "Parameter"):
                    add(cursor.take("DELIMITER", ","))
            add(cursor.take("DELIMITER", ")"))
            add(cursor.take("DELIMITER", ":"))
            for child in ast_children[parameter_count:]:
                add(build(child))
        elif node_type == "ImportStatement":
            add(cursor.take("KEYWORD", "import"))
            for index, child in enumerate(ast_children):
                for part_index, part in enumerate(child.get("children", [])):
                    add(build(part))
                    if part_index < len(child.get("children", [])) - 1:
                        add(cursor.take("DELIMITER", "."))
                if child.get("attributes", {}).get("alias"):
                    add(cursor.take("KEYWORD", "as")); add(cursor.take("IDENTIFIER", child["attributes"]["alias"]))
                if index < len(ast_children) - 1:
                    add(cursor.take("DELIMITER", ","))
        elif node_type == "FromImportStatement":
            add(cursor.take("KEYWORD", "from"))
            module = ast_children[0] if ast_children else None
            for index, part in enumerate(module.get("children", []) if module else []):
                add(build(part))
                if index < len(module.get("children", [])) - 1:
                    add(cursor.take("DELIMITER", "."))
            add(cursor.take("KEYWORD", "import"))
            if attributes.get("parenthesized"):
                add(cursor.take("DELIMITER", "("))
            for index, child in enumerate(ast_children[1:]):
                add(cursor.take("IDENTIFIER", child.get("attributes", {}).get("name")))
                if child.get("attributes", {}).get("alias"):
                    add(cursor.take("KEYWORD", "as"))
                    add(cursor.take("IDENTIFIER", child["attributes"]["alias"]))
                if index < len(ast_children) - 2:
                    add(cursor.take("DELIMITER", ","))
            if attributes.get("parenthesized"):
                add(cursor.take("DELIMITER", ")"))
        elif node_type in {"ImportName", "ImportedName", "ModuleName"}:
            for child in ast_children:
                add(build(child))
        elif node_type == "ElseStatement":
            add(cursor.take("KEYWORD", "else"))
            if language == "mini_python":
                add(cursor.take("DELIMITER", ":"))
            for child in ast_children:
                add(build(child))
        elif node_type == "BlockStatement":
            add(cursor.take("DELIMITER", "{"))
            for child in ast_children:
                add(build(child))
            add(cursor.take("DELIMITER", "}"))
        elif node_type == "BinaryExpression":
            add(build(ast_children[0] if ast_children else None))
            add(cursor.take("OPERATOR", attributes.get("operator")))
            add(build(ast_children[1] if len(ast_children) > 1 else None))
        elif node_type == "UnaryExpression":
            add(cursor.take("OPERATOR", attributes.get("operator")))
            add(build(ast_children[0] if ast_children else None))
        elif node_type in {"Identifier", "NumberLiteral", "StringLiteral", "CharacterLiteral", "BooleanLiteral", "NoneLiteral"}:
            value = attributes.get("name") if node_type == "Identifier" else attributes.get("value")
            lexeme = "None" if node_type == "NoneLiteral" else str(value)
            if node_type == "BooleanLiteral":
                lexeme = ("True" if value else "False") if language == "mini_python" else ("true" if value else "false")
            token_type = "IDENTIFIER" if node_type == "Identifier" else "NUMBER" if node_type == "NumberLiteral" else "STRING" if node_type == "StringLiteral" else "CHARACTER" if node_type == "CharacterLiteral" else "KEYWORD"
            add(cursor.take(token_type, lexeme))
        elif node_type.startswith("Error"):
            add(cursor.take())
        else:
            for child in ast_children:
                add(build(child))
        return node(node_type, children, **{key: value for key, value in attributes.items() if key != "incomplete"})

    return build(ast)
