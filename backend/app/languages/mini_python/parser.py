from dataclasses import dataclass
from typing import Any

from .lexer import Token


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
        expected = lexeme or token_type
        self.error("PY_EXPECTED_TOKEN", message or f"Expected {expected}, found {self.current.lexeme or self.current.type}.")
        return None

    def parse(self) -> dict[str, Any] | None:
        if self.check("EOF"):
            self.error("PY_EMPTY_SOURCE", "Source code is empty.")
            return None
        children: list[dict[str, Any]] = []
        while not self.check("EOF"):
            if self.match("NEWLINE") or self.match("DEDENT"):
                continue
            before = self.index
            statement = self.statement()
            if statement:
                children.append(statement)
            if self.index == before:
                self.advance()
            if self.check("NEWLINE"):
                self.advance()
        return node("Program", children)

    def statement(self) -> dict[str, Any] | None:
        if self.check("IDENTIFIER") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme == "=":
            return self.assignment()
        if self.check("KEYWORD", "print"):
            return self.print_statement()
        if self.check("KEYWORD", "if"):
            return self.block_statement("IfStatement")
        if self.check("KEYWORD", "while"):
            return self.block_statement("WhileStatement")
        if self.check("KEYWORD", "else"):
            self.error("PY_UNEXPECTED_ELSE", "An else block must follow an if statement.")
        else:
            self.error("PY_UNEXPECTED_TOKEN", "Expected a supported statement.")
        self.synchronize()
        return None

    def assignment(self) -> dict[str, Any] | None:
        identifier = self.advance()
        self.expect("OPERATOR", "=")
        expression = self.expression()
        attributes: dict[str, Any] = {"target": identifier.lexeme}
        if contains_error(expression):
            attributes["incomplete"] = True
        return node("Assignment", [expression], **attributes)

    def print_statement(self) -> dict[str, Any] | None:
        self.advance()
        self.expect("DELIMITER", "(", "Expected '(' after print.")
        expression = self.expression()
        self.expect("DELIMITER", ")", "Expected ')' after print expression.")
        attributes: dict[str, Any] = {}
        if contains_error(expression):
            attributes["incomplete"] = True
        return node("PrintStatement", [expression], **attributes)

    def block_statement(self, statement_type: str) -> dict[str, Any] | None:
        keyword = self.advance()
        condition = None if statement_type == "ElseStatement" else self.expression()
        self.expect("DELIMITER", ":", "Expected ':' after block condition.")
        self.expect("NEWLINE", message="Expected a newline after ':'.")
        self.expect("INDENT", message="Expected an indented block.")
        body: list[dict[str, Any]] = []
        while not self.check("DEDENT") and not self.check("EOF"):
            if self.match("NEWLINE"):
                continue
            before = self.index
            child = self.statement()
            if child:
                body.append(child)
            if self.index == before:
                self.advance()
            self.match("NEWLINE")
        self.expect("DEDENT", message="Expected the block to end.")
        attributes: dict[str, Any] = {"keyword": keyword.lexeme}
        children = ([condition] if condition else []) + body
        result = node(statement_type, children, **attributes)
        if statement_type == "IfStatement" and self.check("KEYWORD", "else"):
            else_node = self.block_statement("ElseStatement")
            if else_node:
                result["children"].append(else_node)
        return result

    def expression(self) -> dict[str, Any] | None:
        return self.comparison()

    def comparison(self) -> dict[str, Any] | None:
        left = self.additive()
        while self.check("OPERATOR") and self.current.lexeme in {"==", "!=", "<", ">", "<=", ">="}:
            operator = self.advance().lexeme
            right = self.additive()
            if right is None:
                break
            left = node("BinaryExpression", [left, right] if left else [right], operator=operator)
        return left

    def additive(self) -> dict[str, Any] | None:
        left = self.multiplicative()
        while self.check("OPERATOR") and self.current.lexeme in {"+", "-"}:
            operator = self.advance().lexeme
            right = self.multiplicative()
            if right is None:
                break
            left = node("BinaryExpression", [left, right] if left else [right], operator=operator)
        return left

    def multiplicative(self) -> dict[str, Any] | None:
        left = self.unary()
        while self.check("OPERATOR") and self.current.lexeme in {"*", "/", "%"}:
            operator = self.advance().lexeme
            right = self.unary()
            if right is None:
                break
            left = node("BinaryExpression", [left, right] if left else [right], operator=operator)
        return left

    def unary(self) -> dict[str, Any] | None:
        if self.check("OPERATOR") and self.current.lexeme in {"+", "-"}:
            operator = self.advance().lexeme
            operand = self.unary()
            return node("UnaryExpression", [operand] if operand else [], operator=operator)
        return self.primary()

    def primary(self) -> dict[str, Any] | None:
        token = self.current
        if token.type == "NUMBER":
            self.advance()
            return node("NumberLiteral", value=token.lexeme)
        if token.type == "STRING":
            self.advance()
            return node("StringLiteral", value=token.lexeme)
        if token.type == "IDENTIFIER":
            self.advance()
            return node("Identifier", name=token.lexeme)
        if token.type == "KEYWORD" and token.lexeme in {"True", "False"}:
            self.advance()
            return node("BooleanLiteral", value=token.lexeme == "True")
        if self.match("DELIMITER", "("):
            expression = self.expression()
            self.expect("DELIMITER", ")", "Expected ')' to close expression.")
            return expression
        if token.type in {"NEWLINE", "DEDENT", "EOF"}:
            self.error("PY_EXPECTED_EXPRESSION", "Expected an expression.")
            return node("ErrorExpression", error_code="PY_EXPECTED_EXPRESSION", message="Expected an expression.")
        if token.type == "DELIMITER" and token.lexeme in {")", ":"}:
            self.error("PY_INVALID_EXPRESSION", "Expected an expression before this delimiter.")
            return node("ErrorExpression", error_code="PY_INVALID_EXPRESSION", message="Expected an expression before this delimiter.")
        else:
            self.error("PY_INVALID_EXPRESSION", "Expected a number, string, boolean, identifier, or parenthesized expression.")
            self.advance()
            return node("ErrorExpression", error_code="PY_INVALID_EXPRESSION", message="Invalid expression.")

    def synchronize(self) -> None:
        while not self.check("EOF") and not self.check("NEWLINE") and not self.check("DEDENT"):
            self.advance()
        self.match("NEWLINE")


def contains_error(tree: dict[str, Any] | None) -> bool:
    if tree is None:
        return True
    if tree["type"].startswith("Error") or tree.get("attributes", {}).get("incomplete") is True:
        return True
    return any(contains_error(child) for child in tree.get("children", []))
