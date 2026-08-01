# Decision Agent Skill Design

> **Target design, not an installed Skill:** publish the Skill only after the
> stable CLI contracts in this document exist. Today's CLI cannot observe
> general conversation, log arbitrary decisions, or attach corrections to those
> decisions. See [Design Philosophy](design-philosophy.md).

## Purpose

The Skill connects an integrating agent to Decision Agent's continuous decision
loop. It should notice useful decision signals during ordinary work, invoke
Decision Agent at material decision boundaries, log confirmed decisions, and
turn user corrections into future decision behavior.

The Skill is an orchestrator. Decision extraction, persistence, retrieval, and
policy updates belong in the Decision Agent CLI or a future stable tool API, not
in prose duplicated inside `SKILL.md`.

## Draft Trigger Metadata

```yaml
---
name: decision-agent
description: Use Decision Agent during work that reveals user-specific choices, constraints, rejections, trade-offs, or corrections, and when an agent must make a material decision affected by the user's prior judgment. Proactively capture scoped decision signals, consult relevant history before consequential or precedent-setting choices, log confirmed decisions and rationale, and learn why the user would decide differently. Do not use for factual lookup, mechanical processing, generic code review, or trivial reversible choices with no relevant preference.
---
```

Implicit invocation is best-effort. A Skill is not a continuously running
observer. Environments that require the loop on every task should also add an
`AGENTS.md` policy, hook, or future Plugin/MCP integration.

## Trigger Boundary

Invoke implicitly when:

- the user makes or rejects a choice and the reason may matter later;
- the user states a constraint or trade-off that changes what "best" means;
- the agent faces several valid alternatives with user-specific consequences;
- the decision is hard to reverse, will recur, or establishes precedent;
- the user corrects a recommendation or says they would not decide that way.

Do not invoke for:

- factual questions with an externally verifiable answer;
- formatting, copying, or other mechanical transformations;
- low-impact choices that are easy to reverse;
- preferences attributed only to quoted text, a third party, or an artifact;
- actions outside the authority already granted by the user.

## Workflow

### Observe

Scan the current user-authored context for a clear choice, rejection, constraint,
trade-off, example, or reason. Submit only a minimal structured signal with its
source, scope, and confidence. Do not ask "should I remember this?" for every
signal. Do not turn an inference directly into active policy.

### Decide

Before a material choice, send the context and alternatives to Decision Agent.
Use the returned recommendation and evidence to decide when the task is already
delegated; otherwise present it as a proposal. Explain the result concisely and
distinguish an agent decision from a user-confirmed decision.

### Log

After confirmation or execution, record the selected alternative, status,
explainable rationale, and the signal or policy IDs used. Never persist hidden
chain-of-thought.

### Correct and learn

Treat statements such as "I would not choose that," overrides, and changed
decisions as corrections. If the user already gave a reason, do not ask again.
If the reason is missing and material to reuse, ask one natural follow-up. Link
the correction to the original decision and report the narrow future behavior
that changed. Keep unexplained corrections unresolved rather than inventing a
reason.

### Inspect and forget

Use the tool to show applicable memory when the user asks why a choice was made,
what has been learned, or what will be reused. Honor pause, scope changes, and
forget requests without requiring manual JSON editing.

## Target CLI Contract

The stable agent-facing interface should use JSON on stdin and stdout:

```text
decision-agent observe   # store a scoped Signal
decision-agent decide    # propose a choice using relevant memory
decision-agent log       # record a confirmed or executed Decision
decision-agent correct   # attach a Correction and reason
decision-agent explain   # show evidence for a Decision or Policy
decision-agent memory    # list, pause, scope, or forget memory
decision-agent doctor    # report compatibility and runtime readiness
```

`decide` must not imply `log`: proposing and confirming are distinct. All
responses include a contract version and machine-readable IDs. Mutation
commands are idempotent and lock the relevant state scope against concurrent
agents.

The target models are:

- `Signal`: kind, summary, provenance, scope, confidence, status, timestamps;
- `Policy`: text, scope, supporting and contradicting signal IDs, status;
- `Decision`: context, alternatives, selected option, actor, status, rationale,
  evidence IDs, confidence;
- `Correction`: decision ID, corrected choice, reason, scope, resulting changes.

## State and Safety

Store personal decision data outside the installed Skill. Resolve state in this
order: `DECISION_AGENT_HOME`, project configuration, then the OS user-data
directory. Default observations to project scope; promote to global scope only
when the evidence clearly applies across projects.

The Skill must not read, print, rotate, or copy Gateway secrets. LLM use remains
an explicit runtime configuration and must not silently fall back to a different
engine. Decision Agent recommendations never expand permission for external or
destructive actions.

## Packaging and Distribution

Keep the future Skill at `skills/decision-agent/` in this repository. Include
only `SKILL.md`, `agents/openai.yaml`, and a thin compatibility launcher if the
CLI cannot be invoked directly. Keep user state and business logic out of the
Skill directory.

Release the CLI and Skill from the same immutable Git tag. Install the CLI with
`uv tool install` or `pipx`, then install `skills/decision-agent` from the same
tag with the Codex Skill installer. The Skill checks the CLI contract version
with `decision-agent doctor` and refuses incompatible combinations.

Do not publish the Skill until:

- `observe`, `decide`, `log`, `correct`, `explain`, and memory controls have a
  stable contract;
- JSONL/profile dual history persistence is resolved;
- concurrent mutation and retry tests pass;
- trigger and non-trigger prompts pass fresh-agent tests;
- an end-to-end test covers natural observation, decision, correction reason,
  and a changed later decision;
- documentation clearly distinguishes implemented behavior from target design.

A Plugin or MCP server is a later packaging option when reliable structured tool
discovery or one-step installation becomes more important than a standalone
Skill. It is not required for the first distributable version.
