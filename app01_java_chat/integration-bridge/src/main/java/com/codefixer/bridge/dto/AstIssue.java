package com.codefixer.bridge.dto;

/**
 * One entry of the {@code issues[]} array in the {@code POST /api/v1/ast/parse} response
 * (CONTRACT.md §5): {@code {"line": 12, "severity": "error"|"warning", "message": "string"}}.
 *
 * Field names already match the contract 1:1 (line, severity, message) so no Jackson
 * {@code @JsonProperty} renaming is needed here.
 */
public record AstIssue(int line, String severity, String message) {

    public static AstIssue error(int line, String message) {
        return new AstIssue(line, "error", message);
    }

    public static AstIssue warning(int line, String message) {
        return new AstIssue(line, "warning", message);
    }
}
