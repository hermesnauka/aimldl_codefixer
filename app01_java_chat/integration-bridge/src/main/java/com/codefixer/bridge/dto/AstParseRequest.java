package com.codefixer.bridge.dto;

/**
 * Request body for {@code POST /api/v1/ast/parse}, per CONTRACT.md §5.
 *
 * The Orchestrator always sends {@code language: "java"} — this service is only ever
 * invoked for Java snippets — but the field is still accepted here (and simply ignored
 * beyond an optional sanity check) rather than assumed, to match the contract shape
 * {@code { "language": "java", "code": string }} exactly.
 */
public record AstParseRequest(String language, String code) {
}
