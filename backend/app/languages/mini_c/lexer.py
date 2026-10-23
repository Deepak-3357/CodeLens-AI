from dataclasses import dataclass
from typing import Any


KEYWORDS = {"int", "float", "double", "char", "bool", "if", "else", "while", "printf", "true", "false"}
TYPE_KEYWORDS = {"int", "float", "double", "char", "bool"}
TWO_CHARACTER_OPERATORS = {"==", "!=", "<=", ">="}
ONE_CHARACTER_OPERATORS = {"=", "+", "-", "*", "/", "%", "<", ">", "!"}
DELIMITERS = {"(", ")", "{", "}", ",", ";"}


@dataclass(frozen=True)
class Token:
    type: str
    lexeme: str
    line: int
    column: int
    end_line: int
    end_column: int

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


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
        return self.__dict__.copy()


def _token(token_type: str, value: str, line: int, column: int, end_column: int) -> Token:
    return Token(token_type, value, line, column, line, end_column)


def _diag(code: str, message: str, line: int, column: int, end_column: int) -> LexicalDiagnostic:
    return LexicalDiagnostic("error", code, message, line, column, line, end_column)


def lex(source: str) -> tuple[list[Token], list[LexicalDiagnostic]]:
    tokens: list[Token] = []
    diagnostics: list[LexicalDiagnostic] = []
    index = 0
    line = 1
    column = 1
    length = len(source)

    def advance() -> str:
        nonlocal index, line, column
        character = source[index]
        index += 1
        if character == "\n":
            line += 1
            column = 1
        else:
            column += 1
        return character

    while index < length:
        character = source[index]
        if character.isspace():
            advance()
            continue
        start_line, start_column = line, column
        if source.startswith("//", index):
            while index < length and source[index] != "\n":
                advance()
            continue
        if source.startswith("/*", index):
            advance(); advance()
            closed = False
            while index < length:
                if source.startswith("*/", index):
                    advance(); advance(); closed = True; break
                advance()
            if not closed:
                diagnostics.append(_diag("C_UNTERMINATED_COMMENT", "Unterminated block comment.", start_line, start_column, column))
            continue
        if character.isalpha() or character == "_":
            value = ""
            while index < length and (source[index].isalnum() or source[index] == "_"):
                value += advance()
            token_type = "KEYWORD" if value in KEYWORDS else "IDENTIFIER"
            tokens.append(_token(token_type, value, start_line, start_column, column))
            continue
        if character.isdigit():
            value = ""
            while index < length and source[index].isdigit():
                value += advance()
            token_type = "NUMBER"
            if index < length and source[index] == ".":
                value += advance()
                while index < length and source[index].isdigit():
                    value += advance()
                token_type = "NUMBER"
            if index < length and (source[index].isalpha() or source[index] == "_" or source[index] == "."):
                while index < length and (source[index].isalnum() or source[index] in "_."):
                    value += advance()
                diagnostics.append(_diag("C_MALFORMED_NUMBER", "Malformed numeric literal.", start_line, start_column, column))
                token_type = "INVALID"
            tokens.append(_token(token_type, value, start_line, start_column, column))
            continue
        if character in "\"'":
            quote = advance()
            value = quote
            closed = False
            while index < length and source[index] != "\n":
                current = advance()
                value += current
                if current == "\\" and index < length:
                    value += advance()
                elif current == quote:
                    closed = True
                    break
            if not closed:
                code = "C_UNTERMINATED_STRING" if quote == '"' else "C_UNTERMINATED_CHARACTER"
                diagnostics.append(_diag(code, "Unterminated string literal." if quote == '"' else "Unterminated character literal.", start_line, start_column, column))
                tokens.append(_token("INVALID", value, start_line, start_column, column))
            else:
                token_type = "STRING" if quote == '"' else "CHARACTER"
                if token_type == "CHARACTER" and len(value[1:-1].replace("\\", "")) != 1:
                    diagnostics.append(_diag("C_INVALID_CHARACTER_LITERAL", "Character literals must contain one character.", start_line, start_column, column))
                    token_type = "INVALID"
                tokens.append(_token(token_type, value, start_line, start_column, column))
            continue
        pair = source[index:index + 2]
        if pair in TWO_CHARACTER_OPERATORS:
            advance(); advance(); tokens.append(_token("OPERATOR", pair, start_line, start_column, column)); continue
        if character in ONE_CHARACTER_OPERATORS:
            advance(); tokens.append(_token("OPERATOR", character, start_line, start_column, column)); continue
        if character in DELIMITERS:
            advance(); tokens.append(_token("DELIMITER", character, start_line, start_column, column)); continue
        diagnostics.append(_diag("C_INVALID_CHARACTER", f"Unsupported character {character!r}.", start_line, start_column, start_column + 1))
        advance()
        tokens.append(_token("INVALID", character, start_line, start_column, column))

    tokens.append(_token("EOF", "", line, column, column))
    return tokens, diagnostics
