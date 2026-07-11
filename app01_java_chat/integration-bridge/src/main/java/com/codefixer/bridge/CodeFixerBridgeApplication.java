package com.codefixer.bridge;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * CodeFixer AI — Enterprise Integration Bridge.
 *
 * Java/Spring Boot service responsible for parsing the Abstract Syntax Tree (AST) of
 * Java source snippets submitted by the Orchestrator (see CONTRACT.md §5). Only ever
 * called when the Orchestrator has detected the submitted code's language as "java".
 */
@SpringBootApplication
public class CodeFixerBridgeApplication {

    public static void main(String[] args) {
        SpringApplication.run(CodeFixerBridgeApplication.class, args);
    }
}
