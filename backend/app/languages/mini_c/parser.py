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
        self.known_types = set(TYPE_KEYWORDS)

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
            if self.check("PREPROCESSOR"):
                children.append(self.include_directive())
                continue
            before = self.index
            statement = self.declaration_or_statement()
            if statement:
                children.append(statement)
            if self.index == before:
                self.advance()
        return node("Program", children)

    def declaration_or_statement(self) -> dict[str, Any] | None:
        if self.check("KEYWORD", "typedef"):
            return self.typedef_declaration()
        if self.check("KEYWORD", "struct"):
            if self.index + 2 < len(self.tokens) and self.tokens[self.index + 1].type == "IDENTIFIER" and self.tokens[self.index + 2].lexeme != "{":
                return self.named_type_declaration("struct")
            return self.struct_declaration()
        if self.check("KEYWORD", "enum"):
            if self.index + 2 < len(self.tokens) and self.tokens[self.index + 1].type == "IDENTIFIER" and self.tokens[self.index + 2].lexeme != "{":
                return self.named_type_declaration("enum")
            return self.enum_declaration()
        if self.check("IDENTIFIER") and self.current.lexeme in self.known_types and self.index + 1 < len(self.tokens):
            return self.declaration()
        if self.check("IDENTIFIER") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].type == "IDENTIFIER":
            return self.declaration()
        if self.check("KEYWORD", "const"):
            return self.declaration()
        if self.check("KEYWORD") and self.current.lexeme in TYPE_KEYWORDS:
            if self.index + 2 < len(self.tokens) and self.tokens[self.index + 1].type == "IDENTIFIER" and self.tokens[self.index + 2].lexeme == "(":
                return self.function_definition()
            return self.declaration()
        if self.check("IDENTIFIER") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme in {"=", "+=", "-=", "*=", "/=", "%="}:
            return self.assignment()
        if self.check("IDENTIFIER") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme in {"++", "--"}:
            return self.update_statement()
        if self.check("OPERATOR") and self.current.lexeme in {"++", "--"}:
            return self.update_statement()
        if self.check("IDENTIFIER") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme == "[":
            return self.indexed_assignment()
        if self.check("KEYWORD", "printf"):
            return self.printf_statement()
        if self.check("KEYWORD", "if"):
            return self.if_statement()
        if self.check("KEYWORD", "while"):
            return self.while_statement()
        if self.check("KEYWORD", "for"):
            return self.for_statement()
        if self.check("KEYWORD", "do"):
            return self.do_while_statement()
        if self.check("KEYWORD", "switch"):
            return self.switch_statement()
        if self.check("KEYWORD", "return"):
            return self.return_statement()
        if self.check("KEYWORD", "break"):
            return self.simple_control_statement("BreakStatement")
        if self.check("KEYWORD", "continue"):
            return self.simple_control_statement("ContinueStatement")
        if self.check("IDENTIFIER") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme == "(":
            return self.call_statement()
        if self.check("DELIMITER", "{"):
            return self.block()
        if self.check("DELIMITER", "}"):
            self.error("C_UNEXPECTED_CLOSING_BRACE", "Unexpected closing brace.")
            self.advance()
            return None
        self.error("C_UNEXPECTED_TOKEN", "Expected a supported declaration or statement.")
        self.synchronize()
        return None

    def include_directive(self) -> dict[str, Any]:
        token = self.advance()
        return node("IncludeDirective", [], value=token.lexeme)

    def typedef_declaration(self) -> dict[str, Any]:
        self.advance()
        declared_type = self.expect("KEYWORD", message="Expected a type after typedef.")
        type_name = None
        if declared_type and declared_type.lexeme in {"struct", "enum"}:
            type_name = self.expect("IDENTIFIER", message=f"Expected a {declared_type.lexeme} name after typedef.")
        alias = self.expect("IDENTIFIER", message="Expected a typedef name.")
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after typedef.")
        attributes = {"declared_type": declared_type.lexeme if declared_type else "<missing>", "name": alias.lexeme if alias else "<missing>"}
        if type_name:
            attributes["type_name"] = type_name.lexeme
        if semicolon is None:
            attributes["incomplete"] = True
        if alias:
            self.known_types.add(alias.lexeme)
        return node("TypedefDeclaration", [], **attributes)

    def struct_declaration(self) -> dict[str, Any]:
        self.advance()
        name = self.expect("IDENTIFIER", message="Expected a struct name.")
        fields: list[dict[str, Any]] = []
        if self.match("DELIMITER", "{"):
            while not self.check("DELIMITER", "}") and not self.check("EOF"):
                fields.append(self.declaration())
            closing = self.expect("DELIMITER", "}", "Expected '}' after struct fields.")
        else:
            closing = True
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after struct declaration.")
        attributes = {"name": name.lexeme if name else "<missing>"}
        if closing is None or semicolon is None:
            attributes["incomplete"] = True
        return node("StructDeclaration", fields, **attributes)

    def enum_declaration(self) -> dict[str, Any]:
        self.advance()
        name = self.expect("IDENTIFIER", message="Expected an enum name.")
        members: list[dict[str, Any]] = []
        self.expect("DELIMITER", "{", "Expected '{' after enum name.")
        while not self.check("DELIMITER", "}") and not self.check("EOF"):
            member = self.expect("IDENTIFIER", message="Expected an enum member.")
            if member:
                value = None
                if self.match("OPERATOR", "="):
                    value = self.expression()
                members.append(node("EnumMember", [value] if value else [], name=member.lexeme))
            if not self.match("DELIMITER", ","):
                break
        closing = self.expect("DELIMITER", "}", "Expected '}' after enum members.")
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after enum declaration.")
        attributes = {"name": name.lexeme if name else "<missing>"}
        if closing is None or semicolon is None:
            attributes["incomplete"] = True
        return node("EnumDeclaration", members, **attributes)

    def named_type_declaration(self, type_kind: str) -> dict[str, Any]:
        self.advance()
        type_name = self.expect("IDENTIFIER", message=f"Expected a {type_kind} name.")
        pointer = bool(self.match("OPERATOR", "*"))
        identifier = self.expect("IDENTIFIER", message="Expected an identifier after the named type.")
        expression = None
        if self.match("OPERATOR", "="):
            expression = self.expression()
        additional: list[dict[str, Any]] = []
        while self.match("DELIMITER", ","):
            additional_pointer = bool(self.match("OPERATOR", "*"))
            additional_identifier = self.expect("IDENTIFIER", message="Expected an identifier after ','.")
            additional_expression = None
            if self.match("OPERATOR", "="):
                additional_expression = self.expression()
            additional.append({
                "name": additional_identifier.lexeme if additional_identifier else "<missing>",
                "pointer": additional_pointer,
                "expression": additional_expression,
            })
        semicolon = self.expect("DELIMITER", ";", f"Expected ';' after {type_kind} declaration.")
        attributes: dict[str, Any] = {
            "declared_type": type_kind,
            "type_name": type_name.lexeme if type_name else "<missing>",
            "name": identifier.lexeme if identifier else "<missing>",
        }
        if pointer:
            attributes["pointer"] = True
        if additional:
            attributes["additional_declarators"] = additional
        if semicolon is None or identifier is None or (expression is not None and contains_error(expression)) or any(item["expression"] is not None and contains_error(item["expression"]) for item in additional):
            attributes["incomplete"] = True
        return node("Declaration", [expression] if expression else [], **attributes)

    def function_definition(self) -> dict[str, Any]:
        return_type = self.advance().lexeme
        name = self.expect("IDENTIFIER")
        self.expect("DELIMITER", "(", "Expected '(' after function name.")
        parameters: list[dict[str, Any]] = []
        if not self.check("DELIMITER", ")") and not self.check("KEYWORD", "void"):
            while True:
                parameter_type = self.expect("KEYWORD", message="Expected a parameter type.")
                parameter_name = self.expect("IDENTIFIER", message="Expected a parameter name.")
                parameters.append(node("Parameter", [], declared_type=parameter_type.lexeme if parameter_type else "<missing>", name=parameter_name.lexeme if parameter_name else "<missing>"))
                if not self.match("DELIMITER", ","):
                    break
        else:
            self.match("KEYWORD", "void")
        self.expect("DELIMITER", ")", "Expected ')' after function parameters.")
        body = self.block() if self.check("DELIMITER", "{") else None
        children = parameters + ([body] if body else [])
        attributes = {"return_type": return_type, "name": name.lexeme if name else "<missing>"}
        if body is None and self.match("DELIMITER", ";"):
            return node("FunctionPrototype", children, **attributes)
        if body is None or any(contains_error(child) for child in children):
            attributes["incomplete"] = True
        return node("FunctionDefinition", children, **attributes)

    def declaration(self) -> dict[str, Any]:
        qualifier = bool(self.match("KEYWORD", "const"))
        declared_type = self.advance().lexeme
        pointer = bool(self.match("OPERATOR", "*"))
        identifier = self.expect("IDENTIFIER", message="Expected an identifier after the type.")
        dimensions: list[dict[str, Any]] = []
        while self.match("DELIMITER", "["):
            dimensions.append(self.expression())
            self.expect("DELIMITER", "]", "Expected ']' after array dimension.")
        expression = None
        if self.match("OPERATOR", "="):
            expression = self.expression()
        additional: list[dict[str, Any]] = []
        while self.match("DELIMITER", ","):
            additional_pointer = bool(self.match("OPERATOR", "*"))
            additional_identifier = self.expect("IDENTIFIER", message="Expected an identifier after ','.")
            additional_expression = None
            if self.match("OPERATOR", "="):
                additional_expression = self.expression()
            additional.append({
                "name": additional_identifier.lexeme if additional_identifier else "<missing>",
                "pointer": additional_pointer,
                "expression": additional_expression,
            })
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after declaration.")
        attributes: dict[str, Any] = {"declared_type": declared_type, "name": identifier.lexeme if identifier else "<missing>"}
        if pointer:
            attributes["pointer"] = True
        if dimensions:
            attributes["array"] = True
        if qualifier:
            attributes["const"] = True
        if additional:
            attributes["additional_declarators"] = additional
        children = [node("ArrayDimension", [dimension]) for dimension in dimensions] + ([expression] if expression else [])
        if expression is not None and contains_error(expression) or identifier is None or semicolon is None or any(contains_error(dimension) for dimension in dimensions) or any(item["expression"] is not None and contains_error(item["expression"]) for item in additional):
            attributes["incomplete"] = True
        return node("Declaration", children, **attributes)

    def assignment(self) -> dict[str, Any]:
        identifier = self.advance()
        operator = self.expect("OPERATOR", message="Expected an assignment operator.")
        expression = self.expression()
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after assignment.")
        attributes: dict[str, Any] = {"target": identifier.lexeme}
        if operator and operator.lexeme != "=":
            attributes["operator"] = operator.lexeme
        if contains_error(expression) or semicolon is None:
            attributes["incomplete"] = True
        return node("Assignment", [expression], **attributes)

    def indexed_assignment(self) -> dict[str, Any]:
        target = self.postfix_identifier()
        self.expect("OPERATOR", "=", "Expected '=' after indexed target.")
        expression = self.expression()
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after assignment.")
        target_attributes = target.get("children", [{}])[0].get("attributes", {}) if target.get("type") == "IndexExpression" else target.get("attributes", {})
        attributes = {"target": target_attributes.get("name", "<missing>")}
        if semicolon is None or contains_error(target) or contains_error(expression):
            attributes["incomplete"] = True
        return node("Assignment", [target, expression], **attributes)

    def postfix_identifier(self) -> dict[str, Any]:
        token = self.expect("IDENTIFIER")
        return self.postfix(node("Identifier", name=token.lexeme if token else "<missing>"))

    def return_statement(self) -> dict[str, Any]:
        self.advance()
        expression = None if self.check("DELIMITER", ";") else self.expression()
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after return statement.")
        attributes = {"incomplete": True} if semicolon is None or (expression is not None and contains_error(expression)) else {}
        return node("ReturnStatement", [expression] if expression else [], **attributes)

    def call_statement(self) -> dict[str, Any]:
        callee = self.advance()
        self.expect("DELIMITER", "(")
        arguments: list[dict[str, Any]] = []
        if not self.check("DELIMITER", ")"):
            while True:
                arguments.append(self.expression())
                if not self.match("DELIMITER", ","):
                    break
        self.expect("DELIMITER", ")", "Expected ')' after function arguments.")
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after function call.")
        return node("CallStatement", arguments, callee=callee.lexeme, **({"incomplete": True} if semicolon is None else {}))

    def update_statement(self) -> dict[str, Any]:
        prefix = self.current.lexeme if self.check("OPERATOR") and self.current.lexeme in {"++", "--"} else None
        if prefix:
            self.advance()
        identifier = self.expect("IDENTIFIER", message="Expected an identifier for increment or decrement.")
        operator = prefix or (self.advance().lexeme if self.check("OPERATOR") and self.current.lexeme in {"++", "--"} else None)
        if operator is None:
            self.error("C_EXPECTED_TOKEN", "Expected '++' or '--' after identifier.")
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after increment or decrement.")
        attributes = {"operator": operator or "<missing>", "prefix": bool(prefix)}
        if identifier is None or semicolon is None:
            attributes["incomplete"] = True
        return node("UpdateStatement", [node("Identifier", name=identifier.lexeme if identifier else "<missing>")], **attributes)

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

    def do_while_statement(self) -> dict[str, Any]:
        self.advance()
        body = self.declaration_or_statement()
        self.expect("KEYWORD", "while", "Expected 'while' after do body.")
        self.expect("DELIMITER", "(", "Expected '(' after while.")
        condition = self.expression()
        self.expect("DELIMITER", ")", "Expected ')' after do-while condition.")
        semicolon = self.expect("DELIMITER", ";", "Expected ';' after do-while statement.")
        children = ([body] if body else []) + [condition]
        attributes = {"incomplete": True} if body is None or contains_error(condition) or semicolon is None else {}
        return node("DoWhileStatement", children, **attributes)

    def switch_statement(self) -> dict[str, Any]:
        self.advance()
        self.expect("DELIMITER", "(", "Expected '(' after switch.")
        expression = self.expression()
        self.expect("DELIMITER", ")", "Expected ')' after switch expression.")
        self.expect("DELIMITER", "{", "Expected '{' after switch expression.")
        cases: list[dict[str, Any]] = []
        while not self.check("DELIMITER", "}") and not self.check("EOF"):
            is_default = bool(self.match("KEYWORD", "default"))
            label = None if is_default else self.expect("KEYWORD", "case", "Expected 'case' or 'default' in switch.")
            value = None if is_default else self.expression()
            self.expect("DELIMITER", ":", "Expected ':' after switch label.")
            body: list[dict[str, Any]] = []
            while not self.check("KEYWORD", "case") and not self.check("KEYWORD", "default") and not self.check("DELIMITER", "}") and not self.check("EOF"):
                statement = self.declaration_or_statement()
                if statement:
                    body.append(statement)
            cases.append(node("CaseStatement", ([value] if value else []) + body, **({"default": True} if is_default else {})))
        closing = self.expect("DELIMITER", "}", "Expected '}' after switch body.")
        children = [expression] + cases
        return node("SwitchStatement", children, **({"incomplete": True} if closing is None else {}))

    def simple_control_statement(self, statement_type: str) -> dict[str, Any]:
        self.advance()
        semicolon = self.expect("DELIMITER", ";", f"Expected ';' after {statement_type.replace('Statement', '').lower()}.")
        return node(statement_type, [], **({"incomplete": True} if semicolon is None else {}))

    def for_statement(self) -> dict[str, Any]:
        self.advance()
        self.expect("DELIMITER", "(", "Expected '(' after for.")
        initializer = self.declaration() if self.check("KEYWORD") and self.current.lexeme in TYPE_KEYWORDS else self.assignment()
        condition = self.expression()
        self.expect("DELIMITER", ";", "Expected ';' after for condition.")
        update = self.assignment_expression() if self.check("IDENTIFIER") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme in {"=", "+=", "-=", "*=", "/=", "%="} else self.expression()
        self.expect("DELIMITER", ")", "Expected ')' after for clauses.")
        body = self.declaration_or_statement()
        children = [initializer, condition, update] + ([body] if body else [])
        attributes = {"incomplete": True} if body is None or any(contains_error(child) for child in children) else {}
        return node("ForStatement", children, **attributes)

    def assignment_expression(self) -> dict[str, Any]:
        identifier = self.advance()
        operator = self.advance().lexeme
        expression = self.expression()
        return node("AssignmentExpression", [expression], target=identifier.lexeme, operator=operator)

    def expression(self) -> dict[str, Any]:
        return self.logical_or()

    def logical_or(self) -> dict[str, Any]:
        left = self.logical_and()
        while self.match("OPERATOR", "||"):
            left = node("BinaryExpression", [left, self.logical_and()], operator="||")
        return left

    def logical_and(self) -> dict[str, Any]:
        left = self.bitwise_or()
        while self.match("OPERATOR", "&&"):
            left = node("BinaryExpression", [left, self.bitwise_or()], operator="&&")
        return left

    def bitwise_or(self) -> dict[str, Any]:
        left = self.bitwise_and()
        while self.match("OPERATOR", "|"):
            left = node("BinaryExpression", [left, self.bitwise_and()], operator="|")
        return left

    def bitwise_and(self) -> dict[str, Any]:
        left = self.comparison()
        while self.match("OPERATOR", "&"):
            left = node("BinaryExpression", [left, self.comparison()], operator="&")
        return left

    def comparison(self) -> dict[str, Any]:
        left = self.additive()
        while self.check("OPERATOR") and self.current.lexeme in {"==", "!=", "<", ">", "<=", ">="}:
            operator = self.advance().lexeme
            right = self.additive()
            left = node("BinaryExpression", [left, right], operator=operator)
        return left

    def additive(self) -> dict[str, Any]:
        left = self.multiplicative()
        while self.check("OPERATOR") and self.current.lexeme in {"+", "-", "<<", ">>"}:
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
        if self.check("OPERATOR") and self.current.lexeme in {"+", "-", "!", "&", "*", "~"}:
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
            self.advance()
            return self.postfix(node("Identifier", name=token.lexeme))
        if token.type == "KEYWORD" and token.lexeme in {"true", "false"}:
            self.advance(); return node("BooleanLiteral", value=token.lexeme == "true")
        if self.match("DELIMITER", "{"):
            values: list[dict[str, Any]] = []
            if not self.check("DELIMITER", "}"):
                while True:
                    values.append(self.expression())
                    if not self.match("DELIMITER", ","):
                        break
                    if self.check("DELIMITER", "}"):
                        break
            self.expect("DELIMITER", "}", "Expected '}' after initializer list.")
            return node("InitializerList", values)
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

    def postfix(self, base: dict[str, Any]) -> dict[str, Any]:
        while True:
            if self.match("DELIMITER", "("):
                arguments: list[dict[str, Any]] = []
                if not self.check("DELIMITER", ")"):
                    while True:
                        arguments.append(self.expression())
                        if not self.match("DELIMITER", ","):
                            break
                self.expect("DELIMITER", ")", "Expected ')' after function arguments.")
                base = node("CallExpression", [base, *arguments])
            elif self.match("DELIMITER", "["):
                index = self.expression()
                self.expect("DELIMITER", "]", "Expected ']' after array index.")
                base = node("IndexExpression", [base, index])
            elif self.match("OPERATOR", "++") or self.match("OPERATOR", "--"):
                base = node("UpdateExpression", [base], operator=self.tokens[self.index - 1].lexeme)
            elif self.match("DELIMITER", ".") or self.match("OPERATOR", "->"):
                member = self.expect("IDENTIFIER", message="Expected a member name after member access.")
                base = node("MemberExpression", [base, node("Identifier", name=member.lexeme if member else "<missing>")])
            else:
                break
        return base

    def synchronize(self) -> None:
        while not self.check("EOF") and not self.check("DELIMITER", ";") and not self.check("DELIMITER", "}"):
            self.advance()
        self.match("DELIMITER", ";")
