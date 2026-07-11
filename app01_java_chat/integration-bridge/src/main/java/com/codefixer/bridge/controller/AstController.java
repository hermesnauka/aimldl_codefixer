package com.codefixer.bridge.controller;

import com.codefixer.bridge.dto.AstParseRequest;
import com.codefixer.bridge.dto.AstParseResponse;
import com.codefixer.bridge.service.AstParserService;
import com.codefixer.bridge.service.LangChain4jService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * {@code POST /api/v1/ast/parse}, per CONTRACT.md §5. Only ever called by the
 * Orchestrator when the detected language is Java. Kept thin: all AST logic lives in
 * {@link AstParserService}, all LLM-enrichment logic lives in {@link LangChain4jService}.
 */
@RestController
public class AstController {

    private static final Logger log = LoggerFactory.getLogger(AstController.class);

    private final AstParserService astParserService;
    private final LangChain4jService langChain4jService;

    public AstController(AstParserService astParserService, LangChain4jService langChain4jService) {
        this.astParserService = astParserService;
        this.langChain4jService = langChain4jService;
    }

    @PostMapping("/api/v1/ast/parse")
    public AstParseResponse parse(@RequestBody AstParseRequest request) {
        AstParseResponse response = astParserService.parse(request.code());

        // Secondary, best-effort enrichment: log a natural-language summary of any
        // issues found. Never allowed to affect the contract-shaped response itself —
        // LangChain4jService already degrades gracefully with no API key configured.
        if (!response.issues().isEmpty()) {
            String summary = langChain4jService.summarizeIssues(response.issues());
            log.info("AST issue summary: {}", summary);
        }

        return response;
    }
}
