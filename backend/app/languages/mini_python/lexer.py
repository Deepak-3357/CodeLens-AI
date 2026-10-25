from dataclasses import dataclass
from typing import Any


KEYWORDS = {"print", "if", "elif", "else", "while", "for", "in", "is", "def", "return", "break", "continue", "pass", "import", "from", "as", "try", "except", "finally", "raise", "with", "global", "nonlocal", "lambda", "True", "False", "None", "and", "or", "not"}
TWO_CHARACTER_OPERATORS = {"==", "!=", "<=", ">=", "+=", "-=", "*=", "/=", "%=", "**", "//", "<<", ">>"}
ONE_CHARACTER_OPERATORS = {"=", "+", "-", "*", "/", "%", "<", ">", "&", "|", "^", "~"}
DELIMITERS = {"(", ")", ":", ",", ".", "[", "]", "{", "}"}


@dataclass(frozen=True)
class Token:
    type: str
    lexeme: str
    line: int
    column: int
    end_line: int
    end_column: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "lexeme": self.lexeme,
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column,
        }


@dataclass(frozen=True)
class LexicalDiagnostic:
    severity: str
    code: str
    message: str
    line: int | None
    column: int | None
    end_line: int | None
    end_column: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column,
        }


def _token(token_type: str, value: str, line: int, start: int, end: int) -> Token:
    return Token(token_type, value, line, start + 1, line, end + 1)


def _diagnostic(code: str, message: str, line: int, start: int, end: int) -> LexicalDiagnostic:
    return LexicalDiagnostic("error", code, message, line, start + 1, line, end + 1)


def lex(source: str) -> tuple[list[Token], list[LexicalDiagnostic]]:
    """Lex the documented Mini Python subset without executing source text."""
    tokens: list[Token] = []
    diagnostics: list[LexicalDiagnostic] = []
    indent_stack = [0]
    lines = source.splitlines()
    if source and (source.endswith("\n") or source.endswith("\r")):
        lines = source.splitlines()

    last_content_line = 0
    for line_number, raw_line in enumerate(lines, start=1):
        content = raw_line[:-1] if raw_line.endswith("\r") else raw_line
        if not content.strip() or content.lstrip().startswith("#"):
            continue

        leading = len(content) - len(content.lstrip(" \t"))
        prefix = content[:leading]
        if "\t" in prefix:
            diagnostics.append(_diagnostic("PY_INDENT_TAB", "Tabs are not allowed for indentation in Mini Python.", line_number, prefix.index("\t"), leading))
        indent = len(prefix.replace("\t", "    "))
        if indent > indent_stack[-1]:
            indent_stack.append(indent)
            tokens.append(_token("INDENT", prefix, line_number, 0, leading))
        elif indent < indent_stack[-1]:
            while len(indent_stack) > 1 and indent < indent_stack[-1]:
                indent_stack.pop()
                tokens.append(_token("DEDENT", "", line_number, leading, leading))
            if indent != indent_stack[-1]:
                diagnostics.append(_diagnostic("PY_INCONSISTENT_DEDENT", "Dedentation does not match an earlier indentation level.", line_number, 0, leading))
                indent_stack = [0]
                if indent:
                    indent_stack.append(indent)

        index = leading
        line_has_code = False
        while index < len(content):
            character = content[index]
            if character in " \t":
                index += 1
                continue
            if character == "#":
                break
            line_has_code = True
            start = index
            if character.isalpha() or character == "_":
                index += 1
                while index < len(content) and (content[index].isalnum() or content[index] == "_"):
                    index += 1
                value = content[start:index]
                token_type = "KEYWORD" if value in KEYWORDS else "IDENTIFIER"
                tokens.append(_token(token_type, value, line_number, start, index))
                continue
            if character.isdigit():
                index += 1
                while index < len(content) and content[index].isdigit():
                    index += 1
                if index < len(content) and content[index] == ".":
                    index += 1
                    while index < len(content) and content[index].isdigit():
                        index += 1
                    if index == start + 1 or (index < len(content) and content[index] == "."):
                        while index < len(content) and (content[index].isdigit() or content[index] == "."):
                            index += 1
                        diagnostics.append(_diagnostic("PY_MALFORMED_NUMBER", "Malformed numeric literal.", line_number, start, index))
                        tokens.append(_token("INVALID", content[start:index], line_number, start, index))
                        continue
                if index < len(content) and (content[index].isalpha() or content[index] == "_"):
                    while index < len(content) and (content[index].isalnum() or content[index] in "_."):
                        index += 1
                    diagnostics.append(_diagnostic("PY_MALFORMED_NUMBER", "Malformed numeric literal.", line_number, start, index))
                    tokens.append(_token("INVALID", content[start:index], line_number, start, index))
                    continue
                tokens.append(_token("NUMBER", content[start:index], line_number, start, index))
                continue
            if character in "'\"":
                quote = character
                index += 1
                closed = False
                while index < len(content):
                    if content[index] == "\\":
                        index += 2
                        continue
                    if content[index] == quote:
                        index += 1
                        closed = True
                        break
                    index += 1
                if not closed:
                    diagnostics.append(_diagnostic("PY_UNTERMINATED_STRING", "Unterminated string literal.", line_number, start, len(content)))
                    tokens.append(_token("INVALID", content[start:], line_number, start, len(content)))
                    break
                tokens.append(_token("STRING", content[start:index], line_number, start, index))
                continue
            pair = content[index:index + 2]
            if pair in TWO_CHARACTER_OPERATORS:
                index += 2
                tokens.append(_token("OPERATOR", pair, line_number, start, index))
                continue
            if character in ONE_CHARACTER_OPERATORS:
                index += 1
                tokens.append(_token("OPERATOR", character, line_number, start, index))
                continue
            if character in DELIMITERS:
                index += 1
                tokens.append(_token("DELIMITER", character, line_number, start, index))
                continue
            diagnostics.append(_diagnostic("PY_INVALID_CHARACTER", f"Unsupported character {character!r}.", line_number, start, start + 1))
            tokens.append(_token("INVALID", character, line_number, start, start + 1))
            index += 1

        if line_has_code:
            tokens.append(_token("NEWLINE", "", line_number, len(content), len(content)))
            last_content_line = line_number

    if last_content_line and (not tokens or tokens[-1].type != "NEWLINE"):
        tokens.append(_token("NEWLINE", "", last_content_line, 0, 0))
    eof_line = max(len(lines), 1)
    eof_column = len(lines[-1]) if lines else 0
    while len(indent_stack) > 1:
        indent_stack.pop()
        tokens.append(_token("DEDENT", "", eof_line, eof_column, eof_column))
    tokens.append(_token("EOF", "", eof_line, eof_column, eof_column))
    return tokens, diagnostics
