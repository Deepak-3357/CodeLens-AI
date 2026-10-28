from dataclasses import dataclass
from typing import Any

KEYWORDS = {
    "int", "short", "long", "float", "double", "char", "bool", "void", "auto",
    "signed", "unsigned", "string", "if", "else", "while", "do", "for", "return",
    "true", "false", "nullptr", "const", "break", "continue", "using", "namespace",
    "std", "cout", "cin", "endl", "class", "template", "new", "delete",
}
TYPE_KEYWORDS = {"int", "short", "long", "float", "double", "char", "bool", "void", "auto", "signed", "unsigned", "string"}
TWO_CHARACTER_OPERATORS = {
    "<<=", ">>=", "==", "!=", "<=", ">=", "++", "--", "+=", "-=", "*=", "/=", "%=",
    "&&", "||", "<<", ">>", "::",
}
ONE_CHARACTER_OPERATORS = {"=", "+", "-", "*", "/", "%", "<", ">", "!", "&", "|", "?"}
DELIMITERS = {"(", ")", "{", "}", "[", "]", ",", ";", ".", ":"}
SUPPORTED_HEADERS = {"iostream", "string", "cmath", "vector"}


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


def _token(token_type: str, lexeme: str, line: int, column: int, end_column: int) -> Token:
    return Token(token_type, lexeme, line, column, line, end_column)


def _diagnostic(code: str, message: str, line: int, column: int, end_column: int) -> LexicalDiagnostic:
    return LexicalDiagnostic("error", code, message, line, column, line, end_column)


def lex(source: str) -> tuple[list[Token], list[LexicalDiagnostic]]:
    tokens: list[Token] = []
    diagnostics: list[LexicalDiagnostic] = []
    index = 0
    line = 1
    column = 1

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

    while index < len(source):
        character = source[index]
        if character.isspace():
            advance()
            continue
        start_line, start_column = line, column
        if source.startswith("//", index):
            while index < len(source) and source[index] != "\n":
                advance()
            continue
        if source.startswith("/*", index):
            advance(); advance()
            closed = False
            while index < len(source):
                if source.startswith("*/", index):
                    advance(); advance(); closed = True; break
                advance()
            if not closed:
                diagnostics.append(_diagnostic("CPP_UNTERMINATED_COMMENT", "Unterminated block comment.", start_line, start_column, column))
            continue
        if character == "#" and source.startswith("#include", index):
            value = ""
            for _ in "#include":
                value += advance()
            while index < len(source) and source[index].isspace() and source[index] != "\n":
                value += advance()
            if index < len(source) and source[index] in '<"':
                closing = ">" if source[index] == "<" else '"'
                value += advance()
                while index < len(source) and source[index] not in {closing, "\n"}:
                    value += advance()
                if index < len(source) and source[index] == closing:
                    value += advance()
            else:
                while index < len(source) and source[index] != "\n":
                    value += advance()
            target = value[len("#include"):].strip()
            header = target[1:-1] if len(target) >= 2 and target[0] in '<"' and target[-1] == (">" if target[0] == "<" else '"') else ""
            if not header:
                diagnostics.append(_diagnostic("CPP_MALFORMED_INCLUDE", "Expected a header name after #include.", start_line, start_column, column))
            elif header not in SUPPORTED_HEADERS:
                diagnostics.append(_diagnostic("CPP_UNSUPPORTED_HEADER", f"Header {header!r} is outside the supported Mini C++ subset.", start_line, start_column, column))
            tokens.append(_token("PREPROCESSOR", value, start_line, start_column, column))
            continue
        if character == "#":
            advance()
            diagnostics.append(_diagnostic("CPP_UNSUPPORTED_PREPROCESSOR", "Only supported #include directives are recognized.", start_line, start_column, column))
            continue
        if character.isalpha() or character == "_":
            value = ""
            while index < len(source) and (source[index].isalnum() or source[index] == "_"):
                value += advance()
            tokens.append(_token("KEYWORD" if value in KEYWORDS else "IDENTIFIER", value, start_line, start_column, column))
            continue
        if character.isdigit():
            value = ""
            while index < len(source) and source[index].isdigit():
                value += advance()
            if index < len(source) and source[index] == ".":
                value += advance()
                while index < len(source) and source[index].isdigit():
                    value += advance()
            if index < len(source) and (source[index].isalpha() or source[index] == "_" or source[index] == "."):
                while index < len(source) and (source[index].isalnum() or source[index] in "_."):
                    value += advance()
                diagnostics.append(_diagnostic("CPP_MALFORMED_NUMBER", "Malformed numeric literal.", start_line, start_column, column))
                tokens.append(_token("INVALID", value, start_line, start_column, column))
            else:
                tokens.append(_token("NUMBER", value, start_line, start_column, column))
            continue
        if character in {'"', "'"}:
            quote = advance()
            value = quote
            closed = False
            while index < len(source) and source[index] != "\n":
                current = advance(); value += current
                if current == "\\" and index < len(source):
                    value += advance()
                elif current == quote:
                    closed = True; break
            if not closed:
                diagnostics.append(_diagnostic("CPP_UNTERMINATED_STRING" if quote == '"' else "CPP_UNTERMINATED_CHARACTER", "Unterminated quoted literal.", start_line, start_column, column))
            elif quote == "'" and len(value) not in {3, 4}:
                diagnostics.append(_diagnostic("CPP_INVALID_CHARACTER_LITERAL", "Character literals must contain one character.", start_line, start_column, column))
            tokens.append(_token("STRING" if quote == '"' else "CHARACTER", value, start_line, start_column, column))
            continue
        matched = next((operator for operator in sorted(TWO_CHARACTER_OPERATORS, key=len, reverse=True) if source.startswith(operator, index)), None)
        if matched:
            for _ in matched:
                advance()
            tokens.append(_token("OPERATOR", matched, start_line, start_column, column))
            continue
        if character in ONE_CHARACTER_OPERATORS:
            advance(); tokens.append(_token("OPERATOR", character, start_line, start_column, column)); continue
        if character in DELIMITERS:
            advance(); tokens.append(_token("DELIMITER", character, start_line, start_column, column)); continue
        advance()
        diagnostics.append(_diagnostic("CPP_INVALID_CHARACTER", f"Unsupported character {character!r}.", start_line, start_column, column))
        tokens.append(_token("INVALID", character, start_line, start_column, column))

    tokens.append(Token("EOF", "", line, column, line, column))
    return tokens, diagnostics
