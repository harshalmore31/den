# Den Loop Architecture

> **Status:** Implementation-ready specification
> **Version:** 1.0
> **Companion document:** `architecture.md` — read that first for system context
> **Last updated:** 2026-03-25

---

## Table of Contents

1. [Philosophy — Why Loops Are the Core Primitive](#1-philosophy--why-loops-are-the-core-primitive)
2. [The Four Standard Loop Types](#2-the-four-standard-loop-types)
3. [Loop Primitives — The Building Blocks](#3-loop-primitives--the-building-blocks)
4. [The Evaluation System](#4-the-evaluation-system)
5. [Phase Composition — Chaining Loops](#5-phase-composition--chaining-loops)
6. [Agentfile Spec for Loops](#6-agentfile-spec-for-loops)
7. [Built-in Checks Library](#7-built-in-checks-library)
8. [Custom Loop Design Guide](#8-custom-loop-design-guide)
9. [Loop Engine Implementation](#9-loop-engine-implementation)
10. [Real-World Examples](#10-real-world-examples)

---

## 1. Philosophy — Why Loops Are the Core Primitive

### Single-Shot Execution Is Broken

Every AI tool in production today — ChatGPT, Claude, Copilot, Cursor — operates on the same broken model:

```
User sends input
    |
    v
LLM generates output
    |
    v
Output delivered to user
    (done)
```

This is a single-shot system. The agent gets one attempt. If the output is incomplete, wrong, or low quality, you get what you got. The only correction mechanism available is human review followed by another manual prompt.

This works fine for short questions with objectively correct answers. It fails systematically for any task with structure, length, or quality requirements. And it fails completely for autonomous work — work that happens without a human watching.

The consequences are documented in every AI deployment story:

- Reports that are "technically complete" but miss obvious requirements
- Code that compiles but fails tests because no test was actually run
- Research that cites no sources because no one checked for source citations
- Plans that skip risk sections because no one verified sections existed
- Summaries that are 200 words when 800 were required

The root cause is not model capability. These are not model failures. They are architectural failures. A better model in a single-shot architecture produces better single shots. It does not produce verified outputs.

### What Real-World Workflows Actually Look Like

When a skilled professional uses an AI tool for real work, they do not accept the first output. They follow a pattern:

**Discovery.** They ask questions. They research. They identify what they do not know. They gather information until they have enough to proceed. They do not jump to conclusions.

**Planning.** They draft a plan. They review it against requirements. They revise. They confirm it is complete before executing.

**Execution.** They do the work. They check their work against the plan. They fix what does not match. They iterate until the work matches the intent.

**Verification.** They review the final output against the original requirements. They run tests. They check completeness. They sign off.

This is not a linear one-pass flow. It is a series of loops, each one with entry criteria and exit criteria. Humans do this intuitively. AI agents need it built in.

### Den's Answer: Loops as First-Class Architecture

Den's Loop Architecture takes this natural workflow structure and makes it explicit, configurable, and automatic.

A Den agent does not run a task once and return output. It runs a task through a sequence of defined phases. Each phase is a loop. Each loop has:

- A set of questions or checks to satisfy
- An evaluation method that determines pass or fail
- A maximum iteration budget
- Feedback generation on failure
- Transition conditions that move to the next phase

The result is an agent that works the way a good professional works — not just generating output, but verifying it, correcting it, and confirming it before delivering.

This is the difference between a system that produces output and one that produces verified output. It is the difference between a chatbot and an agent.

### The Design Principles

**Loops are not retry logic.** Retry logic repeats the same thing after a transient failure. Loops refine the approach using structured feedback from each failed attempt. Iteration N+1 is informed by what was wrong with iteration N.

**Evaluation must be algorithmic.** "Ask the LLM if it's good" is not a reliable quality gate. It is circular: you are asking the system that produced the output to judge the output. Algorithmic checks — word count, section detection, URL presence, schema validation, test results — are objective and cannot be gamed by the generating model.

**Phases compose.** A discovery loop's output becomes a planning loop's input. A planning loop's output becomes an execution loop's input. The output of each phase is structured data that flows cleanly to the next phase.

**Loops must be teachable.** Every developer building on Den should be able to define their own loop architectures in the Agentfile. The system ships with four standard types as building blocks, but the primitives are open and composable.

**Failure is information.** A failed iteration is not wasted work. The feedback from a failed evaluation is richer context for the next attempt. Failed attempts are logged to memory. Future runs can learn from past failures.

---

## 2. The Four Standard Loop Types

Den ships with four standard loop types that cover the canonical phases of autonomous work. Each is a specialization of the same underlying loop primitive with defaults suited to its purpose.

### 2.1 Research Loop

The Research Loop answers a defined set of questions. It terminates when all questions have substantive, sourced answers.

```
+---------------------------------------------+
|              RESEARCH LOOP                  |
+---------------------------------------------+
|                                             |
|   Input: question_list                      |
|                                             |
|   +---------------------------------------+ |
|   | Iteration N                           | |
|   |                                       | |
|   |   For each question in list:          | |
|   |     - Search for information          | |
|   |     - Synthesize findings             | |
|   |     - Record answer with sources      | |
|   |                                       | |
|   +---------------------------------------+ |
|                   |                         |
|                   v                         |
|   +---------------------------------------+ |
|   | Algorithmic Evaluation                | |
|   |                                       | |
|   |   For each question:                  | |
|   |     - answer_present: bool            | |
|   |     - sources_present: bool           | |
|   |     - min_word_count: int             | |
|   |     - all_questions_addressed: bool   | |
|   |                                       | |
|   +---------------------------------------+ |
|                   |                         |
|         +---------+---------+               |
|         |                   |               |
|      FAILED              PASSED             |
|         |                   |               |
|         v                   v               |
|   Generate feedback    Output: answers{}    |
|   (which questions     (structured dict     |
|    are incomplete,      keyed by question)  |
|    which lack sources)                      |
|         |                                   |
|    N < max_iter?                            |
|         |                                   |
|    Yes: retry with feedback                 |
|    No:  on_fail behavior                    |
+---------------------------------------------+

Output schema:
{
  "answers": {
    "<question>": {
      "answer": "<text>",
      "sources": ["<url>", ...],
      "word_count": <int>,
      "confidence": "high|medium|low"
    }
  },
  "unanswered": ["<question>", ...],
  "total_sources": <int>
}
```

**When to use:** Any task that begins with uncertainty. Research before building. Competitive analysis before designing. Due diligence before deciding. Market research before planning.

**Key insight:** The Research Loop does not produce a document. It produces a structured answers object. This object becomes the input to the Planning Loop.

### 2.2 Plan Loop

The Plan Loop produces a structured plan that satisfies a defined set of structural requirements. It terminates when the plan passes all checks.

```
+---------------------------------------------+
|               PLAN LOOP                     |
+---------------------------------------------+
|                                             |
|   Input: context (from Research Loop        |
|          or direct task description)        |
|                                             |
|   +---------------------------------------+ |
|   | Iteration N                           | |
|   |                                       | |
|   |   Generate plan addressing:           | |
|   |     - implementation steps            | |
|   |     - files/resources to create       | |
|   |     - risks and mitigations           | |
|   |     - success criteria                | |
|   |                                       | |
|   +---------------------------------------+ |
|                   |                         |
|                   v                         |
|   +---------------------------------------+ |
|   | Evaluation (algorithmic + optional    | |
|   | user approval gate)                   | |
|   |                                       | |
|   |   - has_required_sections: bool       | |
|   |   - min_steps: int                    | |
|   |   - risks_present: bool               | |
|   |   - success_criteria_present: bool    | |
|   |   - [approval: user | auto | skip]    | |
|   |                                       | |
|   +---------------------------------------+ |
|                   |                         |
|         +---------+---------+               |
|         |                   |               |
|      FAILED              PASSED             |
|         |                   |               |
|         v                   v               |
|   Generate feedback    Output: plan{}       |
|   (which sections       (structured plan   |
|    are missing,          with steps array, |
|    which are thin)       risks, criteria)   |
|         |                                   |
|    N < max_iter?                            |
|         |                                   |
|    Yes: retry with feedback                 |
|    No:  on_fail behavior                    |
+---------------------------------------------+

Output schema:
{
  "plan": {
    "objective": "<string>",
    "steps": [
      {
        "id": <int>,
        "action": "<string>",
        "files_affected": ["<path>", ...],
        "expected_output": "<string>"
      }
    ],
    "risks": [
      {
        "risk": "<string>",
        "mitigation": "<string>",
        "severity": "high|medium|low"
      }
    ],
    "success_criteria": ["<string>", ...],
    "estimated_duration": "<string>"
  }
}
```

**When to use:** Any task where execution order matters, where there are multiple files or resources to create, or where mistakes are expensive to undo. Software features, content strategies, data migrations, infrastructure changes.

**User approval gate:** The Plan Loop supports an optional human checkpoint. When `approval: user` is set, the loop pauses after the plan passes algorithmic checks and waits for explicit approval before transitioning to execution. This is the human-in-the-loop control point in an otherwise autonomous workflow.

### 2.3 Execution Loop

The Execution Loop implements a plan and verifies the implementation against the plan's stated objectives. It terminates when the implementation passes all verification checks.

```
+---------------------------------------------+
|             EXECUTION LOOP                  |
+---------------------------------------------+
|                                             |
|   Input: plan{} (from Plan Loop)            |
|                                             |
|   +---------------------------------------+ |
|   | Iteration N                           | |
|   |                                       | |
|   |   For each step in plan.steps:        | |
|   |     - Execute the step                | |
|   |     - Verify step output exists       | |
|   |     - Continue to next step           | |
|   |                                       | |
|   |   Self-review:                        | |
|   |     - Compare output to plan          | |
|   |     - Identify gaps                   | |
|   |                                       | |
|   +---------------------------------------+ |
|                   |                         |
|                   v                         |
|   +---------------------------------------+ |
|   | Evaluation (script-based preferred)   | |
|   |                                       | |
|   |   - artifacts_exist: bool             | |
|   |   - tests_pass: bool (if script)      | |
|   |   - schema_valid: bool (if schema)    | |
|   |   - no_placeholder_text: bool         | |
|   |   - all_steps_completed: bool         | |
|   |                                       | |
|   +---------------------------------------+ |
|                   |                         |
|         +---------+---------+               |
|         |                   |               |
|      FAILED              PASSED             |
|         |                   |               |
|         v                   v               |
|   Generate feedback    Output: artifacts[]  |
|   (which steps failed,  (paths to produced  |
|    which tests failed,   files and results) |
|    what output is        + execution_log{}  |
|    missing)                                 |
|         |                                   |
|    N < max_iter?                            |
|         |                                   |
|    Yes: retry with feedback                 |
|    No:  on_fail behavior                    |
+---------------------------------------------+
```

**When to use:** After a plan is approved. Any task that produces artifacts — code files, documents, data files, configuration. The Execution Loop's distinguishing feature is that it runs external verification scripts, not just self-assessment.

**Script evaluators are the right default here.** If code was written, run the tests. If a document was written, check the schema. If data was processed, validate the output. Do not ask the agent whether it did the work correctly — run the checker.

### 2.4 Verification Loop

The Verification Loop compares final output against the original requirements. It is the final gate before an artifact is delivered. It terminates when the output satisfies all stated requirements.

```
+---------------------------------------------+
|           VERIFICATION LOOP                 |
+---------------------------------------------+
|                                             |
|   Input: artifacts[] (from Execution Loop)  |
|          original_requirements{}            |
|                                             |
|   +---------------------------------------+ |
|   | Iteration N                           | |
|   |                                       | |
|   |   Load all produced artifacts         | |
|   |   Load original requirements          | |
|   |   Systematically check each           | |
|   |   requirement against artifacts       | |
|   |                                       | |
|   +---------------------------------------+ |
|                   |                         |
|                   v                         |
|   +---------------------------------------+ |
|   | Evaluation (hybrid recommended)       | |
|   |                                       | |
|   |   Algorithmic:                        | |
|   |     - all_required_files_present      | |
|   |     - tests_pass                      | |
|   |     - no_todo_comments                | |
|   |     - schema_valid                    | |
|   |                                       | |
|   |   LLM judge:                          | |
|   |     - matches_original_intent         | |
|   |     - edge_cases_handled              | |
|   |     - completeness_score >= threshold | |
|   |                                       | |
|   +---------------------------------------+ |
|                   |                         |
|         +---------+---------+               |
|         |                   |               |
|      FAILED              PASSED             |
|         |                   |               |
|         v                   v               |
|   Generate feedback    DELIVER artifacts    |
|   (specific gaps vs.   Write success to    |
|    requirements)       memory              |
|    Loop back to                             |
|    Execution phase                          |
|    if needed                                |
+---------------------------------------------+
```

**When to use:** As the final phase of any multi-phase workflow. As a standalone loop when you have existing artifacts that need to be validated against requirements. As a quality gate in CI/CD-style automation.

**The verification loop can loop back.** If verification fails badly enough, it should trigger a return to the Execution Loop with structured feedback about what failed. This is the `on_fail: goto` mechanism described in Section 3.

---

## 3. Loop Primitives — The Building Blocks

All loop types, including custom ones, are composed from the same set of primitives. Understanding these primitives lets you design any loop pattern.

### 3.1 Question Set

A named list of questions or requirements that the loop must satisfy. The loop's job is to answer every question or satisfy every requirement in the set.

```yaml
questions:
  - id: competitors
    text: "What existing solutions address this problem?"
    required: true

  - id: tech_stack
    text: "What technology stack is best suited for this?"
    required: true

  - id: risks
    text: "What are the top three risks of this approach?"
    required: true

  - id: timeline
    text: "What is a realistic delivery timeline?"
    required: false  # Loop passes even if this one is unanswered
```

Questions can be `required: true` (default) or `required: false`. A loop passes when all required questions are answered. Optional questions are attempted but do not block progression.

### 3.2 Checks

Checks are individual pass/fail tests applied to loop output. Each check has:

- A name (unique within the loop)
- A type (from the Built-in Checks Library or a custom evaluator)
- Parameters specific to the check type
- A `required` flag (whether failure blocks the loop)
- A `weight` (used in scoring when partial passes are configured)

```yaml
checks:
  - name: has_source_urls
    type: sources_present
    min_count: 3
    required: true
    weight: 1.0

  - name: adequate_length
    type: min_word_count
    min_words: 500
    required: true
    weight: 1.0

  - name: no_placeholders
    type: no_placeholder_text
    required: true
    weight: 1.0

  - name: has_conclusion
    type: section_present
    section_names: ["conclusion", "summary", "next steps"]
    required: false
    weight: 0.5
```

### 3.3 Evaluators

Evaluators run the checks and produce an `EvaluationResult`. There are three evaluator methods:

**algorithmic** — Pure code evaluation. Runs checks as deterministic functions against the output. No LLM call. Fast, cheap, objective, repeatable.

**self-judge** — The generating agent evaluates its own output using a structured prompt that enforces JSON output. Use only for checks that cannot be expressed algorithmically (tone, coherence, intent matching). Cheap in tokens, but subject to self-serving bias.

**hybrid** — Algorithmic checks first. If all algorithmic checks pass, optionally run self-judge or llm-judge for qualitative criteria. The recommended default for most loops.

**script** — An external script evaluates output. The script receives output path via environment variable, exits 0 for pass, non-zero for fail, and writes feedback to stdout. Use for test runners, validators, linters, and custom business logic.

**llm-judge** — An independent LLM call (not the generating agent) evaluates the output. Use for subjective quality judgments where self-serving bias would be a problem. More expensive but more objective.

### 3.4 Gates

Gates are synchronization points within a loop or phase sequence. A gate pauses execution until a condition is met externally.

```yaml
gates:
  - type: user_approval
    timeout: 48h        # Wait up to 48 hours for approval
    on_timeout: fail    # fail | proceed | notify
    notify_via: file    # Write a notification file to /den/output/pending/

  - type: time_window
    window: "09:00-17:00"  # Only proceed during business hours
    timezone: "America/New_York"

  - type: external_check
    script: ./scripts/check-deployment-ready.sh
    poll_interval: 60s
    max_wait: 4h
```

Gates are optional. Most loops do not need them. They exist for workflows where human review is part of the process (user approval gate) or where external dependencies must be satisfied before proceeding (waiting for a deployment to complete before verifying it).

### 3.5 Transitions

Transitions define what happens when a loop completes — either by passing or by exhausting iterations.

```yaml
transitions:
  on_pass:
    goto: next_phase    # Advance to the next phase in the sequence
    pass_data:          # Fields from this phase's output to forward
      - answers
      - sources_count

  on_fail:
    behavior: notify    # notify | stop | retry | goto
    goto: discovery     # If behavior: goto, which phase to return to
    max_retries: 2      # How many times this transition can loop back
    notify_message: |
      Execution phase failed after {iterations} iterations.
      See /den/output/failure-report.md for details.
```

Transitions make phases composable. The output of one phase becomes input to the next, or execution returns to an earlier phase when something goes wrong.

### 3.6 Feedback Generator

When a loop iteration fails, the feedback generator produces structured feedback for the next iteration. The feedback explains what failed and what the next attempt should do differently.

The feedback generator is not configurable in v1 — it is built into the Loop Engine. It takes the evaluation result (which checks failed, why they failed) and produces a structured message that is prepended to the task context for the next iteration.

```
Iteration 2 did not pass evaluation.
Overall score: 0.60 (3/5 checks passed)

The following checks failed:

  - has_source_urls: Found 1 URL but minimum 3 required.
    Action: Search for more authoritative sources.
    Suggestion: Use web_search with more specific queries.

  - min_word_count: Output was 312 words, minimum is 500.
    Action: Expand each answer with more detail and context.

Do not repeat the approach that just failed.
Address these specific gaps in your next attempt.
```

The feedback message is concrete and actionable. "Your output was insufficient" is not useful feedback. "Your output had 312 words and requires 500, and cited 1 source where 3 are required" is.

---

## 4. The Evaluation System

The evaluation system is where Den's quality guarantees come from. This section specifies exactly how each evaluation method works, how checks are applied, and how scores are calculated.

### 4.1 Algorithmic Evaluation

Algorithmic evaluation applies deterministic functions to the output. These functions are implemented in Python, run in the Den Core process (not in the agent's sandbox), and produce binary pass/fail results with reasons.

```
                    Output (text, file path, or JSON)
                              |
                              v
                    +-------------------+
                    | Check Runner      |
                    +-------------------+
                              |
                    +---------+---------+
                    |         |         |
               Check 1    Check 2    Check 3
               (pass)     (FAIL)     (pass)
                    |         |         |
                    +---------+---------+
                              |
                              v
                    +-------------------+
                    | Score Calculator  |
                    |                   |
                    | score = sum of    |
                    |   passed check    |
                    |   weights /       |
                    |   total weights   |
                    |                   |
                    | passed = all      |
                    |   required checks |
                    |   passed          |
                    +-------------------+
                              |
                              v
                    EvaluationResult{
                      passed: bool,
                      score: float,
                      criteria_results: [...],
                      feedback: str
                    }
```

**Scoring:**

The overall score is the weighted fraction of checks that passed:

```
score = sum(weight for check in passed_checks) / sum(weight for check in all_checks)
```

The overall `passed` boolean is independent of score. A loop passes only when all `required: true` checks pass. A high score with one required check failed is still a failure.

**Why this matters:** Score gives you visibility into how close an iteration came to passing. An iteration that scored 0.9 (4/5 checks) is much closer to passing than one that scored 0.4 (2/5 checks). The Loop Engine uses score trends to detect when the agent is making progress.

### 4.2 Self-Judge Evaluation

Self-judge evaluation uses a structured prompt to ask the generating agent to evaluate its own output.

The self-judge evaluator is appropriate for checks that are:
- Structural but not trivially countable (does the plan have a clear logical flow?)
- Semantic (does the summary accurately capture the main points?)
- Stylistic with clear criteria (is the tone professional and direct?)

It is NOT appropriate for:
- Checks that can be counted or measured algorithmically
- Checks where self-serving bias would inflate scores (the agent will be tempted to pass itself)
- Checks that require external ground truth (did the code pass tests?)

**Self-judge prompt template:**

```
You are evaluating your own work against specific criteria.
Be rigorous. Your goal is accurate assessment, not self-approval.

WORK TO EVALUATE:
{output}

EVALUATION CRITERIA:
{criteria_list}

For each criterion, determine whether it PASSED or FAILED.
If FAILED, explain precisely what is missing or wrong.
Be specific — "needs more detail" is not useful. "The risks section
lists 1 risk but requires 3" is useful.

Return ONLY valid JSON matching this schema:
{
  "criteria_results": [
    {
      "criterion": "<criterion text>",
      "passed": true | false,
      "reason": "<precise explanation if failed, empty string if passed>"
    }
  ],
  "overall_score": <0.0 to 1.0>,
  "overall_passed": true | false
}
```

The prompt enforces JSON output. The Loop Engine parses this JSON, validates the schema, and rejects malformed responses (treating them as failures).

### 4.3 LLM Judge Evaluation

LLM judge evaluation makes an independent LLM API call — separate from the generating agent — to evaluate output quality. The judge is given no system prompt that would bias it toward the agent's approach.

This evaluator is appropriate for:
- Subjective quality judgments (is this report well-written?)
- Cross-checking for completeness (does this implementation match the requirements document?)
- Detecting reasoning errors that the generating model is unlikely to catch in self-review

**LLM judge prompt template:**

```
You are an independent quality reviewer. You have no relationship
to the system that produced this work. Your job is rigorous,
honest evaluation.

Do not pass work that only partially satisfies criteria.
Partial completion is failure. Vague answers are failure.
Placeholders are failure.

WORK TO EVALUATE:
{output}

EVALUATION CRITERIA:
{criteria_list}

ORIGINAL REQUIREMENTS (for context):
{original_requirements}

Return ONLY valid JSON:
{
  "criteria_results": [
    {
      "criterion": "<criterion text>",
      "passed": true | false,
      "reason": "<precise explanation>"
    }
  ],
  "overall_score": <0.0 to 1.0>,
  "overall_passed": true | false,
  "summary": "<one sentence overall assessment>",
  "critical_gaps": ["<gap>", ...]
}
```

**Cost considerations:** LLM judge adds an extra API call per iteration. Use it only when self-assessment would be unreliable (subjective quality) or when the stakes justify the cost (final verification of important deliverables).

### 4.4 Script Evaluation

Script evaluation runs an external process and uses the exit code as pass/fail signal. This is the right default for any check that can be expressed as a program.

```
Agent output written to /den/workspace/output/
              |
              v
Script invoked with:
  DEN_OUTPUT_PATH=/den/workspace/output/result.md
  DEN_TASK_NAME=build-feature
  DEN_ITERATION=2
              |
              v
Script logic:
  - Load output file
  - Run tests / validators / linters
  - Check schemas
  - Compare against reference data
  - Write feedback to stdout
  - Exit 0 (pass) or non-zero (fail)
              |
              v
EvaluationResult{
  passed: (exit_code == 0),
  score: 1.0 | 0.0,
  feedback: stdout,
  method_used: "script"
}
```

**Script contract:**

- The script is responsible for all evaluation logic
- It receives output location via environment variable `DEN_OUTPUT_PATH`
- It MUST exit 0 for pass, non-zero for fail
- Feedback written to stdout is captured and used in the next iteration's context
- The script runs inside the agent's sandbox with the same permissions
- Timeout: 120 seconds (configurable via `evaluation.script_timeout`)

**Common script patterns:**

```bash
#!/bin/bash
# Test runner script
cd /den/workspace
python -m pytest tests/ -v --tb=short 2>&1
exit $?
```

```bash
#!/bin/bash
# Schema validator
python -c "
import json, sys
with open('$DEN_OUTPUT_PATH') as f:
    data = json.load(f)
required_keys = ['title', 'summary', 'sections', 'sources']
missing = [k for k in required_keys if k not in data]
if missing:
    print(f'Missing required keys: {missing}')
    sys.exit(1)
print('Schema valid')
sys.exit(0)
"
```

```bash
#!/bin/bash
# Word count check
WORDS=$(wc -w < "$DEN_OUTPUT_PATH")
if [ "$WORDS" -lt 500 ]; then
    echo "Word count: $WORDS (minimum: 500)"
    exit 1
fi
echo "Word count: $WORDS (passed)"
exit 0
```

### 4.5 Hybrid Evaluation

Hybrid evaluation is the recommended default for most loops. It runs algorithmic checks first (fast, cheap, objective) and optionally adds self-judge or llm-judge for qualitative criteria that cannot be expressed algorithmically.

```yaml
evaluation:
  method: hybrid
  algorithmic_checks:
    - name: word_count
      type: min_word_count
      min_words: 800
    - name: has_sources
      type: sources_present
      min_count: 3
    - name: no_placeholders
      type: no_placeholder_text
  qualitative_checks:
    method: llm-judge
    criteria:
      - "Analysis is logically coherent and conclusions follow from evidence"
      - "Tone is appropriate for a professional audience"
    # Qualitative checks only run if all algorithmic checks pass
    # This saves cost — no point paying for LLM judging if basic checks fail
    run_if_algorithmic_passes: true
```

The `run_if_algorithmic_passes: true` flag is important. There is no value in running an expensive LLM judge on output that fails a word count check. Run cheap checks first, expensive checks only when cheap checks pass.

---

## 5. Phase Composition — Chaining Loops

### 5.1 How Phases Chain

A task in the Agentfile can define a `phases` array. Each phase is a loop. Phases execute sequentially. The output of each phase is passed as structured input to the next phase.

```
+------------------+
|   Task Triggered |
+------------------+
         |
         v
+------------------+
|  Phase 1:        |
|  Research Loop   |
|                  |
|  [loop until     |
|   all questions  |
|   answered]      |
+------------------+
         |
         | Output: answers{}
         v
+------------------+
|  Phase 2:        |
|  Plan Loop       |
|                  |
|  Input: answers  |
|                  |
|  [loop until     |
|   plan passes    |
|   checks]        |
+------------------+
         |
         | Output: plan{}
         v
+------------------+
|  Phase 3:        |
|  Execution Loop  |
|                  |
|  Input: plan     |
|                  |
|  [loop until     |
|   artifacts pass |
|   checks]        |
+------------------+
         |
         | Output: artifacts[]
         v
+------------------+
|  Phase 4:        |
|  Verification    |
|  Loop            |
|                  |
|  Input: artifacts|
|  + requirements  |
|                  |
|  [loop until     |
|   verification   |
|   passes]        |
+------------------+
         |
         v
  DELIVER artifacts
  Write to memory
```

### 5.2 Data Flow Between Phases

Each phase produces a structured output object. This object is serialized to `/den/workspace/phases/{phase_name}/output.json` and passed to the next phase as part of its context.

**Phase context format:**

```json
{
  "task_name": "build-feature",
  "current_phase": "planning",
  "phases_completed": ["discovery"],
  "phase_outputs": {
    "discovery": {
      "answers": {
        "competitors": {
          "answer": "...",
          "sources": ["https://...", "https://..."],
          "word_count": 312
        }
      },
      "total_sources": 7,
      "iterations_used": 2
    }
  },
  "original_requirements": "...",
  "phase_feedback": null
}
```

The agent sees this as part of its task context at the start of each phase iteration. It knows what phases preceded it, what was found, and what it needs to produce for the current phase.

### 5.3 Phase Transitions

Transitions define the control flow between phases.

**Normal transition (phase passes):**

```yaml
transitions:
  on_pass:
    goto: next   # Advance to the next phase in the phases array
```

**Jump transition (skip a phase):**

```yaml
transitions:
  on_pass:
    goto: verification   # Skip execution, go directly to verification
    condition: "phase_outputs.discovery.confidence == 'high'"
```

**Loop-back transition (phase fails severely):**

```yaml
transitions:
  on_fail:
    behavior: goto
    goto: discovery   # Return to an earlier phase for more research
    max_retries: 1    # Only allow this loop-back once
    feedback: |
      Execution failed validation. Return to discovery to re-examine
      the approach before attempting implementation again.
```

**Stop transition (fail the whole task):**

```yaml
transitions:
  on_fail:
    behavior: stop
    notify: true
    write_failure_report: /den/output/failure-{timestamp}.md
```

### 5.4 Phase State and Resumption

Each phase writes its state to disk as it progresses. If the agent is restarted mid-task (due to container restart, `den down`/`den up`, or an unhandled error), the Loop Engine reads the persisted phase state and resumes from where it left off.

```
/den/workspace/tasks/{task-name}-{timestamp}/
├── phase_discovery/
│   ├── status.json          # COMPLETED | IN_PROGRESS | FAILED
│   ├── output.json          # Phase output (if completed)
│   ├── iterations/
│   │   ├── 1.json           # Iteration 1 record
│   │   └── 2.json           # Iteration 2 record
│   └── final_feedback.txt   # Feedback that led to pass
├── phase_planning/
│   ├── status.json          # COMPLETED
│   ├── output.json
│   └── iterations/
│       └── 1.json
├── phase_implementation/
│   ├── status.json          # IN_PROGRESS — resume here
│   └── iterations/
│       └── 1.json           # Partial record
└── task_manifest.json       # Overall task state
```

Phase resumption means a multi-phase task that runs for hours does not need to restart from scratch if interrupted. Completed phases are not re-run.

---

## 6. Agentfile Spec for Loops

### 6.1 Single-Phase Loop (the existing spec, extended)

Single-phase loops use the existing `loop:` field in a task. This is the v1 loop model and remains fully supported.

```yaml
tasks:
  generate-report:
    description: |
      Generate a weekly market analysis report covering...

    loop:
      max_iterations: 5
      evaluation:
        method: hybrid
        algorithmic_checks:
          - name: word_count
            type: min_word_count
            min_words: 1000
          - name: has_sources
            type: sources_present
            min_count: 5
          - name: has_sections
            type: sections_present
            required_sections: ["executive_summary", "analysis", "conclusion"]
          - name: no_placeholders
            type: no_placeholder_text
        qualitative_checks:
          method: self-judge
          criteria:
            - "Report is well-organized with clear section headers"
            - "Analysis draws actionable conclusions from the data"
          run_if_algorithmic_passes: true
      on_fail: notify
      cooldown: 30s
```

### 6.2 Multi-Phase Loop (the new phases spec)

Multi-phase loops use the `phases:` array within a task. Each phase is a complete loop definition.

```yaml
tasks:
  build-feature:
    description: |
      Build a new feature based on the user's request.
      Follow the full discovery → planning → implementation → verification flow.

    phases:
      # --------------------------------------------------------
      # Phase 1: Discovery
      # --------------------------------------------------------
      - name: discovery
        type: research
        questions:
          - id: existing_solutions
            text: "Are there existing libraries or tools that solve this?"
            required: true
          - id: technical_approach
            text: "What is the best technical approach for this feature?"
            required: true
          - id: risks
            text: "What are the main implementation risks?"
            required: true
          - id: test_strategy
            text: "How should this feature be tested?"
            required: false
        evaluation:
          method: algorithmic
          checks:
            - name: all_questions_answered
              type: all_questions_addressed
              required: true
            - name: has_sources
              type: sources_present
              min_count: 2
              required: false
            - name: answer_depth
              type: min_word_count
              min_words: 300    # Total across all answers
              required: true
        max_iterations: 3
        cooldown: 10s
        transitions:
          on_pass:
            goto: next
          on_fail:
            behavior: stop

      # --------------------------------------------------------
      # Phase 2: Planning
      # --------------------------------------------------------
      - name: planning
        type: plan
        input_from: discovery   # Receives discovery.output as context
        requirements:
          - "Must include step-by-step implementation plan"
          - "Must list all files to create or modify"
          - "Must identify risks from the discovery phase"
          - "Must define testable success criteria"
        evaluation:
          method: algorithmic
          checks:
            - name: has_steps
              type: sections_present
              required_sections: ["steps"]
              required: true
            - name: min_steps
              type: min_list_items
              field: steps
              min_items: 3
              required: true
            - name: has_risks
              type: sections_present
              required_sections: ["risks"]
              required: true
            - name: has_success_criteria
              type: sections_present
              required_sections: ["success_criteria"]
              required: true
            - name: files_identified
              type: field_not_empty
              field: files_affected
              required: false
        approval: user          # Pause for human review before execution
        approval_timeout: 24h
        max_iterations: 3
        cooldown: 10s
        transitions:
          on_pass:
            goto: next
          on_fail:
            behavior: stop

      # --------------------------------------------------------
      # Phase 3: Implementation
      # --------------------------------------------------------
      - name: implementation
        type: execution
        input_from: planning    # Receives planning.output as plan
        evaluation:
          method: script
          script: |
            #!/bin/bash
            set -e
            cd /den/workspace
            echo "Running test suite..."
            python -m pytest tests/ -v --tb=short
            echo "Checking for TODO comments..."
            if grep -r "TODO\|FIXME\|HACK\|XXX" src/ --include="*.py" -l; then
              echo "Found TODO/FIXME comments — resolve before marking complete"
              exit 1
            fi
            echo "All checks passed"
            exit 0
          script_timeout: 120s
        artifacts:
          - path: /den/output/feature/
            type: directory
            required: true
        max_iterations: 5
        cooldown: 20s
        transitions:
          on_pass:
            goto: next
          on_fail:
            behavior: notify
            write_failure_report: /den/output/implementation-failures.md

      # --------------------------------------------------------
      # Phase 4: Verification
      # --------------------------------------------------------
      - name: verification
        type: verification
        input_from: [planning, implementation]   # Gets both
        evaluation:
          method: hybrid
          algorithmic_checks:
            - name: tests_pass
              type: script_exits_zero
              script: "cd /den/workspace && python -m pytest tests/ -q"
              required: true
            - name: no_todos
              type: no_pattern_in_files
              pattern: "TODO|FIXME|HACK|XXX"
              paths: ["src/"]
              required: true
            - name: artifacts_present
              type: artifacts_exist
              paths:
                - /den/output/feature/
              required: true
          qualitative_checks:
            method: llm-judge
            criteria:
              - "Implementation matches the plan produced in the planning phase"
              - "Edge cases identified in discovery risks are handled"
              - "Code is readable and appropriately commented"
            run_if_algorithmic_passes: true
        max_iterations: 2
        cooldown: 15s
        transitions:
          on_pass:
            goto: done
          on_fail:
            behavior: goto
            goto: implementation    # Loop back to fix problems
            max_retries: 1

    # Task-level failure handling (applies when all phases exhaust retries)
    on_fail: notify
```

### 6.3 Phase Type Reference

Each phase `type` sets defaults appropriate for that loop type. These defaults can be overridden by explicitly specifying any field.

| Phase type | Default evaluation | Default max_iterations | Default cooldown | Output schema |
|---|---|---|---|---|
| `research` | algorithmic | 3 | 10s | `{answers: {}, sources_count: int}` |
| `plan` | algorithmic | 3 | 10s | `{plan: {steps: [], risks: [], success_criteria: []}}` |
| `execution` | script | 5 | 20s | `{artifacts: [], execution_log: {}}` |
| `verification` | hybrid | 2 | 15s | `{verified: bool, gaps: [], score: float}` |
| `custom` | (required) | 3 | 10s | (defined by user) |

### 6.4 Complete Field Reference for phases

```yaml
phases:
  - name: <string>                    # Required. Unique within task.
    type: research|plan|execution|verification|custom
                                      # Required.
    description: <string>             # Optional. Human-readable phase description.
    input_from: <phase_name>|[<phase_name>, ...]
                                      # Optional. Which previous phase(s) provide context.

    # For type: research only
    questions:
      - id: <string>                  # Required. Unique question identifier.
        text: <string>                # Required. The question to answer.
        required: true|false          # Default: true

    # For type: plan only
    requirements: [<string>, ...]     # List of requirements the plan must satisfy.
    approval: user|auto|skip          # Default: auto. 'user' adds a human gate.
    approval_timeout: <duration>      # Default: 48h. How long to wait for approval.

    # For type: execution only
    plan_source: <phase_name>         # Which phase produced the plan to execute.

    # Evaluation (all types)
    evaluation:
      method: algorithmic|self-judge|llm-judge|script|hybrid
                                      # Required.
      # For method: algorithmic or method: hybrid
      algorithmic_checks:
        - name: <string>              # Required. Check identifier.
          type: <check_type>          # Required. From Built-in Checks Library.
          required: true|false        # Default: true.
          weight: <float>             # Default: 1.0. For scoring.
          # ... check-specific parameters ...

      # For method: hybrid — qualitative checks run after algorithmic
      qualitative_checks:
        method: self-judge|llm-judge
        criteria: [<string>, ...]
        run_if_algorithmic_passes: true|false   # Default: true

      # For method: script
      script: <inline bash string>    # Script to run. Mutually exclusive with script_path.
      script_path: <path>             # Path to script file. Mutually exclusive with script.
      script_timeout: <duration>      # Default: 120s.

      # For method: self-judge or llm-judge (non-hybrid)
      criteria: [<string>, ...]       # Evaluation criteria list.

    # For type: plan — artifacts expected
    artifacts:
      - path: <string>                # Path inside Den (supports {date}, {timestamp})
        type: markdown|json|csv|directory|any
        required: true|false          # Default: true

    max_iterations: <int>             # Default: from loop type defaults.
    cooldown: <duration>              # Default: from loop type defaults.

    transitions:
      on_pass:
        goto: next|done|<phase_name>  # Default: next
        pass_data: [<field>, ...]     # Specific fields to forward. Default: all.
      on_fail:
        behavior: stop|notify|goto|retry
                                      # Default: stop
        goto: <phase_name>            # Required if behavior: goto
        max_retries: <int>            # Default: 1. Max times this goto can trigger.
        notify_message: <string>      # Message for notification.
        write_failure_report: <path>  # Write a failure report to this path.
```

---

## 7. Built-in Checks Library

Den ships with a library of algorithmic checks. These are implemented in Python in `den/core/checks/`, tested independently of the agent, and available by name in any Agentfile.

### 7.1 Text Content Checks

**`min_word_count`** — Verify output contains at least N words.

```yaml
- name: adequate_length
  type: min_word_count
  min_words: 800         # Required
  count_method: simple   # simple | linguistic (default: simple)
  # 'simple' splits on whitespace. 'linguistic' uses NLP tokenization.
```

Implementation:

```python
class MinWordCountCheck:
    def __init__(self, min_words: int, count_method: str = "simple"):
        self.min_words = min_words
        self.count_method = count_method

    def run(self, output: str, context: dict) -> CheckResult:
        if self.count_method == "simple":
            count = len(output.split())
        else:
            count = len(nltk.word_tokenize(output))
        passed = count >= self.min_words
        return CheckResult(
            passed=passed,
            reason=f"Word count: {count} (minimum: {self.min_words})"
            if not passed else "",
        )
```

---

**`max_word_count`** — Verify output does not exceed N words. Use for briefs, summaries, and concise outputs.

```yaml
- name: concise_enough
  type: max_word_count
  max_words: 600
```

---

**`no_placeholder_text`** — Detect placeholder text patterns that indicate incomplete output.

```yaml
- name: no_placeholders
  type: no_placeholder_text
  # Patterns checked by default:
  # TBD, TODO, to be added, to be written, placeholder, lorem ipsum,
  # [insert], <insert>, coming soon, PLACEHOLDER, fill in later
  custom_patterns:       # Optional: add your own patterns
    - "needs to be completed"
    - "work in progress"
```

Implementation checks for exact matches and regex patterns. Case-insensitive.

---

**`sources_present`** — Verify the output contains actual URLs (not just mentions of "sources").

```yaml
- name: has_sources
  type: sources_present
  min_count: 3           # Minimum number of distinct URLs
  url_pattern: https://  # URL prefix to detect (default: http)
  require_domain_diversity: false  # Require URLs from different domains
```

This check extracts URLs using regex `https?://[^\s\)>\"]+` and counts distinct values. A URL counts only once even if cited multiple times. Common false positives (localhost, example.com, placeholder.com) are excluded.

---

**`sections_present`** — Verify required section headers exist in the output.

```yaml
- name: has_required_sections
  type: sections_present
  required_sections:
    - "executive summary"
    - "analysis"
    - "risks"
    - "conclusion"
  detection_method: header   # header | keyword | both (default: header)
  # 'header': looks for markdown headers (## Section Name)
  # 'keyword': looks for section name anywhere in text
  # 'both': header preferred, keyword as fallback
  case_sensitive: false      # Default: false
```

---

**`no_pattern_in_files`** — Verify no matching patterns exist in specified files or directories.

```yaml
- name: no_debug_code
  type: no_pattern_in_files
  pattern: "console\\.log|print\\(|debugger|breakpoint"
  paths:
    - /den/workspace/src/
  file_extensions: [".js", ".ts"]    # Optional filter
  exclude_paths:                      # Optional exclusions
    - /den/workspace/src/tests/
```

---

**`format_valid`** — Verify output is valid in a given format.

```yaml
- name: valid_json
  type: format_valid
  format: json|yaml|toml|xml|csv|markdown
  # For json/yaml/toml/xml: validates parseable
  # For csv: validates consistent column count
  # For markdown: validates no broken links (if check_links: true)
  check_links: false    # Only for markdown, default: false (expensive)
```

---

**`schema_valid`** — Verify output matches a JSON schema.

```yaml
- name: matches_schema
  type: schema_valid
  schema:
    type: object
    required: ["title", "sections", "sources"]
    properties:
      title:
        type: string
        minLength: 1
      sections:
        type: array
        minItems: 3
      sources:
        type: array
        items:
          type: string
          pattern: "^https?://"
  # Or reference a schema file:
  schema_file: /den/workspace/schemas/report.schema.json
```

---

**`all_questions_addressed`** — Verify that output contains substantive answers to all required questions. Used in Research loops.

```yaml
- name: all_answered
  type: all_questions_addressed
  questions:
    - id: competitors
      text: "What existing solutions address this problem?"
    - id: risks
      text: "What are the main risks?"
  min_words_per_answer: 100    # Minimum words to count as answered
  require_question_header: false  # Require question text appears as header
```

This check uses semantic matching (not keyword matching) to determine whether each question has been answered. It looks for the answer in the output based on the question's topic, not exact wording.

---

**`field_not_empty`** — Verify a specific field in JSON output is present and non-empty.

```yaml
- name: steps_present
  type: field_not_empty
  field: plan.steps         # Dot-notation path into the JSON output
  min_items: 3              # For arrays: minimum number of items
```

---

**`min_list_items`** — Verify a list field has at least N items.

```yaml
- name: adequate_steps
  type: min_list_items
  field: steps
  min_items: 3
```

### 7.2 File System Checks

**`artifacts_exist`** — Verify required output files or directories were created.

```yaml
- name: output_exists
  type: artifacts_exist
  paths:
    - /den/output/report.md
    - /den/output/data/
  min_size_bytes: 100    # Optional: reject empty files
```

---

**`file_count_in_dir`** — Verify a directory contains at least N files.

```yaml
- name: enough_files
  type: file_count_in_dir
  path: /den/output/results/
  min_count: 5
  file_pattern: "*.json"   # Optional glob filter
```

---

**`file_modified_recently`** — Verify a file was modified within the current task run (ensures the agent actually wrote new output, not stale files).

```yaml
- name: output_is_new
  type: file_modified_recently
  path: /den/output/report.md
  max_age_seconds: 300    # File must have been modified in last 5 minutes
```

### 7.3 Code Quality Checks

**`script_exits_zero`** — Run an arbitrary script and verify it exits 0. The most flexible code check.

```yaml
- name: tests_pass
  type: script_exits_zero
  script: "cd /den/workspace && python -m pytest tests/ -q --tb=line"
  timeout: 120s
```

---

**`no_syntax_errors`** — Verify code files have no syntax errors (language-specific).

```yaml
- name: python_syntax_clean
  type: no_syntax_errors
  language: python|javascript|typescript|bash|json|yaml
  paths:
    - /den/workspace/src/
  file_extensions: [".py"]
```

---

**`no_todo_comments`** — Verify no TODO/FIXME/HACK comments remain in code.

```yaml
- name: no_todos
  type: no_todo_comments
  patterns: ["TODO", "FIXME", "HACK", "XXX", "TEMP"]
  paths:
    - /den/workspace/src/
  exclude_paths:
    - /den/workspace/src/tests/   # May have intentional TODOs
```

---

**`linter_passes`** — Run a linter and verify output is clean.

```yaml
- name: lint_clean
  type: linter_passes
  linter: flake8|eslint|pylint|ruff
  config_file: /den/workspace/.flake8   # Optional
  paths: [/den/workspace/src/]
  max_warnings: 0    # Treat warnings as errors
```

### 7.4 Data and Schema Checks

**`csv_row_count`** — Verify a CSV file has at least N rows.

```yaml
- name: enough_data
  type: csv_row_count
  path: /den/output/results.csv
  min_rows: 10
  has_header: true   # Exclude header from count
```

---

**`json_field_values`** — Verify specific JSON fields have expected values or value ranges.

```yaml
- name: confidence_acceptable
  type: json_field_values
  path: /den/output/analysis.json
  checks:
    - field: confidence_score
      operator: ">="
      value: 0.7
    - field: status
      operator: "in"
      value: ["complete", "verified"]
```

---

**`completeness_score`** — Compute a completeness score based on how many fields are populated. Useful for structured reports.

```yaml
- name: report_complete
  type: completeness_score
  required_fields:
    - title
    - executive_summary
    - analysis
    - sources
    - conclusion
  min_score: 0.8     # 80% of required fields must be populated
```

### 7.5 Research-Specific Checks

**`unique_sources`** — Verify sources are diverse (different domains, not duplicates).

```yaml
- name: diverse_sources
  type: unique_sources
  min_unique_domains: 3
  excluded_domains:           # Do not count these as valid sources
    - wikipedia.org
    - example.com
```

---

**`source_recency`** — Verify sources are recent (within N days). Requires extracting publication dates from URLs or content.

```yaml
- name: recent_sources
  type: source_recency
  max_age_days: 365
  # Note: this check uses heuristics (URL date patterns, metadata)
  # and may produce false negatives for undated sources
  fail_on_undated: false   # Default: false. Undated sources pass.
```

---

## 8. Custom Loop Design Guide

Den's loop primitives are open. Any developer can define loop patterns not covered by the four standard types. This section explains how to design them correctly.

### 8.1 The Design Process

Start by answering these questions for your loop:

**1. What is the loop trying to produce?**

Be specific. "A report" is too vague. "A JSON object with fields title, sections, and sources, where sections is an array of at least 3 objects each with heading and body fields" is a loop design.

**2. How do you know when it's done?**

Write the checks before you write anything else. If you cannot state the checks algorithmically, the loop's exit criteria are not clear enough. Refine the exit criteria until they are expressible as code.

**3. What does failure look like, and what information should the next iteration get?**

Failure feedback drives the improvement cycle. The feedback must be specific enough that the next iteration can act on it. "Output was inadequate" is not feedback. "The sources field contained 1 URL but requires 3, and the body field was 120 words but requires 300" is feedback.

**4. What is the maximum iteration budget?**

Be realistic. A loop that almost never passes in fewer than 3 iterations should have max_iterations >= 5. A loop that typically passes on the first try should have max_iterations: 2 or 3 as a safety net. Never set max_iterations: 1 for a loop that matters — that is not a loop, that is a single shot.

**5. What does this loop produce for the next phase?**

Design the output schema of your loop with the next phase's input in mind. If your research loop will feed a planning loop, design the research output to contain exactly what a planner needs: structured answers, not a prose narrative.

### 8.2 Custom Loop Example: Code Review Loop

A loop that reviews code changes and enforces quality standards before merge.

```yaml
tasks:
  review-pr:
    description: |
      Review the code changes in /den/workspace/pr-diff.patch.
      Identify issues, suggest improvements, and verify the changes
      meet the project's quality standards.

    phases:
      - name: initial-review
        type: custom
        description: "First-pass review of code changes"
        evaluation:
          method: hybrid
          algorithmic_checks:
            - name: review_is_comprehensive
              type: sections_present
              required_sections:
                - "summary"
                - "issues"
                - "suggestions"
              required: true
            - name: issues_are_specific
              type: min_list_items
              field: issues
              min_items: 0    # Zero issues is a valid outcome
              required: false
            - name: review_is_substantive
              type: min_word_count
              min_words: 200
              required: true
          qualitative_checks:
            method: self-judge
            criteria:
              - "Each identified issue includes the file and line number"
              - "Suggestions are actionable, not just observations"
            run_if_algorithmic_passes: true
        max_iterations: 2
        transitions:
          on_pass:
            goto: next
          on_fail:
            behavior: stop

      - name: security-check
        type: custom
        description: "Security-focused analysis of changes"
        evaluation:
          method: script
          script: |
            #!/bin/bash
            # Run static security analysis
            cd /den/workspace
            if ! python -m bandit -r src/ -f json -o /tmp/bandit-output.json; then
              cat /tmp/bandit-output.json | python -c "
import json, sys
data = json.load(sys.stdin)
issues = [r for r in data.get('results', []) if r['issue_severity'] in ['HIGH', 'MEDIUM']]
if issues:
    for i in issues:
        print(f\"  {i['issue_severity']}: {i['issue_text']} ({i['filename']}:{i['line_number']})\")
    sys.exit(1)
print('No security issues found')
sys.exit(0)
"
            fi
          script_timeout: 60s
        max_iterations: 3
        transitions:
          on_pass:
            goto: done
          on_fail:
            behavior: notify
            notify_message: |
              Security issues found in PR. Review /den/output/security-report.md.
```

### 8.3 Custom Loop Example: Newsletter Drafting Loop

A loop for content teams that produces a newsletter draft meeting editorial standards.

```yaml
tasks:
  draft-newsletter:
    description: |
      Draft this week's newsletter. Include 3 feature stories,
      1 community spotlight, and 1 upcoming events section.
      Tone: friendly and informative. Length: 600-800 words total.

    phases:
      - name: content-gathering
        type: research
        questions:
          - id: feature_stories
            text: "What are the 3 most significant stories from this week?"
            required: true
          - id: community_spotlight
            text: "Who should we spotlight from the community this week?"
            required: true
          - id: upcoming_events
            text: "What events are coming up in the next 2 weeks?"
            required: true
        evaluation:
          method: algorithmic
          checks:
            - name: all_answered
              type: all_questions_addressed
              min_words_per_answer: 50
              required: true
        max_iterations: 3

      - name: drafting
        type: custom
        input_from: content-gathering
        evaluation:
          method: hybrid
          algorithmic_checks:
            - name: word_count_range
              type: min_word_count
              min_words: 600
              required: true
            - name: not_too_long
              type: max_word_count
              max_words: 800
              required: true
            - name: has_three_stories
              type: min_list_items
              field: feature_stories
              min_items: 3
              required: true
            - name: has_spotlight
              type: sections_present
              required_sections: ["community spotlight"]
              required: true
            - name: has_events
              type: sections_present
              required_sections: ["upcoming events"]
              required: true
            - name: no_placeholders
              type: no_placeholder_text
              required: true
          qualitative_checks:
            method: llm-judge
            criteria:
              - "Tone is friendly, conversational, and appropriate for a community newsletter"
              - "Each feature story has a clear hook that makes the reader want to learn more"
              - "Transitions between sections are smooth"
            run_if_algorithmic_passes: true
        max_iterations: 4
        cooldown: 15s
        transitions:
          on_pass:
            goto: done
          on_fail:
            behavior: notify
```

### 8.4 Principles for Good Custom Loops

**Make checks specific and measurable.** Every check should have a binary answer. "Is the report good?" is not a check. "Does the report have at least 3 sections with markdown headers?" is a check.

**Use algorithmic checks for structure, LLM judgment for semantics.** Structure (word count, section presence, format validity, test results) should never be delegated to an LLM. Semantics (tone, coherence, intent matching) sometimes require LLM evaluation. Default to algorithmic. Escalate to LLM only when necessary.

**Budget iterations realistically.** Look at what you are asking the loop to do. If you are asking for a 800-word report with 5 sources and 3 sections, a well-configured agent should pass in 1-2 iterations on most runs. Set max_iterations to 2x the typical pass count. If you are setting max_iterations: 10, you probably have a problem with your task description or your checks.

**Design output schemas first.** The output of one loop is the input of the next. Design the output schema before you design the loop behavior. Know what shape your data is in at each transition point.

**Test your checks independently.** Den ships a check testing tool (`den check-test`) that runs your checks against sample inputs. Use it to verify your checks behave as expected before configuring them in a live Agentfile.

```bash
# Test a check against sample input
den check-test --check min_word_count --param min_words=500 \
  --input /path/to/sample-output.md
# Output: PASS: 847 words (minimum: 500)

den check-test --check sources_present --param min_count=3 \
  --input /path/to/sample-output.md
# Output: FAIL: Found 1 URL (minimum: 3). URL found: https://example.com
```

---

## 9. Loop Engine Implementation

This section shows the full Python implementation of the Loop Engine, including multi-phase support.

### 9.1 Core Types

```python
# den/core/loop/types.py

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any
import time


class PhaseStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class LoopStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    EXHAUSTED = "exhausted"
    WAITING_APPROVAL = "waiting_approval"


@dataclass
class CheckResult:
    name: str
    passed: bool
    reason: str           # Empty string if passed, explanation if failed
    value: Any = None     # The measured value (word count, url count, etc.)


@dataclass
class EvaluationResult:
    passed: bool
    score: float                       # 0.0 to 1.0
    feedback: str                      # Structured feedback for next iteration
    method_used: str                   # algorithmic | self-judge | llm-judge | script | hybrid
    check_results: list[CheckResult]   # Per-check pass/fail


@dataclass
class IterationRecord:
    iteration: int
    phase_name: str
    start_time: float
    end_time: float
    output_summary: str
    evaluation: EvaluationResult
    artifact_paths: list[str]
    context_used: dict                 # What context was passed to the agent


@dataclass
class PhaseResult:
    phase_name: str
    phase_type: str
    status: PhaseStatus
    output: dict                       # Structured output from the phase
    iterations_used: int
    iterations_allowed: int
    iteration_records: list[IterationRecord]
    duration_s: float
    final_evaluation: Optional[EvaluationResult]


@dataclass
class TaskResult:
    task_name: str
    status: LoopStatus
    phases: list[PhaseResult]
    total_iterations: int
    total_duration_s: float
    artifact_paths: list[str]
    final_phase: str
```

### 9.2 The Phase Loop

```python
# den/core/loop/phase_loop.py

import json
import time
import logging
from pathlib import Path
from typing import Optional

from .types import (
    PhaseStatus, EvaluationResult, IterationRecord,
    PhaseResult, CheckResult
)

logger = logging.getLogger(__name__)


class PhaseLoop:
    """
    Executes a single phase as a self-correcting loop.

    Each phase iteration:
    1. Builds context from prior phase outputs and prior iteration feedback
    2. Runs the agent
    3. Evaluates the output
    4. If passed: returns PhaseResult with status PASSED
    5. If failed: generates feedback, waits cooldown, retries
    6. If exhausted: returns PhaseResult with status FAILED
    """

    def __init__(
        self,
        agent_context,
        evaluator_factory,
        memory_system,
        workspace_path: Path,
    ):
        self.agent = agent_context
        self.evaluator_factory = evaluator_factory
        self.memory = memory_system
        self.workspace = workspace_path

    def execute(
        self,
        phase_config: dict,
        prior_phase_outputs: dict,
        task_name: str,
    ) -> PhaseResult:
        phase_name = phase_config["name"]
        phase_type = phase_config["type"]
        max_iterations = phase_config.get("max_iterations", self._default_max(phase_type))
        cooldown = phase_config.get("cooldown_s", self._default_cooldown(phase_type))

        logger.info(f"[{task_name}] Starting phase '{phase_name}' (type: {phase_type})")

        phase_dir = self.workspace / "phases" / phase_name
        phase_dir.mkdir(parents=True, exist_ok=True)

        # Check for resumable state (agent may have been restarted mid-phase)
        existing_records = self._load_existing_records(phase_dir)
        start_iteration = len(existing_records) + 1
        feedback: Optional[str] = None
        if existing_records:
            # Resume: use feedback from last failed iteration
            last = existing_records[-1]
            feedback = last.evaluation.feedback
            logger.info(
                f"[{task_name}/{phase_name}] Resuming from iteration {start_iteration} "
                f"(found {len(existing_records)} prior records)"
            )

        evaluator = self.evaluator_factory.create(phase_config["evaluation"])
        records: list[IterationRecord] = existing_records
        phase_start = time.monotonic()

        for iteration in range(start_iteration, max_iterations + 1):
            iter_start = time.monotonic()
            logger.info(
                f"[{task_name}/{phase_name}] Iteration {iteration}/{max_iterations}"
            )

            # Build the full context for this iteration
            context = self._build_context(
                phase_config=phase_config,
                prior_phase_outputs=prior_phase_outputs,
                iteration=iteration,
                feedback=feedback,
                task_name=task_name,
            )

            # Write pending status to disk (enables resumption)
            self._write_status(phase_dir, PhaseStatus.IN_PROGRESS, iteration)

            # Run the agent for this phase iteration
            agent_output = self.agent.execute(context)

            # Evaluate the output
            evaluation = evaluator.evaluate(
                output=agent_output,
                phase_config=phase_config,
            )

            record = IterationRecord(
                iteration=iteration,
                phase_name=phase_name,
                start_time=iter_start,
                end_time=time.monotonic(),
                output_summary=agent_output.summary,
                evaluation=evaluation,
                artifact_paths=agent_output.artifact_paths,
                context_used=context,
            )
            records.append(record)

            # Persist iteration record
            self._write_record(phase_dir, iteration, record)

            # Log to agent memory (enables learning across task runs)
            self.memory.write(
                f"task_history/{task_name}/{phase_name}/iteration_{iteration}.json",
                {
                    "task": task_name,
                    "phase": phase_name,
                    "iteration": iteration,
                    "passed": evaluation.passed,
                    "score": evaluation.score,
                    "check_results": [
                        {"name": c.name, "passed": c.passed, "reason": c.reason}
                        for c in evaluation.check_results
                    ],
                    "timestamp": iter_start,
                }
            )

            if evaluation.passed:
                logger.info(
                    f"[{task_name}/{phase_name}] PASSED on iteration {iteration}. "
                    f"Score: {evaluation.score:.2f}"
                )
                self._write_status(phase_dir, PhaseStatus.PASSED, iteration)

                # Parse structured output for forwarding to next phase
                structured_output = self._extract_structured_output(
                    agent_output, phase_config
                )
                self._write_output(phase_dir, structured_output)

                return PhaseResult(
                    phase_name=phase_name,
                    phase_type=phase_type,
                    status=PhaseStatus.PASSED,
                    output=structured_output,
                    iterations_used=iteration,
                    iterations_allowed=max_iterations,
                    iteration_records=records,
                    duration_s=time.monotonic() - phase_start,
                    final_evaluation=evaluation,
                )

            # Failed — generate feedback for next iteration
            feedback = self._generate_feedback(evaluation, iteration, phase_name)
            logger.warning(
                f"[{task_name}/{phase_name}] Iteration {iteration} FAILED. "
                f"Score: {evaluation.score:.2f}. "
                f"Failed checks: {[c.name for c in evaluation.check_results if not c.passed]}"
            )

            if iteration < max_iterations:
                logger.info(
                    f"[{task_name}/{phase_name}] Waiting {cooldown}s before retry..."
                )
                time.sleep(cooldown)

        # All iterations exhausted
        logger.error(
            f"[{task_name}/{phase_name}] EXHAUSTED {max_iterations} iterations "
            f"without passing."
        )
        self._write_status(phase_dir, PhaseStatus.FAILED, max_iterations)

        return PhaseResult(
            phase_name=phase_name,
            phase_type=phase_type,
            status=PhaseStatus.FAILED,
            output={},
            iterations_used=max_iterations,
            iterations_allowed=max_iterations,
            iteration_records=records,
            duration_s=time.monotonic() - phase_start,
            final_evaluation=records[-1].evaluation if records else None,
        )

    def _build_context(
        self,
        phase_config: dict,
        prior_phase_outputs: dict,
        iteration: int,
        feedback: Optional[str],
        task_name: str,
    ) -> dict:
        """
        Build the full context passed to the agent for this iteration.

        The context includes:
        - Phase description and type-specific instructions
        - Output from all prior phases
        - Feedback from prior iterations (if any)
        - Memory index for relevant historical context
        """
        phase_type = phase_config["type"]
        type_instructions = self._type_instructions(phase_type, phase_config)

        context = {
            "task_name": task_name,
            "phase_name": phase_config["name"],
            "phase_type": phase_type,
            "iteration": iteration,
            "type_instructions": type_instructions,
            "prior_phases": prior_phase_outputs,
            "prior_feedback": feedback,
            "memory_index": self.memory.read_index(),
        }

        # Add type-specific context
        if phase_type == "research":
            context["questions"] = phase_config.get("questions", [])
        elif phase_type == "plan":
            context["requirements"] = phase_config.get("requirements", [])
        elif phase_type == "execution":
            # Find the plan — either from input_from or the immediately prior phase
            input_from = phase_config.get("input_from") or self._find_plan_phase(
                prior_phase_outputs
            )
            if input_from and input_from in prior_phase_outputs:
                context["plan"] = prior_phase_outputs[input_from].get("plan", {})
        elif phase_type == "verification":
            input_sources = phase_config.get("input_from", [])
            if isinstance(input_sources, str):
                input_sources = [input_sources]
            context["artifacts_to_verify"] = [
                prior_phase_outputs.get(src, {}).get("artifacts", [])
                for src in input_sources
            ]

        return context

    def _type_instructions(self, phase_type: str, phase_config: dict) -> str:
        """Return type-specific instructions prepended to agent context."""
        if phase_type == "research":
            questions = phase_config.get("questions", [])
            q_list = "\n".join(
                f"  - [{q['id']}]: {q['text']}" +
                (" (required)" if q.get("required", True) else " (optional)")
                for q in questions
            )
            return (
                f"You are in the RESEARCH phase. Your job is to answer the following "
                f"questions thoroughly. For each answer:\n"
                f"  1. Provide a substantive response with specific information\n"
                f"  2. Include source URLs for factual claims\n"
                f"  3. Use web_search to find current information if needed\n\n"
                f"Questions to answer:\n{q_list}\n\n"
                f"Output your answers as a JSON object keyed by question ID."
            )
        elif phase_type == "plan":
            requirements = phase_config.get("requirements", [])
            req_list = "\n".join(f"  - {r}" for r in requirements)
            return (
                f"You are in the PLANNING phase. Produce a detailed, structured plan.\n"
                f"The plan must satisfy these requirements:\n{req_list}\n\n"
                f"Output your plan as a JSON object with fields:\n"
                f"  - objective: string\n"
                f"  - steps: array of {{id, action, files_affected, expected_output}}\n"
                f"  - risks: array of {{risk, mitigation, severity}}\n"
                f"  - success_criteria: array of strings\n"
                f"  - estimated_duration: string"
            )
        elif phase_type == "execution":
            return (
                "You are in the EXECUTION phase. Implement the plan exactly as specified.\n"
                "After implementing each step:\n"
                "  1. Verify the step's output exists\n"
                "  2. Check it matches what the plan specified\n"
                "  3. Only move to the next step when the current one is complete\n\n"
                "Do not skip steps. Do not leave placeholders. Complete every step."
            )
        elif phase_type == "verification":
            return (
                "You are in the VERIFICATION phase. Compare all produced artifacts "
                "against the original requirements and the plan.\n"
                "Systematically check:\n"
                "  1. Every required file exists and has content\n"
                "  2. The implementation matches the plan\n"
                "  3. Edge cases from the research phase are handled\n"
                "  4. No placeholder text or incomplete sections remain\n\n"
                "If anything is missing or incorrect, fix it in this phase."
            )
        return phase_config.get("description", "")

    def _generate_feedback(
        self, evaluation: EvaluationResult, iteration: int, phase_name: str
    ) -> str:
        failed_checks = [c for c in evaluation.check_results if not c.passed]
        lines = [
            f"Iteration {iteration} of phase '{phase_name}' did not pass.",
            f"Score: {evaluation.score:.0%} ({len(evaluation.check_results) - len(failed_checks)}"
            f"/{len(evaluation.check_results)} checks passed)",
            "",
            "Checks that failed:",
        ]
        for check in failed_checks:
            lines.append(f"  [{check.name}] {check.reason}")
        lines += [
            "",
            "In your next attempt, specifically address these failures.",
            "Do not repeat the same approach that just failed.",
        ]
        return "\n".join(lines)

    def _default_max(self, phase_type: str) -> int:
        return {"research": 3, "plan": 3, "execution": 5, "verification": 2}.get(
            phase_type, 3
        )

    def _default_cooldown(self, phase_type: str) -> int:
        return {"research": 10, "plan": 10, "execution": 20, "verification": 15}.get(
            phase_type, 10
        )

    def _extract_structured_output(self, agent_output, phase_config: dict) -> dict:
        """Extract and normalize the structured output from agent output."""
        try:
            return json.loads(agent_output.primary_content)
        except (json.JSONDecodeError, AttributeError):
            return {"raw_output": agent_output.content, "artifacts": agent_output.artifact_paths}

    def _load_existing_records(self, phase_dir: Path) -> list[IterationRecord]:
        records = []
        iter_dir = phase_dir / "iterations"
        if iter_dir.exists():
            for record_file in sorted(iter_dir.glob("*.json")):
                with open(record_file) as f:
                    data = json.load(f)
                    records.append(IterationRecord(**data))
        return records

    def _write_record(self, phase_dir: Path, iteration: int, record: IterationRecord):
        iter_dir = phase_dir / "iterations"
        iter_dir.mkdir(exist_ok=True)
        with open(iter_dir / f"{iteration:03d}.json", "w") as f:
            json.dump(record.__dict__, f, indent=2, default=str)

    def _write_status(self, phase_dir: Path, status: PhaseStatus, iteration: int):
        with open(phase_dir / "status.json", "w") as f:
            json.dump({"status": status.value, "last_iteration": iteration}, f)

    def _write_output(self, phase_dir: Path, output: dict):
        with open(phase_dir / "output.json", "w") as f:
            json.dump(output, f, indent=2)

    def _find_plan_phase(self, prior_phase_outputs: dict) -> Optional[str]:
        """Find the most recent phase that produced a plan."""
        for phase_name in reversed(list(prior_phase_outputs.keys())):
            if "plan" in prior_phase_outputs[phase_name]:
                return phase_name
        return None
```

### 9.3 The Multi-Phase Loop Engine

```python
# den/core/loop/engine.py

import time
import logging
from pathlib import Path
from typing import Optional

from .types import LoopStatus, PhaseStatus, TaskResult, PhaseResult
from .phase_loop import PhaseLoop

logger = logging.getLogger(__name__)


class LoopEngine:
    """
    Orchestrates multi-phase task execution.

    Takes a task configuration with a phases array, executes each phase
    as a PhaseLoop, manages transitions between phases, and handles
    failure behaviors.
    """

    def __init__(self, agent_context, evaluator_factory, memory_system, workspace_root: Path):
        self.agent = agent_context
        self.evaluator_factory = evaluator_factory
        self.memory = memory_system
        self.workspace_root = workspace_root

    def execute(self, task_config: dict) -> TaskResult:
        task_name = task_config["name"]
        phases_config = task_config.get("phases")

        # Single-phase tasks (legacy loop: spec)
        if not phases_config:
            return self._execute_single_phase(task_config)

        return self._execute_multi_phase(task_config, phases_config)

    def _execute_multi_phase(self, task_config: dict, phases_config: list) -> TaskResult:
        task_name = task_config["name"]
        task_start = time.monotonic()

        workspace = self.workspace_root / task_name
        workspace.mkdir(parents=True, exist_ok=True)

        phase_loop = PhaseLoop(
            agent_context=self.agent,
            evaluator_factory=self.evaluator_factory,
            memory_system=self.memory,
            workspace_path=workspace,
        )

        phase_results: list[PhaseResult] = []
        prior_outputs: dict = {}
        phase_index = 0
        goto_counts: dict[str, int] = {}   # Track loop-back counts to prevent infinite loops
        all_artifacts: list[str] = []

        while phase_index < len(phases_config):
            phase_config = phases_config[phase_index]
            phase_name = phase_config["name"]

            logger.info(
                f"[{task_name}] Phase {phase_index + 1}/{len(phases_config)}: "
                f"'{phase_name}'"
            )

            phase_result = phase_loop.execute(
                phase_config=phase_config,
                prior_phase_outputs=prior_outputs,
                task_name=task_name,
            )
            phase_results.append(phase_result)

            if phase_result.artifacts:
                all_artifacts.extend(phase_result.artifact_paths)

            if phase_result.status == PhaseStatus.PASSED:
                # Store output for forwarding to subsequent phases
                prior_outputs[phase_name] = phase_result.output

                # Determine transition
                transition = phase_config.get("transitions", {}).get("on_pass", {})
                goto = transition.get("goto", "next")

                if goto == "next":
                    phase_index += 1
                elif goto == "done":
                    break
                else:
                    # Jump to a named phase
                    target = self._find_phase_index(phases_config, goto)
                    if target is None:
                        logger.error(
                            f"[{task_name}] Transition goto '{goto}' not found in phases."
                        )
                        break
                    phase_index = target

            else:
                # Phase failed
                transition = phase_config.get("transitions", {}).get("on_fail", {})
                behavior = transition.get("behavior", "stop")

                if behavior == "stop":
                    logger.error(
                        f"[{task_name}] Phase '{phase_name}' failed. Stopping task."
                    )
                    self._handle_task_failure(task_config, phase_results)
                    return TaskResult(
                        task_name=task_name,
                        status=LoopStatus.FAILED,
                        phases=phase_results,
                        total_iterations=sum(p.iterations_used for p in phase_results),
                        total_duration_s=time.monotonic() - task_start,
                        artifact_paths=all_artifacts,
                        final_phase=phase_name,
                    )

                elif behavior == "notify":
                    logger.error(
                        f"[{task_name}] Phase '{phase_name}' failed. Notifying."
                    )
                    self._write_failure_notification(
                        task_name, phase_name, phase_results, transition
                    )
                    return TaskResult(
                        task_name=task_name,
                        status=LoopStatus.FAILED,
                        phases=phase_results,
                        total_iterations=sum(p.iterations_used for p in phase_results),
                        total_duration_s=time.monotonic() - task_start,
                        artifact_paths=all_artifacts,
                        final_phase=phase_name,
                    )

                elif behavior == "goto":
                    goto_target = transition.get("goto")
                    max_retries = transition.get("max_retries", 1)
                    goto_counts[goto_target] = goto_counts.get(goto_target, 0) + 1

                    if goto_counts[goto_target] > max_retries:
                        logger.error(
                            f"[{task_name}] Loop-back to '{goto_target}' exceeded "
                            f"max_retries ({max_retries}). Stopping."
                        )
                        self._handle_task_failure(task_config, phase_results)
                        return TaskResult(
                            task_name=task_name,
                            status=LoopStatus.EXHAUSTED,
                            phases=phase_results,
                            total_iterations=sum(p.iterations_used for p in phase_results),
                            total_duration_s=time.monotonic() - task_start,
                            artifact_paths=all_artifacts,
                            final_phase=phase_name,
                        )

                    target_index = self._find_phase_index(phases_config, goto_target)
                    if target_index is None:
                        logger.error(
                            f"[{task_name}] goto '{goto_target}' not found."
                        )
                        break

                    logger.info(
                        f"[{task_name}] Loop-back to phase '{goto_target}' "
                        f"(attempt {goto_counts[goto_target]}/{max_retries})"
                    )
                    phase_index = target_index

        # All phases completed (or broke out of loop)
        final_status = (
            LoopStatus.SUCCESS
            if all(p.status == PhaseStatus.PASSED for p in phase_results)
            else LoopStatus.FAILED
        )

        if final_status == LoopStatus.SUCCESS:
            self.memory.write(
                f"task_history/{task_name}/last_success.json",
                {
                    "task": task_name,
                    "phases": [
                        {
                            "name": p.phase_name,
                            "iterations": p.iterations_used,
                        }
                        for p in phase_results
                    ],
                    "total_duration_s": time.monotonic() - task_start,
                    "artifact_paths": all_artifacts,
                    "timestamp": task_start,
                }
            )

        logger.info(
            f"[{task_name}] Task complete. Status: {final_status.value}. "
            f"Phases: {len(phase_results)}. "
            f"Total iterations: {sum(p.iterations_used for p in phase_results)}. "
            f"Duration: {time.monotonic() - task_start:.1f}s"
        )

        return TaskResult(
            task_name=task_name,
            status=final_status,
            phases=phase_results,
            total_iterations=sum(p.iterations_used for p in phase_results),
            total_duration_s=time.monotonic() - task_start,
            artifact_paths=all_artifacts,
            final_phase=phase_results[-1].phase_name if phase_results else "",
        )

    def _find_phase_index(self, phases: list, name: str) -> Optional[int]:
        for i, p in enumerate(phases):
            if p["name"] == name:
                return i
        return None

    def _handle_task_failure(self, task_config: dict, phase_results: list):
        on_fail = task_config.get("on_fail", "stop")
        if on_fail == "notify":
            self.memory.write(
                f"task_history/{task_config['name']}/failure_notification.json",
                {
                    "task": task_config["name"],
                    "failed_phase": phase_results[-1].phase_name if phase_results else None,
                    "notify": True,
                }
            )

    def _write_failure_notification(
        self,
        task_name: str,
        phase_name: str,
        phase_results: list,
        transition: dict,
    ):
        notification_path = transition.get(
            "write_failure_report",
            f"/den/output/failure-{task_name}-{phase_name}.md"
        )
        # Write a structured failure report
        report_lines = [
            f"# Task Failure Report",
            f"",
            f"**Task:** {task_name}",
            f"**Failed phase:** {phase_name}",
            f"",
            f"## Phase Summary",
        ]
        for p in phase_results:
            status_icon = "PASSED" if p.status == PhaseStatus.PASSED else "FAILED"
            report_lines.append(
                f"- **{p.phase_name}**: {status_icon} "
                f"({p.iterations_used}/{p.iterations_allowed} iterations)"
            )
        if phase_results and phase_results[-1].final_evaluation:
            eval_ = phase_results[-1].final_evaluation
            report_lines += [
                f"",
                f"## Final Evaluation (Failed Phase)",
                f"",
                f"Score: {eval_.score:.0%}",
                f"",
                f"### Failed Checks",
            ]
            for c in eval_.check_results:
                if not c.passed:
                    report_lines.append(f"- **{c.name}**: {c.reason}")

        report_content = "\n".join(report_lines)
        Path(notification_path).parent.mkdir(parents=True, exist_ok=True)
        Path(notification_path).write_text(report_content)
        logger.info(f"[{task_name}] Failure report written to {notification_path}")

    def _execute_single_phase(self, task_config: dict) -> TaskResult:
        """Execute a task that uses the legacy single-phase loop: spec."""
        # Delegate to the existing single-loop logic
        # This preserves backward compatibility with v1 Agentfiles
        from .legacy import LegacyLoopExecutor
        return LegacyLoopExecutor(
            self.agent, self.evaluator_factory, self.memory, self.workspace_root
        ).execute(task_config)
```

### 9.4 The Evaluator Factory

```python
# den/core/loop/evaluator_factory.py

from .evaluators.algorithmic import AlgorithmicEvaluator
from .evaluators.script import ScriptEvaluator
from .evaluators.llm_judge import LLMJudgeEvaluator
from .evaluators.self_judge import SelfJudgeEvaluator
from .evaluators.hybrid import HybridEvaluator


class EvaluatorFactory:
    """Creates evaluator instances from evaluation config."""

    def __init__(self, agent_context, check_registry):
        self.agent = agent_context
        self.checks = check_registry

    def create(self, eval_config: dict):
        method = eval_config["method"]

        if method == "algorithmic":
            return AlgorithmicEvaluator(
                checks=self._build_checks(eval_config.get("algorithmic_checks", [])),
            )

        elif method == "script":
            return ScriptEvaluator(
                script=eval_config.get("script"),
                script_path=eval_config.get("script_path"),
                timeout=eval_config.get("script_timeout_s", 120),
            )

        elif method == "self-judge":
            return SelfJudgeEvaluator(
                agent=self.agent,
                criteria=eval_config.get("criteria", []),
            )

        elif method == "llm-judge":
            return LLMJudgeEvaluator(
                model=eval_config.get("judge_model", self.agent.model),
                criteria=eval_config.get("criteria", []),
            )

        elif method == "hybrid":
            algorithmic = AlgorithmicEvaluator(
                checks=self._build_checks(eval_config.get("algorithmic_checks", [])),
            )
            qualitative_config = eval_config.get("qualitative_checks")
            qualitative = None
            if qualitative_config:
                qualitative = self.create(qualitative_config)

            return HybridEvaluator(
                algorithmic=algorithmic,
                qualitative=qualitative,
                run_qualitative_if_algorithmic_passes=eval_config.get(
                    "run_if_algorithmic_passes", True
                ),
            )

        raise ValueError(f"Unknown evaluation method: '{method}'")

    def _build_checks(self, checks_config: list):
        return [
            self.checks.create(check_config)
            for check_config in checks_config
        ]
```

---

## 10. Real-World Examples

### 10.1 Software Development Agent

A full discovery → planning → implementation → verification workflow for building software features.

```yaml
# software-dev-agent.agentfile.yaml

name: software-dev-agent
model: claude-sonnet-4-6

system_prompt: |
  You are a senior software engineer. You build features methodically:
  research first, plan second, implement third, verify last.
  You never skip phases. You never submit placeholder code.
  You write tests for everything you build.
  When you receive feedback from a failed evaluation, you read it
  carefully and address every point specifically in your next attempt.

tools:
  - file_read
  - file_write
  - web_search
  - http_get

bash:
  enabled: true
  allowed_commands:
    - python3
    - python
    - pip
    - pytest
    - ruff
    - mypy
    - git
    - ls
    - cat
    - grep
    - find
    - wc
  blocked_commands:
    - "rm -rf"
    - sudo
    - "git push"
  timeout: 120s

memory:
  max_size: 5gb

permissions:
  network:
    - api.anthropic.com
    - pypi.org
    - "*.github.com"
    - docs.python.org
  filesystem:
    - /den/workspace
    - /den/output
    - /den/memory

tasks:
  implement-feature:
    description: |
      Implement the feature described in /den/workspace/feature-request.md.
      Follow the full research → planning → implementation → verification workflow.
      All code must be in /den/workspace/src/.
      All tests must be in /den/workspace/tests/.
      The feature is complete when all tests pass and no TODOs remain.

    phases:
      - name: discovery
        type: research
        questions:
          - id: existing_patterns
            text: >
              What patterns already exist in the codebase
              (at /den/workspace/src/) that this feature should follow?
            required: true
          - id: libraries
            text: >
              What existing libraries or tools would simplify this implementation?
              Check PyPI if needed.
            required: true
          - id: edge_cases
            text: >
              What are the edge cases and error conditions this feature must handle?
            required: true
          - id: test_approach
            text: >
              What is the appropriate testing strategy for this feature?
              Unit tests? Integration tests? Both?
            required: true
        evaluation:
          method: algorithmic
          checks:
            - name: all_answered
              type: all_questions_addressed
              min_words_per_answer: 80
              required: true
            - name: codebase_examined
              type: sources_present
              min_count: 0     # Sources optional for codebase analysis
              required: false
        max_iterations: 3
        cooldown: 10s

      - name: planning
        type: plan
        input_from: discovery
        requirements:
          - "Step-by-step implementation plan"
          - "List of files to create or modify"
          - "Test plan with specific test cases"
          - "Risk mitigation for each edge case found in discovery"
        evaluation:
          method: algorithmic
          checks:
            - name: has_steps
              type: min_list_items
              field: steps
              min_items: 3
              required: true
            - name: has_risks
              type: sections_present
              required_sections: ["risks"]
              required: true
            - name: has_success_criteria
              type: sections_present
              required_sections: ["success_criteria"]
              required: true
            - name: plan_is_detailed
              type: min_word_count
              min_words: 300
              required: true
        approval: auto
        max_iterations: 3
        cooldown: 10s

      - name: implementation
        type: execution
        input_from: planning
        evaluation:
          method: script
          script: |
            #!/bin/bash
            set -e
            cd /den/workspace

            echo "=== Installing dependencies ==="
            pip install -q -r requirements.txt 2>/dev/null || true

            echo "=== Running tests ==="
            python -m pytest tests/ -v --tb=short
            if [ $? -ne 0 ]; then
              echo "FAIL: Tests did not pass"
              exit 1
            fi

            echo "=== Checking for TODOs ==="
            if grep -rn "TODO\|FIXME\|HACK\|PLACEHOLDER" src/ --include="*.py"; then
              echo "FAIL: Found TODO/FIXME/HACK/PLACEHOLDER comments"
              exit 1
            fi

            echo "=== Running type checker ==="
            python -m mypy src/ --ignore-missing-imports 2>&1 | grep "error:" || true
            ERROR_COUNT=$(python -m mypy src/ --ignore-missing-imports 2>&1 | grep -c "error:" || echo 0)
            if [ "$ERROR_COUNT" -gt "5" ]; then
              echo "FAIL: Too many type errors ($ERROR_COUNT)"
              exit 1
            fi

            echo "=== Running linter ==="
            python -m ruff check src/ --exit-non-zero-on-fix
            if [ $? -ne 0 ]; then
              echo "FAIL: Linting issues found"
              exit 1
            fi

            echo "All checks passed"
            exit 0
          script_timeout: 180s
        artifacts:
          - path: /den/workspace/src/
            type: directory
            required: true
          - path: /den/workspace/tests/
            type: directory
            required: true
        max_iterations: 5
        cooldown: 20s
        transitions:
          on_pass:
            goto: next
          on_fail:
            behavior: notify

      - name: verification
        type: verification
        input_from: [discovery, planning, implementation]
        evaluation:
          method: hybrid
          algorithmic_checks:
            - name: tests_pass
              type: script_exits_zero
              script: "cd /den/workspace && python -m pytest tests/ -q"
              required: true
            - name: no_todos
              type: no_todo_comments
              patterns: ["TODO", "FIXME", "HACK", "PLACEHOLDER"]
              paths: ["/den/workspace/src/"]
              required: true
            - name: coverage_acceptable
              type: script_exits_zero
              script: |
                cd /den/workspace
                python -m pytest --cov=src tests/ --cov-fail-under=70 -q
              required: false
          qualitative_checks:
            method: llm-judge
            criteria:
              - "Implementation matches the plan produced in the planning phase"
              - "All edge cases identified in discovery are addressed"
              - "Code is readable with appropriate comments"
              - "No obvious security issues (SQL injection, path traversal, etc.)"
            run_if_algorithmic_passes: true
        max_iterations: 2
        cooldown: 15s
        transitions:
          on_pass:
            goto: done
          on_fail:
            behavior: goto
            goto: implementation
            max_retries: 1

    on_fail: notify
```

---

### 10.2 Research Report Agent

An agent that produces detailed research reports on any topic with full source verification.

```yaml
# research-report-agent.agentfile.yaml

name: research-report-agent
model: claude-sonnet-4-6

system_prompt: |
  You are a research analyst. You produce thorough, well-sourced reports
  that professionals can rely on. You never fabricate sources. You never
  leave sections incomplete. If you cannot find information, you say so
  explicitly rather than guessing.

tools:
  - web_search
  - http_get
  - file_read
  - file_write
  - pdf_read

bash:
  enabled: true
  allowed_commands:
    - wc
    - grep
    - python3
  timeout: 60s

memory:
  max_size: 2gb

cron:
  - schedule: "0 9 * * MON"
    task: weekly-industry-report

tasks:
  research-report:
    description: |
      Produce a research report on the topic in /den/workspace/topic.txt.
      The report must be substantive, well-sourced, and professionally written.
      Save it to /den/output/report-{date}.md.

    phases:
      - name: scoping
        type: research
        questions:
          - id: key_questions
            text: "What are the 5 most important questions to answer about this topic?"
            required: true
          - id: key_sources
            text: "What are the best authoritative sources on this topic?"
            required: true
          - id: recent_developments
            text: "What are the most significant recent developments (last 12 months)?"
            required: true
        evaluation:
          method: algorithmic
          checks:
            - name: questions_answered
              type: all_questions_addressed
              min_words_per_answer: 100
              required: true
            - name: sources_found
              type: sources_present
              min_count: 3
              required: true
        max_iterations: 2

      - name: deep-research
        type: research
        input_from: scoping
        # Research the 5 key questions identified in scoping
        questions: []    # Questions come from scoping phase output dynamically
        evaluation:
          method: algorithmic
          checks:
            - name: substantive_answers
              type: min_word_count
              min_words: 1500   # Total across all answers
              required: true
            - name: source_count
              type: sources_present
              min_count: 8
              required: true
            - name: diverse_sources
              type: unique_sources
              min_unique_domains: 5
              required: true
        max_iterations: 3
        cooldown: 15s

      - name: report-drafting
        type: custom
        input_from: [scoping, deep-research]
        description: |
          Write the full research report using the information gathered.
          Structure: Executive Summary, Background, Key Findings (one section
          per major question), Analysis, Conclusion, References.
        evaluation:
          method: hybrid
          algorithmic_checks:
            - name: word_count
              type: min_word_count
              min_words: 1500
              required: true
            - name: required_sections
              type: sections_present
              required_sections:
                - "executive summary"
                - "background"
                - "key findings"
                - "analysis"
                - "conclusion"
                - "references"
              required: true
            - name: sources_cited
              type: sources_present
              min_count: 8
              required: true
            - name: no_placeholders
              type: no_placeholder_text
              required: true
            - name: output_file_exists
              type: artifacts_exist
              paths: ["/den/output/"]
              required: true
          qualitative_checks:
            method: llm-judge
            criteria:
              - "Executive summary accurately captures the key findings"
              - "Analysis section draws meaningful conclusions from the evidence"
              - "Report is appropriate for a professional audience"
              - "Writing is clear, precise, and free of filler language"
            run_if_algorithmic_passes: true
        artifacts:
          - path: /den/output/report-{date}.md
            type: markdown
            required: true
        max_iterations: 4
        cooldown: 20s

    on_fail: notify
```

---

### 10.3 Data Analysis Pipeline Agent

An agent that processes data files and produces validated analysis outputs.

```yaml
# data-analysis-agent.agentfile.yaml

name: data-analysis-agent
model: claude-sonnet-4-6

system_prompt: |
  You are a data analyst. You analyze datasets methodically, validate
  your findings, and produce structured outputs that downstream systems
  can rely on. You never skip validation steps. You never produce
  output that does not pass the schema check.

tools:
  - file_read
  - file_write
  - csv_analyze

bash:
  enabled: true
  allowed_commands:
    - python3
    - python
    - pip
    - jq
    - wc
    - head
    - tail
  blocked_commands:
    - "rm -rf"
    - sudo
  timeout: 180s

memory:
  max_size: 10gb

cron:
  - schedule: "0 6 * * *"
    task: daily-analysis

tasks:
  daily-analysis:
    description: |
      Analyze the data files in /den/workspace/data/.
      Produce a structured JSON report at /den/output/analysis-{date}.json
      and a human-readable summary at /den/output/summary-{date}.md.

    phases:
      - name: data-validation
        type: custom
        description: |
          Examine the input data files. Verify they are complete, properly
          formatted, and contain expected columns. Report any data quality
          issues found.
        evaluation:
          method: script
          script: |
            #!/bin/bash
            cd /den/workspace/data

            echo "=== Checking data files ==="
            FILE_COUNT=$(ls *.csv 2>/dev/null | wc -l)
            if [ "$FILE_COUNT" -eq 0 ]; then
              echo "FAIL: No CSV files found in /den/workspace/data/"
              exit 1
            fi
            echo "Found $FILE_COUNT CSV files"

            # Check each file has headers and data
            for f in *.csv; do
              ROW_COUNT=$(wc -l < "$f")
              if [ "$ROW_COUNT" -lt 2 ]; then
                echo "FAIL: $f has fewer than 2 rows (header + data)"
                exit 1
              fi
              echo "$f: $ROW_COUNT rows"
            done

            echo "Data validation passed"
            exit 0
          script_timeout: 30s
        max_iterations: 2

      - name: analysis
        type: execution
        input_from: data-validation
        evaluation:
          method: script
          script: |
            #!/bin/bash
            set -e
            cd /den/workspace

            # Verify analysis output exists
            if [ ! -f "/den/output/analysis-$(date +%Y-%m-%d).json" ]; then
              echo "FAIL: Analysis JSON file not found"
              exit 1
            fi

            # Validate JSON schema
            python3 << 'EOF'
import json, sys
from pathlib import Path
from datetime import date

output_file = Path(f"/den/output/analysis-{date.today()}.json")
with open(output_file) as f:
    data = json.load(f)

required_keys = ["date", "record_count", "metrics", "anomalies", "summary"]
missing = [k for k in required_keys if k not in data]
if missing:
    print(f"FAIL: Missing required keys in analysis JSON: {missing}")
    sys.exit(1)

if not isinstance(data["metrics"], dict) or len(data["metrics"]) == 0:
    print("FAIL: metrics field must be a non-empty object")
    sys.exit(1)

if not isinstance(data["anomalies"], list):
    print("FAIL: anomalies field must be an array")
    sys.exit(1)

print(f"Schema valid. Records analyzed: {data['record_count']}")
print(f"Metrics computed: {list(data['metrics'].keys())}")
print(f"Anomalies found: {len(data['anomalies'])}")
sys.exit(0)
EOF

            echo "Analysis validation passed"
            exit 0
          script_timeout: 60s
        artifacts:
          - path: /den/output/analysis-{date}.json
            type: json
            required: true
          - path: /den/output/summary-{date}.md
            type: markdown
            required: true
        max_iterations: 4
        cooldown: 15s

      - name: quality-check
        type: verification
        input_from: [data-validation, analysis]
        evaluation:
          method: hybrid
          algorithmic_checks:
            - name: json_output_valid
              type: format_valid
              format: json
              required: true
            - name: summary_adequate
              type: min_word_count
              min_words: 200
              required: true
            - name: no_placeholders_in_summary
              type: no_placeholder_text
              required: true
          qualitative_checks:
            method: self-judge
            criteria:
              - "Summary accurately reflects the quantitative findings in the JSON"
              - "Anomalies section clearly explains what is unusual and why it matters"
              - "Conclusions are actionable for a business audience"
            run_if_algorithmic_passes: true
        max_iterations: 2
        transitions:
          on_pass:
            goto: done
          on_fail:
            behavior: goto
            goto: analysis
            max_retries: 1

    on_fail: notify
```

---

### 10.4 Content Creation Workflow

An agent for content teams that produces, reviews, and finalizes content through a structured editorial loop.

```yaml
# content-agent.agentfile.yaml

name: content-agent
model: claude-sonnet-4-6

system_prompt: |
  You are a professional content writer and editor. You produce content
  that is engaging, accurate, and appropriate for the target audience.
  You follow the editorial standards in /den/memory/editorial-standards.md.
  Every piece you produce goes through research, drafting, and editing
  before being marked complete.

tools:
  - web_search
  - file_read
  - file_write
  - http_get

bash:
  enabled: true
  allowed_commands:
    - wc
    - grep
    - python3
  timeout: 30s

memory:
  max_size: 3gb
  seed:
    - source: ./editorial-standards.md
      dest: /den/memory/editorial-standards.md
    - source: ./brand-voice-guide.md
      dest: /den/memory/brand-voice-guide.md

cron:
  - schedule: "0 10 * * TUE,THU"
    task: blog-post
  - schedule: "0 14 * * FRI"
    task: weekly-newsletter

tasks:
  blog-post:
    description: |
      Write a blog post on the topic in /den/workspace/brief.md.
      The post must be 800-1200 words, have a compelling title,
      and include 2-3 relevant examples or case studies.
      Save to /den/output/blog-{date}.md.

    phases:
      - name: topic-research
        type: research
        questions:
          - id: audience_interest
            text: "What aspects of this topic are most relevant to our target audience?"
            required: true
          - id: current_angle
            text: "What fresh angle or insight can we offer that is not already covered extensively?"
            required: true
          - id: examples
            text: "What 2-3 specific, recent examples or case studies illustrate this topic well?"
            required: true
          - id: key_takeaways
            text: "What are the 3-5 key takeaways a reader should leave with?"
            required: true
        evaluation:
          method: algorithmic
          checks:
            - name: all_questions_answered
              type: all_questions_addressed
              min_words_per_answer: 80
              required: true
            - name: examples_found
              type: min_word_count
              min_words: 400    # Total — ensures substantive research
              required: true
        max_iterations: 3

      - name: drafting
        type: custom
        input_from: topic-research
        description: |
          Write the full blog post using the research.
          Structure: compelling title, hook paragraph, 3-4 body sections,
          examples woven throughout, conclusion with clear takeaways.
          Length: 800-1200 words. Tone: per editorial standards.
        evaluation:
          method: hybrid
          algorithmic_checks:
            - name: minimum_length
              type: min_word_count
              min_words: 800
              required: true
            - name: maximum_length
              type: max_word_count
              max_words: 1200
              required: true
            - name: no_placeholders
              type: no_placeholder_text
              required: true
            - name: has_title
              type: sections_present
              required_sections: ["#"]   # H1 markdown header
              detection_method: header
              required: true
          qualitative_checks:
            method: llm-judge
            criteria:
              - "Opening paragraph creates a compelling hook that draws the reader in"
              - "Examples are specific, concrete, and clearly relevant"
              - "Tone matches the brand voice guide (read from memory)"
              - "Conclusion clearly states the key takeaways"
              - "Writing is direct — no filler phrases, no hedging unnecessarily"
            run_if_algorithmic_passes: true
        artifacts:
          - path: /den/output/blog-{date}.md
            type: markdown
            required: true
        max_iterations: 4
        cooldown: 15s

      - name: editorial-review
        type: verification
        input_from: [topic-research, drafting]
        evaluation:
          method: hybrid
          algorithmic_checks:
            - name: word_count_in_range
              type: min_word_count
              min_words: 800
              required: true
            - name: not_too_long
              type: max_word_count
              max_words: 1200
              required: true
            - name: file_exists
              type: artifacts_exist
              paths: ["/den/output/"]
              required: true
            - name: no_placeholders
              type: no_placeholder_text
              required: true
          qualitative_checks:
            method: llm-judge
            criteria:
              - "Post delivers on what the title and hook promise"
              - "No factual claims that seem unsupported or suspicious"
              - "Reading experience is smooth — no abrupt transitions"
              - "Post would pass an experienced editor's first review"
            run_if_algorithmic_passes: true
        max_iterations: 2
        transitions:
          on_pass:
            goto: done
          on_fail:
            behavior: goto
            goto: drafting
            max_retries: 1

    on_fail: notify

  weekly-newsletter:
    description: |
      Compile and write the weekly newsletter.
      Include: 3 industry news items with brief commentary,
      1 featured resource or tool, and 1 tip of the week.
      Length: 400-600 words. Save to /den/output/newsletter-{date}.md.

    phases:
      - name: content-gathering
        type: research
        questions:
          - id: news_items
            text: "What are the 3 most significant industry news items from this week?"
            required: true
          - id: featured_resource
            text: "What tool, article, or resource would be most valuable to share this week?"
            required: true
          - id: weekly_tip
            text: "What is one actionable tip relevant to our audience for this week?"
            required: true
        evaluation:
          method: algorithmic
          checks:
            - name: all_answered
              type: all_questions_addressed
              min_words_per_answer: 60
              required: true
            - name: news_sourced
              type: sources_present
              min_count: 3
              required: true
        max_iterations: 3

      - name: writing
        type: custom
        input_from: content-gathering
        evaluation:
          method: hybrid
          algorithmic_checks:
            - name: min_length
              type: min_word_count
              min_words: 400
              required: true
            - name: max_length
              type: max_word_count
              max_words: 600
              required: true
            - name: no_placeholders
              type: no_placeholder_text
              required: true
            - name: has_three_news
              type: min_list_items
              field: news_items
              min_items: 3
              required: false    # Check structure, not count (count verified by word count)
            - name: has_tip_section
              type: sections_present
              required_sections: ["tip"]
              required: true
          qualitative_checks:
            method: self-judge
            criteria:
              - "Each news item has a brief explanation of why it matters"
              - "Featured resource has a clear reason for the recommendation"
              - "Tip is specific and immediately actionable"
              - "Overall tone is warm, direct, and not promotional"
            run_if_algorithmic_passes: true
        artifacts:
          - path: /den/output/newsletter-{date}.md
            type: markdown
            required: true
        max_iterations: 3

    on_fail: notify
```

---

## Appendix A: Loop Architecture Quick Reference

### Phase Types and Their Defaults

```
Type          | Default Eval   | Max Iter | Cooldown | Output
------------- | -------------- | -------- | -------- | -------------------
research      | algorithmic    | 3        | 10s      | {answers, sources}
plan          | algorithmic    | 3        | 10s      | {plan, steps, risks}
execution     | script         | 5        | 20s      | {artifacts, log}
verification  | hybrid         | 2        | 15s      | {verified, gaps}
custom        | (required)     | 3        | 10s      | (user-defined)
```

### Evaluation Method Selection Guide

```
Can the check be expressed as a deterministic function?
    YES -> use algorithmic
    NO  -> continue below

Is the check about structure, format, or measurable properties?
    YES -> use algorithmic (you can express it, keep looking)
    NO  -> continue below

Is self-serving bias a concern (agent judging its own subjective quality)?
    YES -> use llm-judge
    NO  -> use self-judge

Do you have an external validator (test suite, linter, schema checker)?
    YES -> use script
    NO  -> use the evaluator selected above

Do you need both algorithmic and qualitative checks?
    YES -> use hybrid (algorithmic first, qualitative only if algorithmic passes)
```

### Common Checks by Use Case

| Use case | Checks to use |
|---|---|
| Research output | `sources_present`, `min_word_count`, `all_questions_addressed` |
| Document output | `sections_present`, `min_word_count`, `no_placeholder_text`, `format_valid` |
| Code output | `script_exits_zero` (tests), `no_todo_comments`, `linter_passes` |
| Structured data | `schema_valid`, `json_field_values`, `csv_row_count` |
| Any artifact | `artifacts_exist`, `file_modified_recently` |

### Transition Decision Tree

```
Phase passed?
    YES -> on_pass.goto
        = "next"     -> advance to next phase in array
        = "done"     -> task complete, deliver artifacts
        = "<name>"   -> jump to named phase (skip or go forward)

Phase failed?
    NO  -> on_fail.behavior
        = "stop"     -> task fails immediately, write to memory
        = "notify"   -> task fails, write notification file
        = "goto"     -> return to earlier phase (loop-back)
            check: goto_count[target] <= max_retries
                OK  -> go to target phase, decrement budget
                FAIL -> treat as "stop"
```

---

## Appendix B: Agentfile Migration Guide (v1 to v2 loops)

If you have an existing Agentfile using the v1 `loop:` spec, it continues to work unchanged. The single-phase loop is preserved for backward compatibility.

To migrate to the multi-phase loop architecture:

**Before (v1):**
```yaml
tasks:
  build-feature:
    description: "Research and implement the feature..."
    loop:
      max_iterations: 5
      evaluation:
        method: self
        criteria: |
          - Research complete with sources
          - Implementation passes tests
          - No TODOs remain
```

**After (v2 multi-phase):**
```yaml
tasks:
  build-feature:
    description: "Full discovery → planning → implementation → verification flow."
    phases:
      - name: discovery
        type: research
        questions: [...]
        ...
      - name: planning
        type: plan
        ...
      - name: implementation
        type: execution
        ...
      - name: verification
        type: verification
        ...
```

The key benefit of migrating: each phase has its own max_iterations budget and its own evaluation criteria. A 5-iteration single-phase loop that tries to do research and implementation in one go is much less reliable than 4 phases with 2-3 iterations each, where each phase has checks appropriate to its purpose.

---

*This document is the specification for the Loop Architecture. Implementation should follow the Python code in Section 9 and the Agentfile spec in Section 6. Questions and proposed extensions should be reviewed against the design principles in Section 1.*
