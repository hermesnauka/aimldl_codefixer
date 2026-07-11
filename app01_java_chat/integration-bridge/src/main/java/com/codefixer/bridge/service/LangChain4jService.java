package com.codefixer.bridge.service;

import com.codefixer.bridge.dto.AstIssue;
import dev.langchain4j.model.chat.ChatLanguageModel;
import dev.langchain4j.model.openai.OpenAiChatModel;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.stream.Collectors;

/**
 * Small, real LangChain4j integration: summarizes a list of AST issues into one
 * human-readable sentence via an {@link OpenAiChatModel}, per the ARD's "Java /
 * LangChain4j / Spring Boot" stack for the Integration Bridge.
 *
 * This is secondary enrichment, not the core AST-parsing function (that's
 * {@link AstParserService}), so it must never hard-fail the request: if no
 * {@code OPENAI_API_KEY} is configured, or the LLM call itself fails for any reason
 * (network, rate limit, etc.), this gracefully falls back to a plain concatenation of
 * the issue messages instead of calling any LLM.
 */
@Service
public class LangChain4jService {

    private static final Logger log = LoggerFactory.getLogger(LangChain4jService.class);

    private final ChatLanguageModel chatModel;

    public LangChain4jService(@Value("${codefixer.openai.api-key:}") String apiKey,
                               @Value("${codefixer.openai.model:gpt-4o-mini}") String modelName) {
        if (apiKey != null && !apiKey.isBlank()) {
            this.chatModel = OpenAiChatModel.builder()
                    .apiKey(apiKey)
                    .modelName(modelName)
                    .maxRetries(1)
                    .timeout(java.time.Duration.ofSeconds(10))
                    .build();
        } else {
            this.chatModel = null;
        }
    }

    /**
     * Summarizes the given AST issues into a single human-readable sentence.
     *
     * Returns a plain, non-LLM concatenation when:
     * <ul>
     *   <li>no {@code OPENAI_API_KEY} is configured (this constructor received a blank
     *       key, so {@link #chatModel} is {@code null}), or</li>
     *   <li>the issue list is empty, or</li>
     *   <li>the LLM call throws for any reason (network failure, rate limit, etc.)</li>
     * </ul>
     */
    public String summarizeIssues(List<AstIssue> issues) {
        if (issues == null || issues.isEmpty()) {
            return "No AST issues detected.";
        }

        String plainSummary = plainConcatenation(issues);

        if (chatModel == null) {
            return plainSummary;
        }

        try {
            String prompt = "Summarize the following Java AST parsing issues in one concise, "
                    + "human-readable sentence for a software engineer:\n" + plainSummary;
            return chatModel.generate(prompt);
        } catch (Exception e) {
            log.warn("LangChain4j OpenAI summarization failed, falling back to plain concatenation", e);
            return plainSummary;
        }
    }

    private String plainConcatenation(List<AstIssue> issues) {
        return issues.stream()
                .map(issue -> "[" + issue.severity() + "] line " + issue.line() + ": " + issue.message())
                .collect(Collectors.joining("; "));
    }
}
