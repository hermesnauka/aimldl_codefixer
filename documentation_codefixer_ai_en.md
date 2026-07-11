# CodeFixer AI
## Comprehensive Project Documentation: PRD, ARD & SDLC PLAN

This document constitutes the formal technical and functional specification for the **CodeFixer AI** intelligent assistant system, dedicated to advanced debugging, logical analysis, and automatic source code correction. The system utilizes a multi-agent architecture with Large Reasoning Models (LRMs) to ensure the highest precision in resolution reasoning.

---

## 1. PRD (Product Requirements Document)

### 1.1. Goal and Product Vision
**CodeFixer AI** is an advanced engineering chat system designed to minimize the Mean Time to Resolution (MTTR) in the software development lifecycle. The user inputs an encountered programming error and the associated code snippet, and an autonomous AI agent network performs multi-stage reasoning, identifies the optimal solution, and delivers a structurally verified fix after executing sandboxed tests. The system combines institutional design aesthetics with state-of-the-art artificial intelligence paradigms.

### 1.2. Target Audience (Personas)
* **Software Engineer (The Builder):** Focused on operational speed. Requires a precise "here and now" answer without filtering through hundreds of threads on public technical forums. Injects compilation errors or runtime exceptions and expects ready-to-use code with zero regression rate.
* **Architect / Code Auditor (Quality Gatekeeper):** Demands transparency. Requires visibility into the model's reasoning path (Chain-of-Thought) to ensure the proposed patch does not introduce security vulnerabilities and conforms to clean code practices.

### 1.3. Key Features and Requirements
1.  **Conversational LRM Interface:** A chat UI supporting advanced reasoning tokens. Displays the deductive process transparently before presenting the final code output.
2.  **Autonomous Environment Validator (OpenCode Worker):** An execution robot running within an isolated container to test the semantic and syntactic correctness of the generated fix.
3.  **Cascading Model Management (Fallbacks):** Automatic LLM context switching between the primary Hermes 3 model (via the OpenRouter gateway) and backup OpenAI Codex/ChatGPT services in case of network anomalies or rate-limit saturation.
4.  **Institutional Visualization:** User interface designed in strict accordance with the aesthetic canons of the National Bank of Poland (nbp.pl), promoting structural order, authority, and complete digital accessibility.

### 1.4. Specific User Stories

> **US-01: Code Input and Error Analysis**
> * **As a** software developer,
> * **I want to** paste uncompiled source code along with a full stack trace into the chat window,
> * **So that** the system immediately identifies the exact line of code and the root cause of the failure.
> * **Acceptance Criteria:** The system automatically detects the programming language (specifically Python, Java, JavaScript), parses the error log, and the initial response time does not exceed `t < 1.2s`.

> **US-02: Reviewing the Reasoning Flow**
> * **As a** system architect,
> * **I want to** view the complete, expanded thought process of the AI agent (so-called reasoning tokens),
> * **So that** I can understand why a specific fix was deemed optimal in terms of performance and security.
> * **Acceptance Criteria:** The UI provides a dedicated, collapsible panel titled "Agent Reasoning Process", formatted according to the NBP color palette, demonstrating the evaluation and elimination of incorrect hypotheses.

> **US-03: Automated Code Validation by the Worker Agent**
> * **As a** DevOps engineer,
> * **I want** the system-generated code to be automatically tested in an isolated environment by the "OpenCode" worker,
> * **So that** I can be certain the proposed change does not contain syntax or runtime errors.
> * **Acceptance Criteria:** The code is executed within a secure sandbox. The compilation or unit test output (success/failure status) is returned to the chat interface as system metadata.

> **US-04: LLM Provider Failover Resilience**
> * **As a** system maintenance manager,
> * **I want** API requests to be automatically and transparently routed to OpenAI Codex (ChatGPT API) if the OpenRouter (Hermes 3) API becomes unavailable,
> * **So that** the engineering team's workflow remains uninterrupted.
> * **Acceptance Criteria:** Failover switches automatically in the backend layer after two failed connection attempts (timeout `t > 3.0s`), logging the incident into the PostgreSQL database for auditing.

### 1.5. Non-Functional Requirements
* **Performance:** Stream rendering (token-by-token) starts within less than 800 ms from query submission.
* **Security:** Total isolation of the OpenCode execution environment. User code must not access host backend resources or other user sessions.
* **Availability (SLA):** Operational uptime guaranteed at 99.95% on a monthly basis.

### 1.6. Success Criteria and Metrics (KPIs)

| KPI ID | Metric Name | Target Value | Measurement Method |
| :--- | :--- | :--- | :--- |
| **KPI-01** | Fix Accuracy Ratio | > 82% successful compilation on 1st attempt | Automated logs from the OpenCode validator |
| **KPI-02** | Mean Time to Resolution (MTTR) | < 45 seconds for a complete repair loop | Backend telemetry (Node.js Gateway metrics) |
| **KPI-03** | Technical User Retention (Weekly) | > 45% active developers after 4 weeks | Session analytics recorded in the PostgreSQL database |

---

## 2. ARD (Architectural Reference Document)

### 2.1. Polyglot Architecture Concept
To optimize workloads and leverage native technology ecosystems, the system is designed around functional, microservice-oriented components:

