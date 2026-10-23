from dataclasses import dataclass
from typing import Any

from .lexer import Token, TYPE_KEYWORDS


@dataclass(frozen=True)
class SyntaxDiagnostic:
    severity: str
    code: str
    message: str
    line: int | None
    column: int | None
    end_line: int | None
    end_column: int | None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def node(node_type: str, children: list[dict[str, Any]] | None = None, **attributes: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"type": node_type}
    if attributes:
        result["attributes"] = attributes
    if children is not None:
        result["children"] = children
    return result


def contains_error(tree: dict[str, Any] | None) -> bool:
    if tree is None or tree["type"].startswith("Error") or tree.get("attributes", {}).get("incomplete") is True:
        return True
    return any(contains_error(child) for child in tree.get("children", []))


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.index = 0
        self.diagnostics: list[SyntaxDiagnostic] = []

    @property
    def current(self) -> Token:
        return self.tokens[min(self.index, len(self.tokens) - 1)]

    def advance(self) -> Token:
        token = self.current
        if self.index < len(self.tokens) - 1:
            self.index += 1
        return token

    def check(self, token_type: str, lexeme: str | None = None) -> bool:
        return self.current.type == token_type and (lexeme is None or self.current.lexeme == lexeme)

    def match(self, token_type: str, lexeme: str | None = None) -> Token | None:
        if self.check(token_type, lexeme):
            return self.advance()
        return None

    def error(self, code: str, message: str, token: Token | None = None) -> None:
        token = token or self.current
        self.diagnostics.append(SyntaxDiagnostic("error", code, message, token.line, token.column, token.end_line, token.end_column))

    def expect(self, token_type: str, lexeme: str | None = None, message: str | None = None) -> Token | None:
        if self.check(token_type, lexeme):
            return self.advance()
        self.error("C_EXPECTED_TOKEN", message or f"Expected {lexeme or token_type}, found {self.current.lexeme or self.current.type}.")
        return None

    def parse(self) -> dict[str, Any] | None:
        if self.check("EOF"):
            self.error("C_EMPTY_SOURCE", "Source code is empty.")
            return None
        children: list[dict[str, Any]] = []
        while not self.check("EOF"):
            before = self.index
            statement = self.declaration_or_statement()
            if statement:
                children.append(statement)
            if self.index == before:
                self.advance()
        return node("Program", children)

    def declaration_or_statement(self) -> dict[str, Any] | None:
        if self.check("KEYWORD") and self.current.lexeme in TYPE_KEYWORDS:
            return self.declaration()
        if self.check("IDENTIFIER") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme == "=":
            return self.assignment()
        if self.check("KEYWORD", "printf"):
            return self.printf_statement()
        if self.check("KEYWORD", "if"):
            return self.if_statement()
        if self.check("KEYWORD", "while"):
            return self.while_statement()
        if self.check("DELIMITER", "{"):
            return self.block()
        if self.check("DELIMITER", "}"):
            self.error("C_UNEXPECTED_CLOSING_BRACE", "Unexpected closing brace.")
            self.advance()
            return None
        self.error("C_UNEXPECTED_TOKEN", "Expected a supported declaration or statement.")
        self.synchronize()
        return None

    def declaration(self) -> dict[str, Any]:
        declared_type = self.advance().lexeme
        identifier = self.expect("IDENTIFIER", message="Expected an identifier after the type.")
        expression = None
        if self.match("OPERATOR", "="):
            expression = self.expression()
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after declaration.")
        attributes: dict[str, Any] = {"declared_type": declared_type, "name": identifier.lexeme if identifier else "<missing>"}
        if expression is not None and contains_error(expression) or identifier is None or semicolon is None:
            attributes["incomplete"] = True
        return node("Declaration", [expression] if expression else [], **attributes)

    def assignment(self) -> dict[str, Any]:
        identifier = self.advance()
        self.expect("OPERATOR", "=")
        expression = self.expression()
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after assignment.")
        attributes: dict[str, Any] = {"target": identifier.lexeme}
        if contains_error(expression) or semicolon is None:
            attributes["incomplete"] = True
        return node("Assignment", [expression], **attributes)

    def printf_statement(self) -> dict[str, Any]:
        self.advance()
        self.expect("DELIMITER", "(", "Expected '(' after printf.")
        children: list[dict[str, Any]] = []
        string_token = self.expect("STRING", message="Expected a format string as the first printf argument.")
        if string_token:
            children.append(node("StringLiteral", value=string_token.lexeme))
        while self.match("DELIMITER", ","):
            children.append(self.expression())
        self.expect("DELIMITER", ")", "Expected ')' after printf arguments.")
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after printf.")
        attributes: dict[str, Any] = {}
        if string_token is None or semicolon is None or any(contains_error(child) for child in children):
            attributes["incomplete"] = True
        return node("PrintfStatement", children, **attributes)

    def block(self) -> dict[str, Any]:
        self.advance()
        children: list[dict[str, Any]] = []
        while not self.check("DELIMITER", "}") and not self.check("EOF"):
            before = self.index
            statement = self.declaration_or_statement()
            if statement:
                children.append(statement)
            if self.index == before:
                self.advance()
        closing = self.expect("DELIMITER", "}", "Expected '}' to close block.")
        return node("BlockStatement", children, **({"incomplete": True} if closing is None else {}))

    def if_statement(self) -> dict[str, Any]:
        self.advance()
        self.expect("DELIMITER", "(", "Expected '(' after if.")
        condition = self.expression()
        self.expect("DELIMITER", ")", "Expected ')' after if condition.")
        body = self.declaration_or_statement()
        children = [condition] + ([body] if body else [])
        if self.match("KEYWORD", "else"):
            else_body = self.declaration_or_statement()
            if else_body:
                children.append(else_body)
        attributes = {"incomplete": True} if contains_error(condition) or body is None else {}
        return node("IfStatement", children, **attributes)

    def while_statement(self) -> dict[str, Any]:
        self.advance()
        self.expect("DELIMITER", "(", "Expected '(' after while.")
        condition = self.expression()
        self.expect("DELIMITER", ")", "Expected ')' after while condition.")
        body = self.declaration_or_statement()
        children = [condition] + ([body] if body else [])
        attributes = {"incomplete": True} if contains_error(condition) or body is None else {}
        return node("WhileStatement", children, **attributes)

    def expression(self) -> dict[str, Any]:
        return self.comparison()

    def comparison(self) -> dict[str, Any]:
        left = self.additive()
        while self.check("OPERATOR") and self.current.lexeme in {"==", "!=", "<", ">", "<=", ">="}:
            operator = self.advance().lexeme
            right = self.additive()
            left = node("BinaryExpression", [left, right], operator=operator)
        return left

    def additive(self) -> dict[str, Any]:
        left = self.multiplicative()
        while self.check("OPERATOR") and self.current.lexeme in {"+", "-"}:
            operator = self.advance().lexeme
            right = self.multiplicative()
            left = node("BinaryExpression", [left, right], operator=operator)
        return left

    def multiplicative(self) -> dict[str, Any]:
        left = self.unary()
        while self.check("OPERATOR") and self.current.lexeme in {"*", "/", "%"}:
            operator = self.advance().lexeme
            right = self.unary()
            left = node("BinaryExpression", [left, right], operator=operator)
        return left

    def unary(self) -> dict[str, Any]:
        if self.check("OPERATOR") and self.current.lexeme in {"+", "-", "!"}:
            operator = self.advance().lexeme
            return node("UnaryExpression", [self.unary()], operator=operator)
        return self.primary()

    def primary(self) -> dict[str, Any]:
        token = self.current
        if token.type == "NUMBER":
            self.advance(); return node("NumberLiteral", value=token.lexeme)
        if token.type == "STRING":
            self.advance(); return node("StringLiteral", value=token.lexeme)
        if token.type == "CHARACTER":
            self.advance(); return node("CharacterLiteral", value=token.lexeme)
        if token.type == "IDENTIFIER":
            self.advance(); return node("Identifier", name=token.lexeme)
        if token.type == "KEYWORD" and token.lexeme in {"true", "false"}:
            self.advance(); return node("BooleanLiteral", value=token.lexeme == "true")
        if self.match("DELIMITER", "("):
            expression = self.expression()
            self.expect("DELIMITER", ")", "Expected ')' to close expression.")
            return expression
        if token.type in {"DELIMITER", "EOF"} and token.lexeme in {")", ";", "}", ""}:
            self.error("C_EXPECTED_EXPRESSION", "Expected an expression.")
            return node("ErrorExpression", error_code="C_EXPECTED_EXPRESSION", message="Expected an expression.")
        self.error("C_INVALID_EXPRESSION", "Expected a literal, identifier, or parenthesized expression.")
        self.advance()
        return node("ErrorExpression", error_code="C_INVALID_EXPRESSION", message="Invalid expression.")

    def synchronize(self) -> None:
        while not self.check("EOF") and not self.check("DELIMITER", ";") and not self.check("DELIMITER", "}"):
            self.advance()
        self.match("DELIMITER", ";")
