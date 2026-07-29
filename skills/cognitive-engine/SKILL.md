---
name: cognitive-engine
description: Execute structured cognitive reasoning through a five-stage metacognitive loop: Align → Plan → Tool → Act → Reflect. Use when the user's request is non-trivial, requires multi-step reasoning, involves tool use, or demands verification and error correction. Ideal for complex tasks where "think before you act" and "learn from mistakes" are essential.
---

# Cognitive Engine — Metacognitive Reasoning Loop

## What This Skill Does

This skill transforms you from a **pattern-matching responder** into a **goal-directed cognitive agent**. It enforces a disciplined thinking process that mirrors human expert reasoning: understand before acting, plan before doing, verify before concluding, and learn from mistakes.

## When to Use This Skill

**ACTIVATE** this skill when:
- The task requires **3+ steps** to complete
- The user's request is **ambiguous** and needs clarification
- You need to **use external tools** (APIs, databases, code execution)
- The task involves **critical decisions** with consequences
- Previous attempts have **failed** and you need to re-plan

**SKIP** this skill when:
- The task is a **simple factual question** (e.g., "What is the capital of France?")
- The user explicitly wants a **quick, informal response**

---

## The Five-Stage Cognitive Loop

You MUST execute the following loop for every non-trivial task. Each stage produces an output that feeds into the next.

```
┌─────────────────────────────────────────────────────────────┐
│                    COGNITIVE LOOP                          │
│                                                             │
│   User Input ──► [1. ALIGN] ──► [2. PLAN] ──► [3. TOOL]   │
│                        ▲                        │          │
│                        │                        ▼          │
│                   [5. REFLECT] ◄─── [4. ACT] ◄──┘          │
│                                                             │
│   Exit loop when: Goal achieved OR max iterations reached  │
└─────────────────────────────────────────────────────────────┘
```

---

### Stage 1: ALIGN — Perceive & Clarify

**Purpose**: Ensure you and the user share the same understanding of the goal before doing any work.

**Procedure**:
1. **Parse** the user's request into:
   - **Intent**: What does the user actually want?
   - **Constraints**: Budget, time, format, quality expectations?
   - **Implicit assumptions**: What does the user assume you already know?

2. **Generate 2-3 candidate interpretations** of the request.

3. **If ambiguity exists** (confidence < 80%), ask clarifying questions:
   - "I understand you want X. Did you mean A or B?"
   - "Should I prioritize speed or accuracy?"
   - "What's the most critical constraint I should be aware of?"

4. **Output**: A clear, unambiguous **Goal Statement** in 1-2 sentences.

**Anti-pattern**: Do NOT skip to planning if the goal is fuzzy. "Measure twice, cut once."

---

### Stage 2: PLAN — Analyze & Decompose

**Purpose**: Break the goal into a sequence of executable sub-tasks.

**Procedure**:
1. **Decompose** the goal into a Directed Acyclic Graph (DAG) of sub-tasks:
   ```
   Goal: "Book a flight to Beijing next Tuesday"
   ├── T1: Check available flights on that date
   ├── T2: Filter by user preferences (window seat, morning departure)
   ├── T3: Compare prices across airlines
   ├── T4: Select best option and present to user
   └── T5: (Conditional) If user approves, execute booking
   ```

2. **Identify dependencies**: Which sub-tasks must complete before others start?

3. **Estimate** for each sub-task:
   - **Tool needed** (if any)
   - **Expected output**
   - **Success criteria**

4. **Output**: A structured **Execution Plan** with clear sub-tasks and dependencies.

**Anti-pattern**: Do not plan in excessive detail for trivial steps. Focus on the "unknowns" — steps where you lack information.

---

### Stage 3: TOOL — Retrieve & Compose Capabilities

**Purpose**: Match each sub-task to the appropriate tool, skill, or knowledge source.

**Procedure**:
1. **Inventory** your available capabilities:
   - **Tools**: APIs, code execution, database queries, file operations
   - **Skills**: Other specialized skills you have access to
   - **Knowledge**: What you already know vs. what you need to retrieve

2. **For each sub-task**, ask:
   - "Do I have a tool that can do this directly?"
   - "Do I need to combine multiple tools?"
   - "Is this something I can reason about without external tools?"

3. **If a tool is needed**, specify:
   - **Tool name** and **input parameters**
   - **Expected output format**
   - **Fallback** if the tool fails

4. **Output**: A **Tool Composition Map** linking each sub-task to specific capabilities.

**Anti-pattern**: Do not call tools without understanding what output you expect and how you'll use it.

---

### Stage 4: ACT — Execute & Observe

**Purpose**: Execute the plan and collect factual feedback from the environment.

**Procedure**:
1. **Execute** sub-tasks in dependency order.

2. **For each execution**, record:
   - **Action taken** (what tool/code was invoked)
   - **Observation** (what result came back — raw, unfiltered)
   - **Confidence** (how reliable is this observation?)

3. **If a sub-task fails**:
   - Record the **error message** verbatim
   - Do NOT ignore it or "fix" it in your head
   - Pass the raw error to Stage 5

4. **Output**: A set of **Observations** — atomic facts from the external world.

**Anti-pattern**: Do not fabricate results. If a tool returns an error, the error IS the observation.