| Component / Layer | Core Technology | Architectural Justification and System Role |
| :--- | :--- | :--- |
| **Frontend & User Interface** | `React.js / TypeScript` | Handles dynamic chat state management and Server-Sent Events (SSE) streaming. Styled strictly following the NBP.pl visual identity guidelines. |
| **BFF / Orchestration Gateway** | `Node.js / Express` | Backend-For-Frontend layer. Manages user authentication, session persistence, fast HTTP/WebSocket routing, and asynchronous audit log writing. |
| **Core AI Agent (Orchestrator)** | `Python / LangGraph / LangChain` | The brain of the system responsible for stateful, graph-based multi-agent modeling. Governs reasoning loops, handles conversational memory, and makes LLM routing decisions. |
| **Enterprise Integration Bridge** | `Java / LangChain4j / Spring Boot` | Component responsible for integrating with enterprise code repositories, parsing Abstract Syntax Trees (AST), and securing legacy enterprise connections via strong Java typing. |
| **Database** | `PostgreSQL (v16)` | Relational database ensuring strict ACID compliance. Persists user profiles, chat histories, detailed LLM call logs, and code execution metrics. |

### 2.2. AI Engine and Agent Topology
Reasoning logic is structured into a Directed Acyclic Graph (DAG) managed by `LangGraph`. The architecture distinguishes the following agent roles:
* **Consulting Agent (Router):** Analyzes the incoming user code and routes the request to the appropriate sub-graph depending on the detected programming language.
* **Reasoning Agent:** Utilizes the **Hermes 3 (OpenHermes)** model via **OpenRouter** tokens. This model outputs internal thought tokens, decomposing the bug methodically. If API limits are breached, the `LangChain` abstraction switches queries to **ChatGPT / OpenAI Codex**.
* **Worker Agent (OpenCode Execution Worker):** Utilizes a specialized runtime model/environment to execute the code in a secure sandbox. Returns raw output logs and exit codes back to the Reasoning Agent for an iterative Self-Correction Loop if errors persist.

### 2.3. Visual Identity Guidelines (NBP.pl Styling)
The presentation layer of CodeFixer AI discards generic tech templates in favor of an authoritative, clean design referencing the National Bank of Poland. Composition rules include:
* **Color Palette:** The dominant color is institution deep navy blue (`#002C5B`), symbolizing stability and trust. Highlights, callout borders, and secondary headings use a muted gold (`#B59A57`). The application background adopts a matte cream/light gray tint (`#FCFBFA`).
* **Branding and Layout:** The CodeFixer AI logo is embedded in a geometric, centrally aligned seal with classic serif typography. All data sections, cards, and tables possess thin, distinct borders, mimicking the layout of formal financial and statistical reports.

---

## 3. SDLC PLAN (Project Plan and Schedule)

The project will be executed using the Agile Scrum framework within a rigid 6-month Software Development Lifecycle (SDLC). Each sprint lasts exactly 2 weeks.

### 3.1. Phase 1: Initiation, Design, and Architecture (Months 1-2)
* **Requirements & UX/UI Analysis:** Preparation of full chat interface mockups in Figma, ensuring strict adherence to the NBP.pl color scheme and typography.
* **Infrastructure & Database:** Designing the relational schema in PostgreSQL. Local and dev cluster configuration.
* **Polyglot Skeleton Initialisation:** Setting up a monorepo structure. Bootstrapping basic applications in Node.js (Gateway), Python (LangChain), and Java (LangChain4j).

### 3.2. Phase 2: Implementation Phase and Sprints (Months 3-4)
Iterative development of key system domains across structured sprints:

| Sprint Numbers | Technological Domain | Scope of Work & Key Milestones |
| :--- | :--- | :--- |
| **Sprint 1 - 2** | Infrastructure, Gateway & PostgreSQL | Setting up CI/CD pipelines (GitHub Actions). Implementing auth layer in Node.js. Creating session and auditing tables in PostgreSQL. Applying the NBP layout structure (navy/gold) in the React frontend. |
| **Sprint 3 - 4** | AI Orchestration (Python & LangGraph) | Building the stateful agent graph in Python using LangGraph. Integrating OpenRouter (Hermes 3) and designing the failover abstraction to OpenAI Codex via LangChain. Streaming reasoning tokens to the frontend. |
| **Sprint 5 - 6** | Java Gateway & OpenCode Integration | Implementing the Java microservice using LangChain4j for advanced code structural parsing. Integrating the OpenCode Worker execution pipeline. Closing the agent's Self-Correction Loop. |

### 3.3. Phase 3: Testing and Quality Assurance (Month 5)
* **Unit & Integration Testing:** Achieving a minimum of 85% code coverage for critical logical components in Python and Java.
* **Security Audits (Penetration Testing):** Validating the strict isolation of OpenCode containers against Remote Code Execution (RCE) vulnerabilities.
* **Closed Beta Release:** Launching the platform for a cohort of 500 software engineers to monitor token burn rates, latency, and failover stability.

### 3.4. Phase 4: Production Deployment and Maintenance (Month 6)
* **Environment Deployment (Production Release):** Containerizing the entire system using Docker and deploying it to a Kubernetes cluster.
* **Monitoring & Telemetry:** Connecting Node.js, Python, and Java application logs with Datadog and Firebase Performance to continually track LLM token generation latency.
* **Handover to Operations:** Activating standard support workflows and indexing unrecognized code failure patterns for continuous fine-tuning.
