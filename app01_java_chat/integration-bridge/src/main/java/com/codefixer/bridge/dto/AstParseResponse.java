package com.codefixer.bridge.dto;

import java.util.List;

/**
 * Response body for {@code POST /api/v1/ast/parse}, per CONTRACT.md §5:
 *
 * <pre>
 * {
 *   "valid": true,
 *   "issues": [{"line": 12, "severity": "error"|"warning", "message": "string"}],
 *   "classNames": ["string"],
 *   "methodSignatures": ["string"]
 * }
 * </pre>
 *
 * Field names (valid, issues, classNames, methodSignatures) already match the contract's
 * camelCase 1:1 under Jackson's default naming strategy, so no {@code @JsonProperty}
 * overrides are required.
 */
public record AstParseResponse(
        boolean valid,
        List<AstIssue> issues,
        List<String> classNames,
        List<String> methodSignatures
) {
}
