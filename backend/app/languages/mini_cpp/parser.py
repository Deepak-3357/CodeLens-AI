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
    PRECEDENCE = {
        "=": 1, "+=": 1, "-=": 1, "*=": 1, "/=": 1, "%=": 1,
        "?": 2, "||": 3, "&&": 4, "==": 5, "!=": 5,
        "<": 6, "<=": 6, ">": 6, ">=": 6, "+": 7, "-": 7,
        "*": 8, "/": 8, "%": 8,
    }
    TYPE_PARTS = TYPE_KEYWORDS | {"std", "::"}

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
        if self.check("DELIMITER", ";"):
            self.advance(); return node("EmptyStatement")
        if self.check("KEYWORD", "using"):
            return self.using_statement()
        if self.check("KEYWORD", "if"): return self.if_statement()
        if self.check("KEYWORD", "while"): return self.while_statement()
        if self.check("KEYWORD", "do"): return self.do_while_statement()
        if self.check("KEYWORD", "for"): return self.for_statement()
        if self.check("KEYWORD", "return"): return self.return_statement()
        if self.check("KEYWORD", "break"): return self.simple_statement("BreakStatement")
        if self.check("KEYWORD", "continue"): return self.simple_statement("ContinueStatement")
        if self.check("DELIMITER", "{"): return self.block()
        if self.is_type_start():
            return self.function_or_declaration()
        if self.is_stream_start():
            return self.stream_statement()
        if self.is_assignment_start():
            return self.assignment_statement()
        if self.check("IDENTIFIER") or self.check("KEYWORD") or self.check("NUMBER") or self.check("STRING") or self.check("CHARACTER"):
            expression = self.expression()
            semicolon = self.expect("DELIMITER", ";", "Expected ';' after expression.")
            return node("ExpressionStatement", [expression], **({"incomplete": True} if semicolon is None or contains_error(expression) else {}))
        if self.check("DELIMITER", "}"):
            self.error("CPP_UNEXPECTED_CLOSING_BRACE", "Unexpected closing brace."); self.advance(); return None
        self.error("CPP_UNSUPPORTED_SYNTAX", "Expected a supported C++ declaration or statement.")
        self.synchronize()
        return None

    def is_type_start(self) -> bool:
        if self.check("KEYWORD", "const"):
            return self.peek().lexeme in TYPE_KEYWORDS or (self.peek().lexeme == "std" and self.peek(2).lexeme == "::" and self.peek(3).lexeme == "string")
        return (self.check("KEYWORD") and self.current.lexeme in TYPE_KEYWORDS) or (self.check("KEYWORD", "std") and self.peek().lexeme == "::" and self.peek(2).lexeme == "string")

    def type_lookahead_end(self) -> int:
        position = self.index
        if self.tokens[position].lexeme == "const": position += 1
        while position < len(self.tokens) and self.tokens[position].lexeme in TYPE_KEYWORDS | {"std", "::"}:
            position += 1
        return position

    def looks_like_function(self) -> bool:
        position = self.type_lookahead_end()
        return position + 1 < len(self.tokens) and self.tokens[position].type in {"IDENTIFIER", "KEYWORD"} and self.tokens[position + 1].lexeme == "("

    def function_or_declaration(self) -> dict[str, Any]:
        if self.looks_like_function():
            return self.function_definition()
        return self.declaration(True)

    def parse_type(self) -> tuple[str, bool]:
        const = bool(self.match("KEYWORD", "const"))
        parts: list[str] = []
        while self.current.lexeme in TYPE_KEYWORDS | {"std", "::"}:
            parts.append(self.advance().lexeme)
            if parts[-1] == "long" and self.current.lexeme == "long":
                continue
        return " ".join(parts).replace("std ::", "std::"), const

    def declaration(self, require_semicolon: bool) -> dict[str, Any]:
        declared_type, const = self.parse_type()
        declarators: list[dict[str, Any]] = []
        first_name = self.expect("IDENTIFIER", message="Expected an identifier after the type.")
        while first_name:
            dimensions: list[dict[str, Any]] = []
            while self.match("DELIMITER", "["):
                dimensions.append(self.expression()) if not self.check("DELIMITER", "]") else None
                self.expect("DELIMITER", "]", "Expected ']' after array dimension.")
            initializer: dict[str, Any] | None = None
            if self.match("OPERATOR", "="):
                if self.match("DELIMITER", "{"):
                    values: list[dict[str, Any]] = []
                    while not self.check("DELIMITER", "}") and not self.check("EOF"):
                        values.append(self.expression())
                        if not self.match("DELIMITER", ","): break
                    self.expect("DELIMITER", "}", "Expected '}' after initializer list.")
                    initializer = node("InitializerList", values)
                else:
                    initializer = self.expression()
            children = ([initializer] if initializer else []) + dimensions
            declarators.append(node("VariableDeclarator", children, name=first_name.lexeme))
            if not self.match("DELIMITER", ","):
                break
            first_name = self.expect("IDENTIFIER", message="Expected an identifier after ','.")
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after declaration.") if require_semicolon else True
        incomplete = first_name is None or semicolon is None or any(contains_error(item) for item in declarators)
        attributes: dict[str, Any] = {"declared_type": declared_type or "<missing>", "const": const}
        if incomplete: attributes["incomplete"] = True
        return node("VariableDeclaration", declarators, **attributes)

    def function_definition(self) -> dict[str, Any]:
        return_type, _ = self.parse_type()
        name = self.expect("IDENTIFIER", message="Expected a function name.")
        self.expect("DELIMITER", "(", "Expected '(' after function name.")
        parameters: list[dict[str, Any]] = []
        if not self.check("DELIMITER", ")"):
            while True:
                parameter_type, parameter_const = self.parse_type()
                parameter_name = None if self.check("DELIMITER", ",") or self.check("DELIMITER", ")") else self.expect("IDENTIFIER", message="Expected a parameter name.")
                parameters.append(node("Parameter", [], declared_type=parameter_type, const=parameter_const, name=parameter_name.lexeme if parameter_name else "<missing>"))
                if not self.match("DELIMITER", ","): break
        self.expect("DELIMITER", ")", "Expected ')' after function parameters.")
        body = self.block() if self.check("DELIMITER", "{") else None
        if body is None:
            self.expect("DELIMITER", ";", "Expected '{' or ';' after function declaration.")
        attributes: dict[str, Any] = {"return_type": return_type, "name": name.lexeme if name else "<missing>"}
        if body is None: attributes["prototype"] = True
        if name is None or contains_error(body): attributes["incomplete"] = True
        return node("FunctionDefinition", parameters + ([body] if body else []), **attributes)

    def using_statement(self) -> dict[str, Any]:
        self.advance()
        if self.match("KEYWORD", "namespace"):
            namespace = self.advance() if self.current.type in {"IDENTIFIER", "KEYWORD"} else None
            if namespace is None:
                self.error("CPP_EXPECTED_TOKEN", "Expected a namespace name after 'using namespace'.")
            semicolon = self.expect("DELIMITER", ";", "Expected ';' after using namespace declaration.")
            valid = namespace is not None and namespace.lexeme == "std" and semicolon is not None
            if not valid: self.error("CPP_UNSUPPORTED_NAMESPACE", "Only 'using namespace std;' is supported.", namespace or self.current)
            return node("UsingNamespace", [], name=namespace.lexeme if namespace else "<missing>", **({"incomplete": True} if not valid else {}))
        if self.match("KEYWORD", "std") and self.match("OPERATOR", "::"):
            name = self.expect("KEYWORD", message="Expected a supported std name.")
            semicolon = self.expect("DELIMITER", ";", "Expected ';' after using declaration.")
            valid = name is not None and name.lexeme in {"cout", "cin", "endl", "string"} and semicolon is not None
            if not valid: self.error("CPP_UNSUPPORTED_NAMESPACE", "Only selected std names are supported.", name or self.current)
            return node("UsingDeclaration", [], name=name.lexeme if name else "<missing>", **({"incomplete": True} if not valid else {}))
        self.error("CPP_UNSUPPORTED_NAMESPACE", "Only 'using namespace std;' and selected std names are supported.")
        self.synchronize()
        return node("UsingDeclaration", [], incomplete=True)

    def assignment_target(self) -> dict[str, Any]:
        target = self.primary()
        return target

    def is_assignment_start(self) -> bool:
        return self.check("IDENTIFIER") and (self.peek().lexeme in {"=", "+=", "-=", "*=", "/=", "%=", "++", "--"} or self.peek().lexeme == "[")

    def assignment_statement(self) -> dict[str, Any]:
        target = self.assignment_target()
        if self.current.lexeme in {"++", "--"}:
            operator = self.advance(); semicolon = self.expect("DELIMITER", ";", "Expected ';' after update expression.")
            return node("UpdateStatement", [target], operator=operator.lexeme, **({"incomplete": True} if semicolon is None else {}))
        operator = self.advance()
        expression = self.expression()
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after assignment.")
        return node("Assignment", [target, expression], operator=operator.lexeme, **({"incomplete": True} if semicolon is None or contains_error(expression) else {}))

    def stream_prefix(self) -> tuple[str, str] | None:
        start = self.index
        qualified = self.match("KEYWORD", "std") is not None
        if qualified and not self.match("OPERATOR", "::"):
            self.index = start; return None
        name = self.current.lexeme
        if name not in {"cout", "cin"}:
            self.index = start; return None
        self.advance()
        return ("output" if name == "cout" else "input", f"std::{name}" if qualified else name)

    def is_stream_start(self) -> bool:
        start = self.index
        result = self.stream_prefix() is not None
        self.index = start
        return result

    def stream_statement(self) -> dict[str, Any]:
        kind, name = self.stream_prefix() or ("output", "cout")
        operator = "<<" if kind == "output" else ">>"
        values: list[dict[str, Any]] = []
        while self.match("OPERATOR", operator):
            if kind == "output" and self.current.lexeme in {"endl"}:
                values.append(node("EndlLiteral", value=self.advance().lexeme))
            elif kind == "output" and self.current.lexeme == "std" and self.peek().lexeme == "::" and self.peek(2).lexeme == "endl":
                self.advance(); self.advance(); self.advance(); values.append(node("EndlLiteral", value="std::endl"))
            else:
                values.append(self.expression())
        semicolon = self.expect("DELIMITER", ";", f"Expected ';' after {name} stream statement.")
        return node("OutputStatement" if kind == "output" else "InputStatement", values, stream=name, **({"incomplete": True} if semicolon is None or any(contains_error(value) for value in values) else {}))

    def if_statement(self) -> dict[str, Any]:
        self.advance(); self.expect("DELIMITER", "(", "Expected '(' after if."); condition = self.expression(); self.expect("DELIMITER", ")", "Expected ')' after if condition.")
        body = self.statement_body(); else_body = None
        if self.match("KEYWORD", "else"): else_body = self.if_statement() if self.check("KEYWORD", "if") else self.statement_body()
        children = [condition, body] + ([else_body] if else_body else [])
        return node("IfStatement", children, **({"incomplete": True} if any(contains_error(item) for item in children) else {}))

    def while_statement(self) -> dict[str, Any]:
        self.advance(); self.expect("DELIMITER", "(", "Expected '(' after while."); condition = self.expression(); self.expect("DELIMITER", ")", "Expected ')' after while condition."); body = self.statement_body()
        return node("WhileStatement", [condition, body], **({"incomplete": True} if contains_error(condition) or contains_error(body) else {}))

    def do_while_statement(self) -> dict[str, Any]:
        self.advance(); body = self.statement_body(); self.expect("KEYWORD", "while", "Expected 'while' after do body."); self.expect("DELIMITER", "(", "Expected '(' after while."); condition = self.expression(); self.expect("DELIMITER", ")", "Expected ')' after do-while condition."); semicolon = self.expect("DELIMITER", ";", "Expected ';' after do-while statement.")
        return node("DoWhileStatement", [body, condition], **({"incomplete": True} if semicolon is None or contains_error(body) or contains_error(condition) else {}))

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
            operator = self.advance()
            next_minimum = self.PRECEDENCE[operator.lexeme] if operator.lexeme in {"=", "+=", "-=", "*=", "/=", "%="} else self.PRECEDENCE[operator.lexeme] + 1
            right = self.expression(next_minimum)
            left = node("ConditionalExpression" if operator.lexeme == "?" else "BinaryExpression", [left, right], operator=operator.lexeme, **({"incomplete": True} if contains_error(right) else {}))
        return left

    def unary(self) -> dict[str, Any]:
        if self.current.lexeme in {"+", "-", "!", "++", "--", "&"}:
            operator = self.advance(); child = self.unary(); return node("UnaryExpression", [child], operator=operator.lexeme, **({"incomplete": True} if contains_error(child) else {}))
        return self.primary()

    def primary(self) -> dict[str, Any]:
        token = self.current
        if self.match("DELIMITER", "("):
            value = self.expression(); closing = self.expect("DELIMITER", ")", "Expected ')' after expression.")
            return node("ParenthesizedExpression", [value], **({"incomplete": True} if closing is None or contains_error(value) else {}))
        if token.type in {"NUMBER", "STRING", "CHARACTER"}:
            self.advance(); return node({"NUMBER": "NumberLiteral", "STRING": "StringLiteral", "CHARACTER": "CharacterLiteral"}[token.type], value=token.lexeme)
        if token.lexeme in {"true", "false", "nullptr"}:
            self.advance(); return node("BooleanLiteral" if token.lexeme != "nullptr" else "NullptrLiteral", value=token.lexeme == "true" if token.lexeme != "nullptr" else None)
        if token.type in {"IDENTIFIER", "KEYWORD"}:
            self.advance(); name = token.lexeme
            if self.match("OPERATOR", "::"):
                member = self.expect("IDENTIFIER", message="Expected a name after '::'.") or self.expect("KEYWORD", message="Expected a name after '::'.")
                name = f"{name}::{member.lexeme if member else '<missing>'}"
            result = node("Identifier", name=name)
            if self.match("DELIMITER", "("):
                args: list[dict[str, Any]] = []
                if not self.check("DELIMITER", ")"):
                    while True:
                        args.append(self.expression())
                        if not self.match("DELIMITER", ","): break
                closing = self.expect("DELIMITER", ")", "Expected ')' after arguments.")
                result = node("CallExpression", args, callee=name, **({"incomplete": True} if closing is None else {}))
            while self.match("DELIMITER", "["):
                index = self.expression(); closing = self.expect("DELIMITER", "]", "Expected ']' after array index.")
                result = node("IndexExpression", [result, index], **({"incomplete": True} if closing is None else {}))
            if self.current.lexeme in {"++", "--"}:
                result = node("UpdateExpression", [result], operator=self.advance().lexeme)
            return result
        self.error("CPP_EXPECTED_EXPRESSION", "Expected an expression.")
        if not self.check("EOF"): self.advance()
        return node("ErrorExpression", [], code="CPP_EXPECTED_EXPRESSION", incomplete=True)

    def synchronize(self) -> None:
        while not self.check("EOF") and not self.check("DELIMITER", ";") and not self.check("DELIMITER", "}"):
            self.advance()
        self.match("DELIMITER", ";")
