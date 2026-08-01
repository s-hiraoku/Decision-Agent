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
- execution of actions outside the authority already granted by the user. The
  Skill may still evaluate such a decision and present a recommendation.

## Workflow

### Filter before persistence or engine use

Before `observe`, `log`, `correct`, or a mutating `memory` operation persists
anything, and before `decide` sends any input to a local or remote decision
engine, run the same sensitive-data filter over every stored or transmitted
field, including decision context, alternatives, rationale, corrections, and
user-provided reasons:

- remove raw conversation or artifact text that is not needed by the decision;
- redact incidental credentials, API tokens, private keys, session cookies, and
  complete payment or government identifiers with a category placeholder;
- reject the mutation or decision request when redaction would leave no useful
  decision meaning, or when highly sensitive personal data has no deliberately
  configured scope;
- do not persist rejected content, a content hash, or the rejected secret value;
  do not send it to the decision engine; return only a non-sensitive rejection
  category.

### Observe

Scan the current user-authored context for a clear choice, rejection, constraint,
trade-off, example, or reason. After the shared persistence filter passes,
submit a minimal structured summary with its source, scope, and confidence. Do
not ask "should I remember this?" for every signal. Do not turn an inference
directly into active policy.

### Decide

Before a material choice, apply the shared filter and send only the passing,
minimized context and alternatives to Decision Agent. Use the returned
recommendation and evidence to decide when the task is already delegated;
otherwise present it as a proposal. Explain the result concisely and distinguish
an agent decision from a user-confirmed decision.

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
reason. When the user rejects an unlogged `decide` proposal, submit the returned
proposal ID and proposal fields with `correct`; after the shared filter passes,
that one mutation atomically creates a `Decision` with `rejected` status and its
linked `Correction`. A retry replays both records under the same `operation_id`
or creates neither.

### Inspect and forget

Use the tool to show applicable memory when the user asks why a choice was made,
what has been learned, or what will be reused. Honor pause, scope changes, and
forget requests without requiring manual JSON editing.

`memory pause` is scoped and acquires that scope's mutation lock. Operations
that acquired the lock first finish before pause succeeds; after the pause
acknowledgement, `observe`, `log`, `correct`, and other non-control mutations in
that scope fail closed, and `decide` and `explain` neither retrieve nor apply its
memory. `memory list`, `forget`, and an explicit scoped `resume` remain
available. Resume takes the same lock and affects only later operations, so no
personal memory is stored or used between the pause and resume acknowledgements.

The target `memory forget` operation is a hard deletion, not a permanent
tombstone containing the forgotten data. Under the scope lock, it atomically
rewrites JSONL without the selected records, removes legacy embedded records,
and follows provenance and record links through all dependent memory. Policies,
Decisions, and Corrections that contain or derive from forgotten evidence are
re-derived or redacted; if they cannot remain meaningful without that evidence,
they are deleted. Forgetting a Decision also removes its linked Corrections.
Retrieval and export must exclude the selected IDs, dependent records, and
derived content as soon as forgetting starts, with no dangling references. An
interrupted compaction resumes before the scope is available again. Only a non-
sensitive operation ID and terminal `forgotten` replay marker may remain to
prevent a timed-out retry from recreating forgotten data; remove the canonical
payload and its digest so retained state cannot test guesses about forgotten
content. The current CLI has no `memory forget` command and still has dual
profile/JSONL persistence, so this behavior is a release blocker rather than a
claim about today's implementation.

## Target CLI Contract

The stable agent-facing interface should use a versioned namespace with JSON on
stdin and stdout:

```text
decision-agent agent-v1 observe   # store a scoped Signal
decision-agent agent-v1 decide    # propose a choice using relevant memory
decision-agent agent-v1 log       # record a confirmed or executed Decision
decision-agent agent-v1 correct   # attach a Correction and optional reason
decision-agent agent-v1 explain   # show evidence for a Decision or Policy
decision-agent agent-v1 memory    # list, pause, scope, or forget memory
decision-agent agent-v1 doctor    # report compatibility and runtime readiness
```

The existing `decision-agent decide <profile> <request>` and `train` commands
remain the frozen numeric MVP and keep their positional-file contract. The
published Skill uses only `agent-v1`; a future incompatible agent contract gets
a new namespace instead of silently changing existing scripts.

`agent-v1 decide` must not imply `log`: proposing and confirming are distinct.
It returns a proposal ID and the filtered proposal fields needed for an atomic
`correct` if the proposal is immediately rejected; the proposal ID alone is not
a durable Decision. All responses include a contract version and machine-
readable IDs. Mutation commands lock the relevant state scope against concurrent
agents.

Every `observe`, `log`, `correct`, and mutating `memory` request includes a
caller-generated `operation_id` (UUID) that is stable across retries of one
logical operation. The idempotency identity is `(scope, command, operation_id)`:

- the same identity and canonical request payload returns the original result
  with `replayed: true` and creates no additional record;
- the same identity with a different canonical payload returns a conflict and
  performs no mutation while the original record exists;
- after forgetting, the terminal `forgotten: true` result takes precedence for
  that identity regardless of the retry payload, because no payload verifier is
  retained; it performs no mutation and reveals no original result fields;
- a timeout is retried with the same `operation_id`; a new logical observation,
  decision, or correction always receives a new one;
- the operation ID, payload digest, and result identity are retained while the
  mutation record exists. After forgetting, only the operation ID and a non-
  sensitive terminal replay marker remain so a delayed retry cannot recreate
  deleted memory.

The target models are:

- `Signal`: kind, summary, provenance, scope, confidence, status, timestamps;
- `Policy`: text, scope, supporting and contradicting signal IDs, status;
- `Decision`: context, alternatives, selected option, actor, scope, status,
  rationale, evidence IDs, confidence;
- `Correction`: decision ID, corrected choice, nullable reason, scope, status
  (`unresolved`, `explained`, or `applied`), resulting changes.

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
- timed-out mutation retries deduplicate by `operation_id`, payload conflicts
  fail closed before forgetting, and any reuse of a forgotten operation identity
  returns only the terminal marker without recreating memory;
- immediate proposal rejection atomically creates one rejected Decision and one
  linked Correction, and retry tests prove it creates no duplicates;
- scoped pause concurrency tests prove no memory is stored, retrieved, or
  applied after pause succeeds and before resume succeeds;
- sensitive-data filtering and hard-deletion tests prove rejected or forgotten
  content and all dependent or derived content are absent from retrieval and
  exports, rejected decision inputs never reach an engine, and forgotten
  payload digests are removed;
- trigger and non-trigger prompts pass fresh-agent tests;
- an end-to-end test covers natural observation, decision, correction reason,
  and a changed later decision;
- documentation clearly distinguishes implemented behavior from target design.

A Plugin or MCP server is a later packaging option when reliable structured tool
discovery or one-step installation becomes more important than a standalone
Skill. It is not required for the first distributable version.
