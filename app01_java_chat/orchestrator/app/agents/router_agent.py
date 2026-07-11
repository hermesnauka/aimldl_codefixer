"""Consulting/Router Agent (§2.2 Agent Topology): detects/confirms the
target language among "python" | "java" | "javascript".

Deliberately NOT an LLM call — deterministic heuristics over code+errorLog
text are faster (US-01: initial response should start quickly, t<1.2s
conceptually) and, for these three languages, reliable enough that an LLM
round-trip would only add latency without meaningfully improving accuracy.

If a language hint is already given and non-null, it is trusted and returned
as-is (confirmed, not re-derived) — the caller (Gateway/user) may already
know it. Otherwise, infer from syntax/error patterns in `code` and
`error_log`. Defaults to "python" if genuinely ambiguous (e.g. empty input),
but only after checking heuristics for the other two.
"""
from __future__ import annotations

import re

_VALID_LANGUAGES = ("python", "java", "javascript")

# Ordered most-specific-first so e.g. Java's "public class" doesn't get
# shadowed by a loose JS heuristic matching unrelated substrings.
_JAVA_CODE_PATTERNS = (
    re.compile(r"\bpublic\s+(final\s+)?class\s+\w+"),
    re.compile(r"\bpublic\s+static\s+void\s+main\s*\("),
    re.compile(r"\bimport\s+java\."),
    re.compile(r"\bSystem\.out\.println\s*\("),
    re.compile(r"\bpackage\s+[\w.]+;"),
    re.compile(r"\bthrows\s+\w+Exception\b"),
)
_JAVA_ERROR_PATTERNS = (
    re.compile(r"Exception in thread"),
    re.compile(r"\bat\s+[\w.$]+\([\w.]+\.java:\d+\)"),
    re.compile(r"java\.lang\.\w+(Exception|Error)"),
)

_PYTHON_CODE_PATTERNS = (
    re.compile(r"^\s*def\s+\w+\s*\(", re.MULTILINE),
    re.compile(r"^\s*import\s+\w+", re.MULTILINE),
    re.compile(r"^\s*from\s+\w+(\.\w+)*\s+import\s+", re.MULTILINE),
    re.compile(r"^\s*class\s+\w+.*:\s*$", re.MULTILINE),
    re.compile(r"\bself\b"),
    re.compile(r"print\s*\("),
)
_PYTHON_ERROR_PATTERNS = (
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"\bFile \"[^\"]+\.py\", line \d+"),
    re.compile(r"\b\w*Error:\s"),  # e.g. "ValueError:", "KeyError:"
)

_JS_CODE_PATTERNS = (
    re.compile(r"\bfunction\s*\w*\s*\("),
    re.compile(r"\bconst\s+\w+\s*="),
    re.compile(r"\blet\s+\w+\s*="),
    re.compile(r"=>\s*{"),
    re.compile(r"\brequire\s*\(['\"]"),
    re.compile(r"\bconsole\.log\s*\("),
    re.compile(r"\bexport\s+(default\s+)?(function|const|class)\b"),
)
_JS_ERROR_PATTERNS = (
    re.compile(r"\bTypeError:\s"),
    re.compile(r"\bReferenceError:\s"),
    re.compile(r"at\s+[\w.<>]+\s+\(.*\.js:\d+:\d+\)"),
    re.compile(r"\bnode:internal"),
    re.compile(r"UnhandledPromiseRejection"),
)


def _score(text: str, patterns: tuple[re.Pattern, ...]) -> int:
    return sum(1 for pattern in patterns if pattern.search(text))


def detect_language(
    *,
    code: str | None,
    error_log: str | None,
    language_hint: str | None = None,
) -> str:
    """Return one of "python" | "java" | "javascript".

    If `language_hint` is already one of the three valid literals, it is
    returned unchanged (pass-through/confirm). Otherwise heuristically
    inferred from `code` and `error_log`. Defaults to "python" if no
    signal is found in either.
    """
    if language_hint and language_hint.strip().lower() in _VALID_LANGUAGES:
        return language_hint.strip().lower()

    combined_code = code or ""
    combined_error = error_log or ""

    java_score = _score(combined_code, _JAVA_CODE_PATTERNS) + _score(
        combined_error, _JAVA_ERROR_PATTERNS
    )
    js_score = _score(combined_code, _JS_CODE_PATTERNS) + _score(
        combined_error, _JS_ERROR_PATTERNS
    )
    python_score = _score(combined_code, _PYTHON_CODE_PATTERNS) + _score(
        combined_error, _PYTHON_ERROR_PATTERNS
    )

    scores = {"python": python_score, "java": java_score, "javascript": js_score}
    best_language, best_score = max(scores.items(), key=lambda item: item[1])

    if best_score == 0:
        # Genuinely ambiguous (e.g. empty input, plain-text-only error log).
        return "python"
    return best_language
