package com.codefixer.bridge.service;

import com.codefixer.bridge.dto.AstIssue;
import com.codefixer.bridge.dto.AstParseResponse;
import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.Problem;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.EnumDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.RecordDeclaration;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Real AST parsing of Java source using JavaParser (com.github.javaparser:javaparser-core) —
 * genuinely walks a {@link CompilationUnit}, not a regex-based approximation.
 *
 * Called by {@link com.codefixer.bridge.controller.AstController}, kept thin per instructions.
 */
@Service
public class AstParserService {

    private final JavaParser javaParser;

    public AstParserService() {
        // Default to a recent Java language level so modern syntax (records, sealed
        // classes, pattern matching, etc.) parses without spurious "unsupported" issues.
        ParserConfiguration configuration =
                new ParserConfiguration().setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_21);
        this.javaParser = new JavaParser(configuration);
    }

    /**
     * Parses a Java source snippet and returns a contract-shaped result.
     *
     * On success, walks the {@link CompilationUnit} to collect real class/interface/enum/
     * record names and method signatures. On failure, every JavaParser {@link Problem} is
     * converted into an {@link AstIssue} with severity "error".
     */
    public AstParseResponse parse(String code) {
        ParseResult<CompilationUnit> result = javaParser.parse(code == null ? "" : code);

        if (!result.isSuccessful() || result.getResult().isEmpty()) {
            List<AstIssue> issues = problemsToIssues(result.getProblems());
            if (issues.isEmpty()) {
                // JavaParser reported failure but with no structured problems (e.g. blank
                // input) — still surface at least one issue rather than an empty array.
                issues.add(AstIssue.error(0, "Unable to parse Java source: no compilation unit produced."));
            }
            return new AstParseResponse(false, issues, List.of(), List.of());
        }

        CompilationUnit unit = result.getResult().get();

        // Non-fatal problems can still be reported alongside a successful parse
        // (JavaParser can recover from some issues); surface them as warnings.
        List<AstIssue> issues = problemsToIssues(result.getProblems()).stream()
                .map(issue -> new AstIssue(issue.line(), "warning", issue.message()))
                .collect(Collectors.toCollection(ArrayList::new));

        List<String> classNames = extractClassNames(unit);
        List<String> methodSignatures = extractMethodSignatures(unit);

        return new AstParseResponse(true, issues, classNames, methodSignatures);
    }

    private List<AstIssue> problemsToIssues(List<Problem> problems) {
        List<AstIssue> issues = new ArrayList<>();
        for (Problem problem : problems) {
            int line = problem.getLocation()
                    .flatMap(com.github.javaparser.TokenRange::toRange)
                    .map(range -> range.begin.line)
                    .orElse(0);
            issues.add(AstIssue.error(line, problem.getVerboseMessage()));
        }
        return issues;
    }

    private List<String> extractClassNames(CompilationUnit unit) {
        List<String> names = new ArrayList<>();
        unit.findAll(ClassOrInterfaceDeclaration.class)
                .forEach(decl -> names.add(decl.getNameAsString()));
        unit.findAll(EnumDeclaration.class)
                .forEach(decl -> names.add(decl.getNameAsString()));
        unit.findAll(RecordDeclaration.class)
                .forEach(decl -> names.add(decl.getNameAsString()));
        return names;
    }

    private List<String> extractMethodSignatures(CompilationUnit unit) {
        List<String> signatures = new ArrayList<>();
        unit.findAll(MethodDeclaration.class)
                .forEach(method -> signatures.add(method.getDeclarationAsString(true, true, true)));
        return signatures;
    }
}