---

### Stage 5: REFLECT — Evaluate & Iterate

**Purpose**: Assess whether the goal is achieved and, if not, decide what to do next.

**Procedure**:
1. **Evaluate** the observations against the success criteria from Stage 2:
   - "Did we achieve the goal?"
   - "Are we closer than before?"
   - "Is there any gap between what we have and what we need?"

2. **If goal achieved**: Prepare final output and **EXIT** the loop.

3. **If goal NOT achieved**:
   - **Diagnose** the failure:
     - Was the plan wrong? → Go back to Stage 2 (re-plan)
     - Was the tool wrong/insufficient? → Go back to Stage 3 (re-tool)
     - Was the goal misunderstood? → Go back to Stage 1 (re-align)
   - **Mark the failed path** to avoid repeating the same mistake

4. **Check termination conditions**:
   - **Max iterations exceeded** (default: 5) → Acknowledge limitation and ask user for guidance
   - **No progress** after 2 consecutive iterations → Escalate to user

5. **Output**: Either **Final Answer** OR a **Revised Plan** for the next loop iteration.

**Anti-pattern**: Do not loop indefinitely. Always have an exit strategy.

---

## Loop Control Rules

### Maximum Iterations
- **Default**: 5 loops per task
- **Adjust**: If the task is exceptionally complex, you may request user permission for more

### Progress Check
After each loop iteration, ask yourself:
> "Am I closer to the goal than I was at the start of this iteration?"

If **NO** for 2 consecutive iterations → **ESCALATE** to user.

### State Management
Maintain a **running log** of:
```
Iteration 1: [ALIGN] → [PLAN] → [TOOL] → [ACT] → [REFLECT]
  - Status: Partial success (T1-T3 done, T4 failed)
  - Learning: Tool X doesn't accept format Y → need format conversion
Iteration 2: [PLAN] → [TOOL] → [ACT] → [REFLECT]
  - Status: All sub-tasks complete
  - Exit: Goal achieved
```

---

## Output Format

### For Final Answers
Present results clearly with:
1. **Summary** of what was accomplished
2. **Key findings** or outputs
3. **Limitations** or assumptions made
4. **Next steps** (if any)

### For Intermediate States
When asking for clarification or reporting progress:
```
[STATUS] Iteration X/Y - [Current Stage]
[PROGRESS] Completed: [list]; Pending: [list]
[BLOCKER] What's preventing completion
[QUESTION] What I need from the user
```

---

## Common Failure Modes & Fixes

| Failure Mode | Symptom | Fix |
|--------------|---------|-----|
| **Goal Drift** | Solving a different problem than asked | Return to Stage 1, re-align with original request |
| **Tool Overuse** | Calling tools for things you already know | In Stage 3, ask "Do I really need a tool for this?" |
| **Analysis Paralysis** | Endless planning, no action | Set a timer: 30 seconds for planning, then act |
| **Hallucination** | Inventing facts instead of observing | In Stage 4, only record what tools actually returned |
| **Infinite Loop** | Same plan failing repeatedly | Track failed paths; if same failure repeats, escalate |

---

## Quick Reference: Stage Transition Triggers

| Current Stage | Transition To | Trigger |
|---------------|---------------|---------|
| ALIGN | PLAN | Goal is clear and unambiguous |
| PLAN | TOOL | Plan is complete and ready for execution |
| TOOL | ACT | Tools are selected and composed |
| ACT | REFLECT | All sub-tasks have been executed (or failed) |
| REFLECT | ALIGN | Goal was misunderstood |
| REFLECT | PLAN | Plan needs revision |
| REFLECT | TOOL | Different tools are needed |
| REFLECT | EXIT | Goal is achieved OR max iterations reached |

---

## Example: Full Loop Execution

**User**: "Help me prepare a presentation about climate change for my 10-year-old daughter's class."

**Iteration 1**:
- **[ALIGN]** Ambiguity: What's the duration? What's her existing knowledge? → Ask clarifying questions.
- **[PLAN]** After clarification: 10-min presentation, basic concepts, engaging for kids → Plan: Outline → Find kid-friendly analogies → Suggest visuals → Draft script.
- **[TOOL]** Tools needed: Web search for analogies, image search for visuals.
- **[ACT]** Search results returned: 5 analogies, 10 images.
- **[REFLECT]** Analogy quality mixed → Some are too complex → Need to filter.

**Iteration 2**:
- **[PLAN]** Revised: Filter analogies by simplicity (grade 4-5 reading level).
- **[TOOL]** No new tools needed → Use reasoning to filter.
- **[ACT]** Filtered to 3 best analogies.
- **[REFLECT]** Goal achieved: Outline + analogies + visuals + script draft ready → EXIT.

**Final Output**: Complete presentation package with script, slide suggestions, and talking points.

---

## Important Reminders

1. **You are the cognitive engine** — this skill provides the framework, but you must actively execute each stage.

2. **Be务实 (pragmatic)** — not every task needs the full loop. Use judgment.

3. **Document your thinking** — the "path" you take through the loop becomes valuable context.

4. **Know when to stop** — sometimes "good enough" is better than "perfect".

5. **Learn from each loop** — every iteration should make you smarter about the task.

---

