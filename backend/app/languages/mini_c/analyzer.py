from typing import Any

from .lexer import lex
from .parser import Parser, contains_error
from app.parse_tree import build_parse_tree


GRAMMAR_VERSION = "mini-c-1.0"


def analyze_mini_c(source: str) -> dict[str, Any]:
    tokens, lexical_diagnostics = lex(source)
    parser = Parser(tokens)
    tree = parser.parse()
    diagnostics = [item.as_dict() for item in lexical_diagnostics] + [item.as_dict() for item in parser.diagnostics]
    lexical_valid = not lexical_diagnostics
    syntax_valid = not parser.diagnostics and lexical_valid and tree is not None
    tree_complete = tree is not None and not lexical_diagnostics and not parser.diagnostics and not contains_error(tree)
    parse_status = "valid_complete" if tree_complete else "invalid_partial" if tree is not None else "invalid_no_tree"
    visible_tokens = [token.as_dict() for token in tokens]
    return {
        "language": "mini_c",
        "grammar_version": GRAMMAR_VERSION,
        "lexical_valid": lexical_valid,
        "syntax_valid": syntax_valid,
        "success": lexical_valid and syntax_valid,
        "tokens": visible_tokens,
        "diagnostics": diagnostics,
        "tree": tree,
        "parse_tree": build_parse_tree(tree, tokens, "mini_c"),
        "parse_status": parse_status,
        "tree_complete": tree_complete,
        "summary": {"token_count": len(visible_tokens), "diagnostic_count": len(diagnostics)},
    }
