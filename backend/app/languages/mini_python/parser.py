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
        if self.check("IDENTIFIER") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme == ",":
            lookahead = self.index
            while lookahead < len(self.tokens) and self.tokens[lookahead].type not in {"NEWLINE", "EOF", "DEDENT"}:
                if self.tokens[lookahead].lexeme == "=":
                    return self.assignment()
                lookahead += 1
        if self.check("IDENTIFIER") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme in {"=", "+=", "-=", "*=", "/=", "%="}:
            return self.assignment()
        if self.check("IDENTIFIER") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme in {"[", "."}:
            lookahead = self.index
            while lookahead < len(self.tokens) and self.tokens[lookahead].type not in {"NEWLINE", "EOF", "DEDENT"}:
                if self.tokens[lookahead].lexeme in {"=", "+=", "-=", "*=", "/=", "%="}:
                    return self.assignment()
                lookahead += 1
        if self.check("KEYWORD", "print"):
            return self.print_statement()
        if self.check("KEYWORD", "if"):
            return self.block_statement("IfStatement")
        if self.check("KEYWORD", "while"):
            return self.block_statement("WhileStatement")
        if self.check("KEYWORD", "for"):
            return self.for_statement()
        if self.check("KEYWORD", "def"):
            return self.function_definition()
        if self.check("KEYWORD", "return"):
            return self.return_statement()
        if self.check("KEYWORD", "import"):
            return self.import_statement()
        if self.check("KEYWORD", "from"):
            return self.from_import_statement()
        if self.check("KEYWORD", "try"):
            return self.try_statement()
        if self.check("KEYWORD", "raise"):
            return self.raise_statement()
        if self.check("KEYWORD", "with"):
            return self.with_statement()
        if self.check("KEYWORD", "global") or self.check("KEYWORD", "nonlocal"):
            return self.scope_statement()
        if self.check("KEYWORD", "pass"):
            self.advance(); return node("PassStatement")
        if self.check("KEYWORD", "break"):
            self.advance(); return node("BreakStatement")
        if self.check("KEYWORD", "continue"):
            self.advance(); return node("ContinueStatement")
        if self.check("IDENTIFIER") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme == "(":
            return self.call_statement()
        if self.check("KEYWORD", "else"):
            self.error("PY_UNEXPECTED_ELSE", "An else block must follow an if statement.")
        elif self.check("IDENTIFIER") or self.check("NUMBER") or self.check("STRING") or self.check("DELIMITER", "("):
            expression = self.expression()
            return node("ExpressionStatement", [expression], **({"incomplete": True} if contains_error(expression) else {}))
        else:
            self.error("PY_UNEXPECTED_TOKEN", "Expected a supported statement.")
        self.synchronize()
        return None

    def assignment(self) -> dict[str, Any] | None:
        if self.check("IDENTIFIER") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme == ",":
            targets = [self.advance()]
            while self.match("DELIMITER", ","):
                target = self.expect("IDENTIFIER", message="Expected a name in tuple assignment.")
                if target:
                    targets.append(target)
            operator = self.expect("OPERATOR", "=", "Expected '=' after assignment targets.")
            expression = self.expression()
            attributes: dict[str, Any] = {"target": targets[0].lexeme, "targets": [item.lexeme for item in targets]}
            if operator is None or contains_error(expression):
                attributes["incomplete"] = True
            return node("Assignment", [expression], **attributes)
        first = self.advance()
        target = self.postfix(node("Identifier", name=first.lexeme))
        identifiers = [first] if target and target.get("type") == "Identifier" else []
        operator = self.expect("OPERATOR", message="Expected an assignment operator.")
        while operator and operator.lexeme == "=" and self.check("IDENTIFIER") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme == "=":
            identifiers.append(self.advance())
            self.advance()
        expression = self.expression()
        attributes: dict[str, Any] = {"target": first.lexeme}
        if len(identifiers) > 1:
            attributes["targets"] = [identifier.lexeme for identifier in identifiers]
        if operator and operator.lexeme != "=":
            attributes["operator"] = operator.lexeme
        if contains_error(expression):
            attributes["incomplete"] = True
        if target and target.get("type") != "Identifier":
            return node("Assignment", [target, expression], **attributes)
        return node("Assignment", [expression], **attributes)

    def print_statement(self) -> dict[str, Any] | None:
        self.advance()
        self.expect("DELIMITER", "(", "Expected '(' after print.")
        expressions: list[dict[str, Any] | None] = []
        if not self.check("DELIMITER", ")"):
            while True:
                argument_operator = None
                if self.match("OPERATOR", "*") or self.match("OPERATOR", "**"):
                    argument_operator = self.tokens[self.index - 1].lexeme
                if self.check("IDENTIFIER") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme == "=":
                    name = self.advance().lexeme
                    self.advance()
                    expressions.append(node("KeywordArgument", [self.expression()], name=name))
                else:
                    argument = self.expression()
                    expressions.append(node("StarArgument", [argument], operator=argument_operator) if argument_operator else argument)
                if not self.match("DELIMITER", ","):
                    break
        self.expect("DELIMITER", ")", "Expected ')' after print expression.")
        attributes: dict[str, Any] = {}
        if any(contains_error(expression) for expression in expressions):
            attributes["incomplete"] = True
        return node("PrintStatement", expressions, **attributes)

    def call_statement(self) -> dict[str, Any]:
        expression = self.expression()
        return node("ExpressionStatement", [expression], **({"incomplete": True} if contains_error(expression) else {}))

    def for_statement(self) -> dict[str, Any]:
        keyword = self.advance()
        target = self.expect("IDENTIFIER", message="Expected a loop variable after for.")
        self.expect("KEYWORD", "in", "Expected 'in' after the loop variable.")
        iterable = self.expression()
        self.expect("DELIMITER", ":", "Expected ':' after for loop iterable.")
        body = self.parse_indented_body()
        children = [node("Identifier", name=target.lexeme if target else "<missing>"), iterable] + body
        if self.check("KEYWORD", "else"):
            children.append(self.block_statement("ElseStatement"))
        attributes = {"keyword": keyword.lexeme}
        if target is None or contains_error(iterable) or not body:
            attributes["incomplete"] = True
        return node("ForStatement", children, **attributes)

    def parse_indented_body(self) -> list[dict[str, Any]]:
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
        return body

    def function_definition(self) -> dict[str, Any]:
        self.advance()
        name = self.expect("IDENTIFIER", message="Expected a function name after def.")
        self.expect("DELIMITER", "(", "Expected '(' after function name.")
        parameters: list[dict[str, Any]] = []
        while self.check("IDENTIFIER"):
            parameter = self.advance()
            default = None
            if self.match("OPERATOR", "="):
                default = self.expression()
            parameters.append(node("Parameter", [default] if default else [], name=parameter.lexeme))
            if not self.match("DELIMITER", ","):
                break
        self.expect("DELIMITER", ")", "Expected ')' after parameters.")
        self.expect("DELIMITER", ":", "Expected ':' after function definition.")
        body = self.parse_indented_body()
        attributes = {"name": name.lexeme if name else "<missing>"}
        if name is None or not body:
            attributes["incomplete"] = True
        return node("FunctionDefinitionPython", parameters + body, **attributes)

    def return_statement(self) -> dict[str, Any]:
        self.advance()
        expression = None if self.check("NEWLINE") or self.check("DEDENT") or self.check("EOF") else self.expression()
        return node("ReturnStatementPython", [expression] if expression else [])

    def raise_statement(self) -> dict[str, Any]:
        self.advance()
        expression = None if self.check("NEWLINE") or self.check("DEDENT") or self.check("EOF") else self.expression()
        return node("RaiseStatement", [expression] if expression else [])

    def try_statement(self) -> dict[str, Any]:
        self.advance()
        self.expect("DELIMITER", ":", "Expected ':' after try.")
        body = self.parse_indented_body()
        clauses: list[dict[str, Any]] = []
        while self.match("KEYWORD", "except"):
            exception = None
            if not self.check("DELIMITER", ":"):
                exception = self.expression()
            alias = None
            if self.match("KEYWORD", "as"):
                alias_token = self.expect("IDENTIFIER", message="Expected an exception name after 'as'.")
                alias = node("Identifier", name=alias_token.lexeme if alias_token else "<missing>")
            self.expect("DELIMITER", ":", "Expected ':' after except clause.")
            clauses.append(node("ExceptClause", ([exception] if exception else []) + ([alias] if alias else []) + self.parse_indented_body(), has_exception=exception is not None, has_alias=alias is not None))
        if self.match("KEYWORD", "finally"):
            self.expect("DELIMITER", ":", "Expected ':' after finally.")
            clauses.append(node("FinallyClause", self.parse_indented_body()))
        if not clauses:
            self.error("PY_EXPECTED_TOKEN", "Expected an except or finally clause.")
        return node("TryStatement", [*body, *clauses], **({"incomplete": True} if not clauses else {}))

    def with_statement(self) -> dict[str, Any]:
        self.advance()
        context = self.expression()
        alias = None
        if self.match("KEYWORD", "as"):
            identifier = self.expect("IDENTIFIER", message="Expected a name after 'as'.")
            alias = node("Identifier", name=identifier.lexeme if identifier else "<missing>")
        self.expect("DELIMITER", ":", "Expected ':' after with item.")
        body = self.parse_indented_body()
        return node("WithStatement", [context] + ([alias] if alias else []) + body)

    def scope_statement(self) -> dict[str, Any]:
        keyword = self.advance().lexeme
        names: list[dict[str, Any]] = []
        while True:
            name = self.expect("IDENTIFIER", message=f"Expected a name after {keyword}.")
            if name:
                names.append(node("Identifier", name=name.lexeme))
            if not self.match("DELIMITER", ","):
                break
        return node("ScopeStatement", names, keyword=keyword)

    def import_statement(self) -> dict[str, Any]:
        self.advance()
        modules: list[dict[str, Any]] = []
        while True:
            parts = self.import_name()
            alias = None
            if self.match("KEYWORD", "as"):
                alias_token = self.expect("IDENTIFIER", message="Expected an alias after 'as'.")
                alias = alias_token.lexeme if alias_token else "<missing>"
            modules.append(node("ImportName", parts, alias=alias) if alias else node("ImportName", parts))
            if not self.match("DELIMITER", ","):
                break
        return node("ImportStatement", modules)

    def from_import_statement(self) -> dict[str, Any]:
        self.advance()
        module = self.import_name()
        self.expect("KEYWORD", "import", "Expected 'import' in from-import statement.")
        parenthesized = bool(self.match("DELIMITER", "("))
        names: list[dict[str, Any]] = []
        while True:
            name = self.expect("IDENTIFIER", message="Expected an imported name.")
            alias = None
            if self.match("KEYWORD", "as"):
                alias_token = self.expect("IDENTIFIER", message="Expected an alias after 'as'.")
                alias = alias_token.lexeme if alias_token else "<missing>"
            names.append(node("ImportedName", name=name.lexeme if name else "<missing>", alias=alias) if alias else node("ImportedName", name=name.lexeme if name else "<missing>"))
            if not self.match("DELIMITER", ","):
                break
        if parenthesized:
            self.expect("DELIMITER", ")", "Expected ')' after imported names.")
        return node("FromImportStatement", [node("ModuleName", module), *names], parenthesized=parenthesized)

    def import_name(self) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = []
        identifier = self.expect("IDENTIFIER", message="Expected a module name.")
        if identifier:
            parts.append(node("Identifier", name=identifier.lexeme))
        while self.match("DELIMITER", "."):
            identifier = self.expect("IDENTIFIER", message="Expected a module name after '.'.")
            if identifier:
                parts.append(node("Identifier", name=identifier.lexeme))
        return parts

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
        if statement_type == "IfStatement" and self.check("KEYWORD", "elif"):
            else_node = self.block_statement("ElifStatement")
            if else_node:
                result["children"].append(else_node)
        elif statement_type == "ElifStatement" and self.check("KEYWORD", "elif"):
            else_node = self.block_statement("ElifStatement")
            if else_node:
                result["children"].append(else_node)
        elif statement_type in {"IfStatement", "ElifStatement"} and self.check("KEYWORD", "else"):
            else_node = self.block_statement("ElseStatement")
            if else_node:
                result["children"].append(else_node)
        elif statement_type in {"WhileStatement", "ForStatement"} and self.check("KEYWORD", "else"):
            else_node = self.block_statement("ElseStatement")
            if else_node:
                result["children"].append(else_node)
        return result

    def expression(self) -> dict[str, Any] | None:
        condition = self.boolean_or()
        if self.match("KEYWORD", "if"):
            test = self.boolean_or()
            self.expect("KEYWORD", "else", "Expected 'else' in conditional expression.")
            alternate = self.expression()
            return node("ConditionalExpression", [condition, test, alternate] if condition and test and alternate else [],)
        return condition

    def boolean_or(self) -> dict[str, Any] | None:
        left = self.boolean_and()
        while self.match("KEYWORD", "or"):
            right = self.boolean_and()
            left = node("BinaryExpression", [left, right] if left and right else [], operator="or")
        return left

    def boolean_and(self) -> dict[str, Any] | None:
        left = self.bitwise_or()
        while self.match("KEYWORD", "and"):
            right = self.bitwise_or()
            left = node("BinaryExpression", [left, right] if left and right else [], operator="and")
        return left

    def bitwise_or(self) -> dict[str, Any] | None:
        left = self.bitwise_xor()
        while self.match("OPERATOR", "|"):
            left = node("BinaryExpression", [left, self.bitwise_xor()], operator="|")
        return left

    def bitwise_xor(self) -> dict[str, Any] | None:
        left = self.bitwise_and()
        while self.match("OPERATOR", "^"):
            left = node("BinaryExpression", [left, self.bitwise_and()], operator="^")
        return left

    def bitwise_and(self) -> dict[str, Any] | None:
        left = self.comparison()
        while self.match("OPERATOR", "&"):
            left = node("BinaryExpression", [left, self.comparison()], operator="&")
        return left

    def comparison(self) -> dict[str, Any] | None:
        left = self.additive()
        while (self.check("OPERATOR") and self.current.lexeme in {"==", "!=", "<", ">", "<=", ">="}) or self.check("KEYWORD", "in") or self.check("KEYWORD", "is") or (self.check("KEYWORD", "not") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme == "in"):
            if self.check("KEYWORD", "not") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme == "in":
                self.advance(); self.advance(); operator = "not in"
            elif self.check("KEYWORD", "is") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme == "not":
                self.advance(); self.advance(); operator = "is not"
            else:
                operator = self.advance().lexeme
            right = self.additive()
            if right is None:
                break
            left = node("BinaryExpression", [left, right] if left else [right], operator=operator)
        return left

    def additive(self) -> dict[str, Any] | None:
        left = self.multiplicative()
        while self.check("OPERATOR") and self.current.lexeme in {"+", "-", "<<", ">>"}:
            operator = self.advance().lexeme
            right = self.multiplicative()
            if right is None:
                break
            left = node("BinaryExpression", [left, right] if left else [right], operator=operator)
        return left

    def multiplicative(self) -> dict[str, Any] | None:
        left = self.unary()
        while self.check("OPERATOR") and self.current.lexeme in {"*", "/", "//", "%", "**"}:
            operator = self.advance().lexeme
            right = self.unary()
            if right is None:
                break
            left = node("BinaryExpression", [left, right] if left else [right], operator=operator)
        return left

    def unary(self) -> dict[str, Any] | None:
        if self.match("KEYWORD", "not"):
            return node("UnaryExpression", [self.unary()], operator="not")
        if self.check("OPERATOR") and self.current.lexeme in {"+", "-", "~"}:
            operator = self.advance().lexeme
            operand = self.unary()
            return node("UnaryExpression", [operand] if operand else [], operator=operator)
        return self.primary()

    def primary(self) -> dict[str, Any] | None:
        token = self.current
        if token.type == "NUMBER":
            self.advance()
            return self.postfix(node("NumberLiteral", value=token.lexeme))
        if token.type == "STRING":
            self.advance()
            return self.postfix(node("StringLiteral", value=token.lexeme))
        if token.type == "IDENTIFIER":
            self.advance()
            return self.postfix(node("Identifier", name=token.lexeme))
        if token.type == "KEYWORD" and token.lexeme in {"True", "False"}:
            self.advance()
            return self.postfix(node("BooleanLiteral", value=token.lexeme == "True"))
        if token.type == "KEYWORD" and token.lexeme == "None":
            self.advance()
            return self.postfix(node("NoneLiteral", value=None))
        if self.match("KEYWORD", "lambda"):
            parameters: list[dict[str, Any]] = []
            while self.check("IDENTIFIER"):
                parameter = self.advance()
                parameters.append(node("Parameter", name=parameter.lexeme))
                if not self.match("DELIMITER", ","):
                    break
            self.expect("DELIMITER", ":", "Expected ':' after lambda parameters.")
            return node("LambdaExpression", [*parameters, self.expression()])
        if self.match("DELIMITER", "["):
            elements: list[dict[str, Any]] = []
            if not self.check("DELIMITER", "]"):
                while True:
                    elements.append(self.expression())
                    if not self.match("DELIMITER", ","):
                        break
            self.expect("DELIMITER", "]", "Expected ']' after list literal.")
            return self.postfix(node("ListLiteral", elements))
        if self.match("DELIMITER", "{"):
            if self.match("DELIMITER", "}"):
                return node("DictLiteral", [])
            first = self.expression()
            if self.match("DELIMITER", ":"):
                values = [node("KeyValue", [first, self.expression()])]
                while self.match("DELIMITER", ","):
                    if self.check("DELIMITER", "}"):
                        break
                    key = self.expression()
                    self.expect("DELIMITER", ":", "Expected ':' between dictionary key and value.")
                    values.append(node("KeyValue", [key, self.expression()]))
                self.expect("DELIMITER", "}", "Expected '}' after dictionary literal.")
                return self.postfix(node("DictLiteral", values))
            elements = [first]
            while self.match("DELIMITER", ","):
                if self.check("DELIMITER", "}"):
                    break
                elements.append(self.expression())
            self.expect("DELIMITER", "}", "Expected '}' after set literal.")
            return self.postfix(node("SetLiteral", elements))
        if self.match("DELIMITER", "("):
            expression = self.expression()
            if self.match("DELIMITER", ","):
                elements = [expression]
                while not self.check("DELIMITER", ")"):
                    elements.append(self.expression())
                    if not self.match("DELIMITER", ","):
                        break
                self.expect("DELIMITER", ")", "Expected ')' after tuple literal.")
                return self.postfix(node("TupleLiteral", elements))
            self.expect("DELIMITER", ")", "Expected ')' to close expression.")
            return self.postfix(expression)
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

    def postfix(self, base: dict[str, Any] | None) -> dict[str, Any] | None:
        while base is not None:
            if self.match("DELIMITER", "("):
                arguments: list[dict[str, Any]] = []
                if not self.check("DELIMITER", ")"):
                    while True:
                        argument_operator = None
                        if self.match("OPERATOR", "*") or self.match("OPERATOR", "**"):
                            argument_operator = self.tokens[self.index - 1].lexeme
                        if self.check("IDENTIFIER") and self.index + 1 < len(self.tokens) and self.tokens[self.index + 1].lexeme == "=":
                            name = self.advance().lexeme
                            self.advance()
                            arguments.append(node("KeywordArgument", [self.expression()], name=name))
                        else:
                            argument = self.expression()
                            arguments.append(node("StarArgument", [argument], operator=argument_operator) if argument_operator else argument)
                        if not self.match("DELIMITER", ","):
                            break
                self.expect("DELIMITER", ")", "Expected ')' after function arguments.")
                base = node("CallExpression", [base, *arguments])
                continue
            if self.match("DELIMITER", "["):
                start = None if self.check("DELIMITER", ":") else self.expression()
                if self.match("DELIMITER", ":"):
                    stop = None if self.check("DELIMITER", "]") else self.expression()
                    step = None
                    if self.match("DELIMITER", ":"):
                        step = None if self.check("DELIMITER", "]") else self.expression()
                    self.expect("DELIMITER", "]", "Expected ']' after slice.")
                    base = node("SliceExpression", [child for child in (base, start, stop, step) if child is not None])
                else:
                    self.expect("DELIMITER", "]", "Expected ']' after index.")
                    base = node("IndexExpression", [base, start] if start else [base])
                continue
            if self.match("DELIMITER", "."):
                member = self.expect("IDENTIFIER", message="Expected an attribute name after '.'.")
                base = node("MemberExpression", [base, node("Identifier", name=member.lexeme if member else "<missing>")])
                continue
            break
        return base

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
