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
            add(cursor.take("IDENTIFIER", attributes.get("target")))
            add(cursor.take("OPERATOR", "="))
            add(expression(ast_children[0] if ast_children else None))
            if language == "mini_c":
                add(cursor.take("DELIMITER", ";"))
        elif node_type == "Declaration":
            add(cursor.take("KEYWORD", attributes.get("declared_type")))
            add(cursor.take("IDENTIFIER", attributes.get("name")))
            if ast_children:
                add(cursor.take("OPERATOR", "="))
                add(expression(ast_children[0]))
            add(cursor.take("DELIMITER", ";"))
        elif node_type in {"PrintStatement", "PrintfStatement"}:
            keyword = "print" if node_type == "PrintStatement" else "printf"
            add(cursor.take("KEYWORD", keyword))
            add(cursor.take("DELIMITER", "("))
            for index, child in enumerate(ast_children):
                add(build(child))
                if node_type == "PrintfStatement" and index < len(ast_children) - 1:
                    add(cursor.take("DELIMITER", ","))
            add(cursor.take("DELIMITER", ")"))
            if node_type == "PrintfStatement":
                add(cursor.take("DELIMITER", ";"))
        elif node_type in {"IfStatement", "WhileStatement"}:
            add(cursor.take("KEYWORD", node_type[:-9].lower()))
            if language == "mini_c":
                add(cursor.take("DELIMITER", "("))
            for child in ast_children:
                add(build(child))
                if children and children[-1].get("type") != "Terminal":
                    break
            if language == "mini_c":
                add(cursor.take("DELIMITER", ")"))
            else:
                add(cursor.take("DELIMITER", ":"))
            for child in ast_children[1:]:
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
        elif node_type in {"Identifier", "NumberLiteral", "StringLiteral", "CharacterLiteral", "BooleanLiteral"}:
            value = attributes.get("name") if node_type == "Identifier" else attributes.get("value")
            lexeme = str(value)
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
