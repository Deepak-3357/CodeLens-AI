from dataclasses import dataclass
from typing import Any

from .lexer import TYPE_KEYWORDS, Token


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
    PRECEDENCE = {"||": 1, "&&": 2, "==": 3, "!=": 3, "<": 4, "<=": 4, ">": 4, ">=": 4, "+": 5, "-": 5, "*": 6, "/": 6, "%": 6}

    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.index = 0
        self.diagnostics: list[SyntaxDiagnostic] = []

    @property
    def current(self) -> Token:
        return self.tokens[min(self.index, len(self.tokens) - 1)]

    def peek(self, offset: int = 1) -> Token:
        return self.tokens[min(self.index + offset, len(self.tokens) - 1)]

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
        self.error("CPP_EXPECTED_TOKEN", message or f"Expected {lexeme or token_type}, found {self.current.lexeme or self.current.type}.")
        return None

    def parse(self) -> dict[str, Any] | None:
        if self.check("EOF"):
            self.error("CPP_EMPTY_SOURCE", "Source code is empty.")
            return None
        children: list[dict[str, Any]] = []
        while not self.check("EOF"):
            before = self.index
            if self.check("PREPROCESSOR"):
                children.append(node("IncludeDirective", [], value=self.advance().lexeme)); continue
            item = self.declaration_or_statement()
            if item:
                children.append(item)
            if self.index == before:
                self.advance()
        return node("Program", children)

    def declaration_or_statement(self) -> dict[str, Any] | None:
        if self.check("KEYWORD", "if"): return self.if_statement()
        if self.check("KEYWORD", "while"): return self.while_statement()
        if self.check("KEYWORD", "for"): return self.for_statement()
        if self.check("KEYWORD", "return"): return self.return_statement()
        if self.check("KEYWORD", "break"): return self.simple_statement("BreakStatement")
        if self.check("KEYWORD", "continue"): return self.simple_statement("ContinueStatement")
        if self.check("DELIMITER", "{"): return self.block()
        if self.is_type_start():
            if self.peek().type in {"IDENTIFIER", "KEYWORD"} and self.peek(2).lexeme == "(":
                return self.function_definition()
            return self.declaration(True)
        if self.is_assignment_start():
            return self.assignment_statement()
        if self.is_output_start():
            return self.output_statement()
        if self.check("IDENTIFIER") or self.check("NUMBER") or self.check("STRING") or self.check("CHARACTER"):
            expression = self.expression()
            semicolon = self.expect("DELIMITER", ";", "Expected ';' after expression.")
            return node("ExpressionStatement", [expression], **({"incomplete": True} if semicolon is None or contains_error(expression) else {}))
        if self.check("DELIMITER", "}"):
            self.error("CPP_UNEXPECTED_CLOSING_BRACE", "Unexpected closing brace."); self.advance(); return None
        self.error("CPP_UNEXPECTED_TOKEN", "Expected a supported C++ declaration or statement.")
        self.synchronize()
        return None

    def is_type_start(self) -> bool:
        return (self.check("KEYWORD") and self.current.lexeme in TYPE_KEYWORDS) or (self.check("KEYWORD", "const") and self.peek().lexeme in TYPE_KEYWORDS - {"void"})

    def is_assignment_start(self) -> bool:
        return self.check("IDENTIFIER") and (self.peek().lexeme in {"=", "+=", "-=", "*=", "/="} or self.peek().lexeme in {"++", "--"})

    def is_output_start(self) -> bool:
        return self.current.lexeme == "std" and self.peek().lexeme == "::" and self.peek(2).lexeme == "cout"

    def declaration(self, require_semicolon: bool) -> dict[str, Any]:
        const = bool(self.match("KEYWORD", "const"))
        declared_type = self.expect("KEYWORD", message="Expected a C++ type.")
        declarators: list[dict[str, Any]] = []
        first_name = self.expect("IDENTIFIER", message="Expected an identifier after the type.")
        expression = None
        if self.match("OPERATOR", "="):
            expression = self.expression()
        if first_name:
            declarators.append(node("VariableDeclarator", [expression] if expression else [], name=first_name.lexeme))
        while self.match("DELIMITER", ","):
            name = self.expect("IDENTIFIER", message="Expected an identifier after ','.")
            value = None
            if self.match("OPERATOR", "="): value = self.expression()
            declarators.append(node("VariableDeclarator", [value] if value else [], name=name.lexeme if name else "<missing>"))
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after declaration.") if require_semicolon else True
        attributes = {"declared_type": declared_type.lexeme if declared_type else "<missing>", "const": const}
        incomplete = first_name is None or semicolon is None or any(contains_error(item) for item in declarators)
        if incomplete: attributes["incomplete"] = True
        return node("VariableDeclaration", declarators, **attributes)

    def function_definition(self) -> dict[str, Any]:
        return_type = self.advance()
        name = self.expect("IDENTIFIER", message="Expected a function name.")
        self.expect("DELIMITER", "(", "Expected '(' after function name.")
        parameters: list[dict[str, Any]] = []
        if not self.check("DELIMITER", ")"):
            while True:
                parameter_type = self.expect("KEYWORD", message="Expected a parameter type.")
                parameter_name = self.expect("IDENTIFIER", message="Expected a parameter name.")
                parameters.append(node("Parameter", [], declared_type=parameter_type.lexeme if parameter_type else "<missing>", name=parameter_name.lexeme if parameter_name else "<missing>"))
                if not self.match("DELIMITER", ","): break
        self.expect("DELIMITER", ")", "Expected ')' after function parameters.")
        body = self.block() if self.check("DELIMITER", "{") else None
        attributes = {"return_type": return_type.lexeme, "name": name.lexeme if name else "<missing>"}
        if body is None: attributes["incomplete"] = True
        return node("FunctionDefinition", parameters + ([body] if body else []), **attributes)

    def assignment_statement(self) -> dict[str, Any]:
        target = self.advance()
        operator = self.advance()
        if operator.lexeme in {"++", "--"}:
            semicolon = self.expect("DELIMITER", ";", "Expected ';' after update expression.")
            return node("UpdateStatement", [node("Identifier", name=target.lexeme)], operator=operator.lexeme, **({"incomplete": True} if semicolon is None else {}))
        expression = self.expression()
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after assignment.")
        return node("Assignment", [expression], target=target.lexeme, operator=operator.lexeme, **({"incomplete": True} if semicolon is None or contains_error(expression) else {}))

    def output_statement(self) -> dict[str, Any]:
        self.advance(); self.expect("OPERATOR", "::"); self.expect("KEYWORD", "cout")
        values: list[dict[str, Any]] = []
        while self.match("OPERATOR", "<<"):
            if self.current.lexeme == "std" and self.peek().lexeme == "::" and self.peek(2).lexeme == "endl":
                self.advance(); self.advance(); self.advance(); values.append(node("EndlLiteral", value="std::endl"))
            else:
                values.append(self.expression())
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after std::cout.")
        return node("OutputStatement", values, **({"incomplete": True} if semicolon is None or any(contains_error(item) for item in values) else {}))

    def if_statement(self) -> dict[str, Any]:
        self.advance(); self.expect("DELIMITER", "(", "Expected '(' after if."); condition = self.expression(); self.expect("DELIMITER", ")", "Expected ')' after if condition.")
        body = self.statement_body(); else_body = None
        if self.match("KEYWORD", "else"): else_body = self.statement_body()
        children = [condition, body] + ([else_body] if else_body else [])
        return node("IfStatement", children, **({"incomplete": True} if any(contains_error(item) for item in children) else {}))

    def while_statement(self) -> dict[str, Any]:
        self.advance(); self.expect("DELIMITER", "(", "Expected '(' after while."); condition = self.expression(); self.expect("DELIMITER", ")", "Expected ')' after while condition."); body = self.statement_body()
        return node("WhileStatement", [condition, body], **({"incomplete": True} if contains_error(condition) or contains_error(body) else {}))

    def for_statement(self) -> dict[str, Any]:
        self.advance(); self.expect("DELIMITER", "(", "Expected '(' after for.")
        initializer = None
        if not self.check("DELIMITER", ";"):
            initializer = self.declaration(False) if self.is_type_start() else self.expression()
        self.expect("DELIMITER", ";", "Expected ';' after for initializer.")
        condition = None if self.check("DELIMITER", ";") else self.expression()
        self.expect("DELIMITER", ";", "Expected ';' after for condition.")
        update = None if self.check("DELIMITER", ")") else self.expression()
        self.expect("DELIMITER", ")", "Expected ')' after for clauses.")
        body = self.statement_body()
        children = [item for item in (initializer, condition, update, body) if item]
        return node("ForStatement", children, **({"incomplete": True} if any(contains_error(item) for item in children) else {}))

    def return_statement(self) -> dict[str, Any]:
        self.advance(); expression = None if self.check("DELIMITER", ";") else self.expression(); semicolon = self.expect("DELIMITER", ";", "Expected ';' after return statement.")
        return node("ReturnStatement", [expression] if expression else [], **({"incomplete": True} if semicolon is None or (expression and contains_error(expression)) else {}))

    def simple_statement(self, statement_type: str) -> dict[str, Any]:
        self.advance(); semicolon = self.expect("DELIMITER", ";", "Expected ';' after control statement.")
        return node(statement_type, [], **({"incomplete": True} if semicolon is None else {}))

    def statement_body(self) -> dict[str, Any]:
        return self.block() if self.check("DELIMITER", "{") else self.declaration_or_statement() or node("ErrorStatement", incomplete=True)

    def block(self) -> dict[str, Any]:
        self.expect("DELIMITER", "{"); children: list[dict[str, Any]] = []
        while not self.check("DELIMITER", "}") and not self.check("EOF"):
            before = self.index; item = self.declaration_or_statement()
            if item: children.append(item)
            if before == self.index: self.advance()
        closing = self.expect("DELIMITER", "}", "Expected '}' to close block.")
        return node("BlockStatement", children, **({"incomplete": True} if closing is None or any(contains_error(item) for item in children) else {}))

    def expression(self, minimum_precedence: int = 0) -> dict[str, Any]:
        left = self.unary()
        while self.current.lexeme in self.PRECEDENCE and self.PRECEDENCE[self.current.lexeme] >= minimum_precedence:
            operator = self.advance(); right = self.expression(self.PRECEDENCE[operator.lexeme] + 1); left = node("BinaryExpression", [left, right], operator=operator.lexeme, **({"incomplete": True} if contains_error(right) else {}))
        return left

    def unary(self) -> dict[str, Any]:
        if self.current.lexeme in {"+", "-", "!"}:
            operator = self.advance(); child = self.unary(); return node("UnaryExpression", [child], operator=operator.lexeme, **({"incomplete": True} if contains_error(child) else {}))
        return self.primary()

    def primary(self) -> dict[str, Any]:
        token = self.current
        if self.match("DELIMITER", "("):
            value = self.expression(); closing = self.expect("DELIMITER", ")", "Expected ')' after expression.")
            return node("ParenthesizedExpression", [value], **({"incomplete": True} if closing is None or contains_error(value) else {}))
        if token.type == "NUMBER":
            self.advance(); return node("NumberLiteral", value=token.lexeme)
        if token.type == "STRING":
            self.advance(); return node("StringLiteral", value=token.lexeme)
        if token.type == "CHARACTER":
            self.advance(); return node("CharacterLiteral", value=token.lexeme)
        if token.type == "KEYWORD" and token.lexeme in {"true", "false"}:
            self.advance(); return node("BooleanLiteral", value=token.lexeme == "true")
        if token.type in {"IDENTIFIER", "KEYWORD"}:
            self.advance(); result = node("Identifier", name=token.lexeme)
            if self.match("DELIMITER", "("):
                args: list[dict[str, Any]] = []
                if not self.check("DELIMITER", ")"):
                    while True:
                        args.append(self.expression())
                        if not self.match("DELIMITER", ","): break
                closing = self.expect("DELIMITER", ")", "Expected ')' after arguments.")
                result = node("CallExpression", args, callee=token.lexeme, **({"incomplete": True} if closing is None else {}))
            if self.match("OPERATOR", "++") or self.match("OPERATOR", "--"):
                result = node("UpdateExpression", [result], operator=self.tokens[self.index - 1].lexeme)
            return result
        self.error("CPP_EXPECTED_EXPRESSION", "Expected an expression.")
        if not self.check("EOF"): self.advance()
        return node("ErrorExpression", [], code="CPP_EXPECTED_EXPRESSION", incomplete=True)

    def synchronize(self) -> None:
        while not self.check("EOF") and not self.check("DELIMITER", ";") and not self.check("DELIMITER", "}"):
            self.advance()
        self.match("DELIMITER", ";")
