"""Bounded interpreter for the deliberately small executable Mini C++ subset."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any


class MiniCppExecutionError(Exception):
    def __init__(self, message: str, category: str = "runtime") -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class MiniCppExecutionOutcome:
    status: str
    stdout: str
    stderr: str
    duration_ms: float
    message: str
    error_category: str | None = None


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(os.getenv(name, str(default)))))
    except ValueError:
        return default


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        return max(minimum, min(maximum, float(os.getenv(name, str(default)))))
    except ValueError:
        return default


class _ReturnSignal(Exception):
    def __init__(self, value: Any) -> None:
        self.value = value


class MiniCppInterpreter:
    def __init__(self, tree: dict[str, Any], stdin: str = "") -> None:
        self.tree = tree
        self.stdin = stdin
        self.environment: dict[str, Any] = {}
        self.functions: dict[str, dict[str, Any]] = {}
        self.output: list[str] = []
        self.input_index = 0
        self.steps = 0
        self.started = time.monotonic()
        self.max_steps = _bounded_int("CODELENS_MINI_CPP_MAX_STEPS", 10_000, 1, 1_000_000)
        self.max_output = _bounded_int("CODELENS_MINI_CPP_MAX_OUTPUT_LENGTH", 64_000, 1, 1_000_000)
        self.max_time = _bounded_float("CODELENS_MINI_CPP_TIMEOUT_SECONDS", 2.0, 0.01, 10.0)
        self.max_call_depth = _bounded_int("CODELENS_MINI_CPP_MAX_CALL_DEPTH", 32, 1, 128)

    def run(self) -> MiniCppExecutionOutcome:
        try:
            self._collect_functions(self.tree)
            top_level = [child for child in self.tree.get("children", []) if child.get("type") != "FunctionDefinition"]
            self._execute_statements(top_level, 0)
            if "main" in self.functions:
                self._call_function("main", [], 0)
            stdout = "".join(self.output)
            return MiniCppExecutionOutcome("Success", stdout, "", self._duration_ms(), "Interpreted Mini C++ execution completed successfully.")
        except MiniCppExecutionError as error:
            return MiniCppExecutionOutcome("Error", "".join(self.output), str(error), self._duration_ms(), "Interpreted Mini C++ execution did not complete.", error.category)
        except _ReturnSignal:
            return MiniCppExecutionOutcome("Error", "".join(self.output), "Return is only supported inside a function.", self._duration_ms(), "Interpreted Mini C++ execution did not complete.", "unsupported")

    def _duration_ms(self) -> float:
        return (time.monotonic() - self.started) * 1000

    def _tick(self) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise MiniCppExecutionError("Mini C++ interpreter step limit exceeded.", "resource_limit")
        if time.monotonic() - self.started > self.max_time:
            raise MiniCppExecutionError("Mini C++ interpreter time limit exceeded.", "timeout")

    def _collect_functions(self, tree: dict[str, Any]) -> None:
        for child in tree.get("children", []):
            if child.get("type") == "FunctionDefinition":
                attributes = child.get("attributes", {})
                body = next((item for item in child.get("children", []) if item.get("type") == "BlockStatement"), None)
                if body is None:
                    continue
                name = attributes.get("name")
                if not isinstance(name, str) or name in self.functions:
                    raise MiniCppExecutionError("Malformed or duplicate function definition is not executable.", "unsupported")
                self.functions[name] = {"node": child, "body": body, "parameters": [item for item in child.get("children", []) if item.get("type") == "Parameter"]}

    def _execute_statements(self, statements: list[dict[str, Any]], depth: int) -> None:
        for statement in statements:
            self._tick()
            self._execute_statement(statement, depth)

    def _execute_statement(self, statement: dict[str, Any], depth: int) -> None:
        statement_type = statement.get("type")
        if statement_type in {"IncludeDirective", "UsingNamespace", "UsingDeclaration", "EmptyStatement"}:
            return
        if statement_type == "VariableDeclaration":
            declared_type = statement.get("attributes", {}).get("declared_type", "")
            if not self._supported_type(declared_type):
                raise MiniCppExecutionError(f"Mini C++ interpreter does not support type {declared_type!r}.", "unsupported")
            for declarator in statement.get("children", []):
                attributes = declarator.get("attributes", {})
                name = attributes.get("name")
                if not isinstance(name, str) or name == "<missing>":
                    raise MiniCppExecutionError("Malformed declaration cannot be executed.", "unsupported")
                children = declarator.get("children", [])
                if any(child.get("type") == "InitializerList" for child in children) or any(child.get("type") == "NumberLiteral" for child in children[1:]):
                    raise MiniCppExecutionError("Arrays and initializer lists are analysis-only in the Mini C++ interpreter.", "unsupported")
                self.environment[name] = self._evaluate(children[0]) if children else self._default_value(declared_type)
            return
        if statement_type == "Assignment":
            target, value = statement.get("children", [None, None])
            name = self._target_name(target)
            if name is None:
                raise MiniCppExecutionError("Only simple variable assignments are executable.", "unsupported")
            right = self._evaluate(value)
            operator = statement.get("attributes", {}).get("operator", "=")
            self.environment[name] = self._apply_assignment(operator, self.environment.get(name, 0), right)
            return
        if statement_type == "UpdateStatement":
            target = statement.get("children", [None])[0]
            name = self._target_name(target)
            if name is None:
                raise MiniCppExecutionError("Only simple variable updates are executable.", "unsupported")
            self.environment[name] = self.environment.get(name, 0) + (1 if statement.get("attributes", {}).get("operator") == "++" else -1)
            return
        if statement_type in {"OutputStatement", "InputStatement"}:
            self._execute_stream(statement)
            return
        if statement_type == "ExpressionStatement":
            self._evaluate(statement.get("children", [None])[0])
            return
        if statement_type == "ReturnStatement":
            value = self._evaluate(statement["children"][0]) if statement.get("children") else None
            raise _ReturnSignal(value)
        if statement_type == "BlockStatement":
            self._execute_statements(statement.get("children", []), depth)
            return
        if statement_type == "FunctionDefinition":
            return
        raise MiniCppExecutionError(f"Mini C++ interpreter does not support statement {statement_type!r}.", "unsupported")

    def _supported_type(self, declared_type: str) -> bool:
        return declared_type in {"int", "short", "long", "long long", "signed", "unsigned", "float", "double", "string", "std::string"}

    def _default_value(self, declared_type: str) -> Any:
        return 0.0 if declared_type in {"float", "double"} else "" if "string" in declared_type else 0

    def _target_name(self, target: dict[str, Any] | None) -> str | None:
        if not target or target.get("type") != "Identifier":
            return None
        name = target.get("attributes", {}).get("name")
        return name if isinstance(name, str) and "::" not in name else None

    def _apply_assignment(self, operator: str, current: Any, value: Any) -> Any:
        if operator == "=": return value
        if operator == "+=": return current + value
        if operator == "-=": return current - value
        if operator == "*=": return current * value
        if operator == "/=": return self._divide(current, value)
        if operator == "%=": return current % value
        raise MiniCppExecutionError(f"Assignment operator {operator!r} is unsupported.", "unsupported")

    def _execute_stream(self, statement: dict[str, Any]) -> None:
        if statement.get("type") == "InputStatement":
            for value in statement.get("children", []):
                name = self._target_name(value)
                if name is None:
                    raise MiniCppExecutionError("Mini C++ input requires simple variables.", "unsupported")
                raw = self._next_input()
                current = self.environment.get(name, 0)
                try:
                    self.environment[name] = float(raw) if isinstance(current, float) else int(raw)
                except ValueError as error:
                    raise MiniCppExecutionError("Mini C++ input could not be converted to the variable type.", "runtime") from error
            return
        for value in statement.get("children", []):
            if value.get("type") == "EndlLiteral":
                self._append_output("\n")
            else:
                self._append_output(str(self._evaluate(value)))

    def _next_input(self) -> str:
        while self.input_index < len(self.stdin) and self.stdin[self.input_index].isspace():
            self.input_index += 1
        start = self.input_index
        while self.input_index < len(self.stdin) and not self.stdin[self.input_index].isspace():
            self.input_index += 1
        if start == self.input_index:
            raise MiniCppExecutionError("Mini C++ input was exhausted.", "runtime")
        return self.stdin[start:self.input_index]

    def _append_output(self, value: str) -> None:
        if sum(len(item) for item in self.output) + len(value) > self.max_output:
            raise MiniCppExecutionError("Mini C++ interpreter output limit exceeded.", "resource_limit")
        self.output.append(value)

    def _evaluate(self, expression: dict[str, Any] | None, depth: int = 0) -> Any:
        self._tick()
        if expression is None:
            raise MiniCppExecutionError("Incomplete expression cannot be executed.", "unsupported")
        expression_type = expression.get("type")
        attributes = expression.get("attributes", {})
        if expression_type == "NumberLiteral":
            value = attributes.get("value", "0")
            return float(value) if "." in str(value) else int(value)
        if expression_type == "StringLiteral":
            return self._decode_string(str(attributes.get("value", '""')))
        if expression_type == "CharacterLiteral":
            return self._decode_string(str(attributes.get("value", "''")))
        if expression_type == "BooleanLiteral": return bool(attributes.get("value"))
        if expression_type == "NullptrLiteral": return None
        if expression_type == "Identifier":
            name = attributes.get("name")
            if name not in self.environment:
                raise MiniCppExecutionError(f"Variable {name!r} is not initialized.", "runtime")
            return self.environment[name]
        if expression_type == "ParenthesizedExpression": return self._evaluate(expression.get("children", [None])[0], depth)
        if expression_type == "UnaryExpression":
            operator = attributes.get("operator")
            value = self._evaluate(expression.get("children", [None])[0], depth)
            if operator == "+": return +value
            if operator == "-": return -value
            if operator == "!": return not value
            if operator in {"++", "--"}:
                target = expression.get("children", [None])[0]
                name = self._target_name(target)
                if name is None: raise MiniCppExecutionError("Increment and decrement require simple variables.", "unsupported")
                self.environment[name] = value + (1 if operator == "++" else -1)
                return self.environment[name]
            raise MiniCppExecutionError(f"Unary operator {operator!r} is unsupported.", "unsupported")
        if expression_type == "UpdateExpression":
            target = expression.get("children", [None])[0]
            name = self._target_name(target)
            if name is None: raise MiniCppExecutionError("Update expressions require simple variables.", "unsupported")
            old = self.environment.get(name, 0); self.environment[name] = old + (1 if attributes.get("operator") == "++" else -1); return old
        if expression_type == "BinaryExpression":
            operator = attributes.get("operator")
            left = self._evaluate(expression.get("children", [None, None])[0], depth)
            right = self._evaluate(expression.get("children", [None, None])[1], depth)
            if operator in {"=", "+=", "-=", "*=", "/=", "%="}:
                target = expression.get("children", [None])[0]
                name = self._target_name(target)
                if name is None: raise MiniCppExecutionError("Assignment requires a simple variable target.", "unsupported")
                self.environment[name] = self._apply_assignment(operator, left, right); return self.environment[name]
            if operator == "+": return left + right
            if operator == "-": return left - right
            if operator == "*": return left * right
            if operator == "/": return self._divide(left, right)
            if operator == "%": return left % right
            if operator == "==": return left == right
            if operator == "!=": return left != right
            if operator == "<": return left < right
            if operator == "<=": return left <= right
            if operator == ">": return left > right
            if operator == ">=": return left >= right
            if operator == "&&": return bool(left and right)
            if operator == "||": return bool(left or right)
            raise MiniCppExecutionError(f"Binary operator {operator!r} is unsupported.", "unsupported")
        if expression_type == "CallExpression":
            return self._call_function(str(attributes.get("callee")), [self._evaluate(child, depth) for child in expression.get("children", [])], depth + 1)
        raise MiniCppExecutionError(f"Mini C++ interpreter does not support expression {expression_type!r}.", "unsupported")

    def _call_function(self, name: str, arguments: list[Any], depth: int) -> Any:
        if depth > self.max_call_depth:
            raise MiniCppExecutionError("Mini C++ interpreter call-depth limit exceeded.", "resource_limit")
        function = self.functions.get(name)
        if function is None:
            raise MiniCppExecutionError(f"Function {name!r} is not supported by the interpreter.", "unsupported")
        previous = self.environment
        self.environment = dict(previous)
        parameters = function["parameters"]
        if len(arguments) != len(parameters):
            raise MiniCppExecutionError(f"Function {name!r} received the wrong number of arguments.", "runtime")
        for parameter, argument in zip(parameters, arguments):
            parameter_name = parameter.get("attributes", {}).get("name")
            if isinstance(parameter_name, str) and parameter_name != "<missing>": self.environment[parameter_name] = argument
        try:
            self._execute_statement(function["body"], depth)
        except _ReturnSignal as returned:
            return returned.value
        finally:
            self.environment = previous
        return None

    def _divide(self, left: Any, right: Any) -> Any:
        if right == 0:
            raise MiniCppExecutionError("Division by zero.", "runtime")
        return left / right

    def _decode_string(self, value: str) -> str:
        if len(value) < 2: return value
        body = value[1:-1]
        escapes = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'", "0": "\0"}
        result: list[str] = []
        index = 0
        while index < len(body):
            if body[index] == "\\" and index + 1 < len(body):
                index += 1; result.append(escapes.get(body[index], body[index]))
            else:
                result.append(body[index])
            index += 1
        return "".join(result)


def execute_mini_cpp(tree: dict[str, Any], stdin: str = "") -> MiniCppExecutionOutcome:
    return MiniCppInterpreter(tree, stdin).run()
