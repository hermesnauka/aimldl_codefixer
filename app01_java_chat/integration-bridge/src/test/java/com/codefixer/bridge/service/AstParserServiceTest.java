package com.codefixer.bridge.service;

import com.codefixer.bridge.dto.AstParseResponse;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class AstParserServiceTest {

    private final AstParserService service = new AstParserService();

    @Test
    void parsesValidJavaClassAndExtractsClassNameAndMethodSignatures() {
        String source = """
                package com.example;

                public class Calculator {

                    public int add(int a, int b) {
                        return a + b;
                    }

                    private String describe() {
                        return "calculator";
                    }
                }
                """;

        AstParseResponse response = service.parse(source);

        assertThat(response.valid()).isTrue();
        assertThat(response.issues()).isEmpty();
        assertThat(response.classNames()).containsExactly("Calculator");
        assertThat(response.methodSignatures())
                .anyMatch(sig -> sig.contains("add") && sig.contains("int a") && sig.contains("int b"))
                .anyMatch(sig -> sig.contains("describe"));
    }

    @Test
    void parsesMultipleClassesAndInterfaces() {
        String source = """
                package com.example;

                interface Greeter {
                    String greet(String name);
                }

                class EnglishGreeter implements Greeter {
                    public String greet(String name) {
                        return "Hello, " + name;
                    }
                }
                """;

        AstParseResponse response = service.parse(source);

        assertThat(response.valid()).isTrue();
        assertThat(response.classNames()).containsExactlyInAnyOrder("Greeter", "EnglishGreeter");
        assertThat(response.methodSignatures())
                .anyMatch(sig -> sig.contains("greet"));
    }

    @Test
    void reportsInvalidForSyntacticallyBrokenJava() {
        String brokenSource = """
                package com.example;

                public class Broken {
                    public void doSomething( {
                        int x = ;
                    }
                """; // missing closing paren, invalid expression, missing closing brace

        AstParseResponse response = service.parse(brokenSource);

        assertThat(response.valid()).isFalse();
        assertThat(response.issues()).isNotEmpty();
        assertThat(response.issues()).allMatch(issue -> "error".equals(issue.severity()));
        assertThat(response.classNames()).isEmpty();
        assertThat(response.methodSignatures()).isEmpty();
    }

    @Test
    void reportsInvalidForEmptyGarbageInput() {
        AstParseResponse response = service.parse("this is not java code at all {{{ }}} ???");

        assertThat(response.valid()).isFalse();
        assertThat(response.issues()).isNotEmpty();
    }
}
