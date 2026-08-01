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

### Filter before persistence, engine use, or return

Before `observe`, `log`, `correct`, or a mutating `memory` operation persists
anything, and before `decide` sends any input to a local or remote decision
engine, run the same sensitive-data filter over every stored or transmitted
field. Before `decide`, `explain`, or `memory list` returns stored content,
validate that each record belongs to the command's effective scope set and run
the filter again over every response field. Covered fields include decision
context, alternatives, rationale, corrections, and user-provided reasons:

- remove raw conversation or artifact text that is not needed by the decision;
- redact incidental credentials, API tokens, private keys, session cookies, and
  complete payment or government identifiers with a category placeholder;
- reject the mutation or decision request when redaction would leave no useful
  decision meaning, or when highly sensitive personal data has no deliberately
  configured scope;
- do not persist rejected content, a content hash, or the rejected secret value;
  do not send it to the decision engine or return it from a read; return only a
  non-sensitive rejection category.

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
explainable rationale, and the signal or policy IDs used. When logging a
`decide` result, submit its proposal ID and complete filtered proposal fields so
the mutation can validate the selected option and persist context and
alternatives without reconstructing conversation. Never persist hidden chain-of-
thought.

### Correct and learn

Treat statements such as "I would not choose that," overrides, and changed
decisions as corrections. If the user already gave a reason, do not ask again.
If the reason is missing and material to reuse, ask one natural follow-up. Link
the correction to the original decision and report the narrow future behavior
that changed. Keep unexplained corrections unresolved rather than inventing a
reason. A pure rejection may leave both the replacement choice and reason
unknown; store it as unresolved rather than requiring either value. When the
user rejects an unlogged `decide` proposal, submit the returned
proposal ID and proposal fields with `correct`; after the shared filter passes,
that one mutation atomically creates a `Decision` with `rejected` status and its
linked `Correction`, plus a unique proposal-consumption mapping shared with
`log`. Concurrent `log` or `correct` calls for the same proposal serialize on
that proposal ID: an identical filtered mutation returns the existing result,
while a different payload conflicts and must target the resulting Decision ID
as a later, separate correction. A retry replays all created records under the
same `operation_id` or creates none. If that Decision is forgotten, replace the
consumption mapping with a non-sensitive terminal marker keyed by proposal ID.
Every later `log` or `correct` for that proposal returns only `forgotten: true`,
regardless of operation ID or supplied proposal fields, and cannot recreate it.

### Inspect and forget

Use the tool to show applicable memory when the user asks why a choice was made,
what has been learned, or what will be reused. Honor pause, scope changes, and
forget requests without requiring manual JSON editing.

Every command that stores, retrieves, or applies memory participates in a scoped
read/write barrier. `decide`, `explain`, and other readers hold a shared lease
through their last use and response construction; mutations hold an exclusive
lease. `memory pause` takes the exclusive lease and drains earlier readers and
writers before it succeeds. After the pause acknowledgement, `observe`, `log`,
`correct`, and other non-control mutations in that scope fail closed, and
`decide` and `explain` neither retrieve nor apply its memory. `memory list`,
`forget`, and an explicit scoped `resume` remain available, but list returns
only non-sensitive control metadata such as scope, paused state, and generation;
it never returns Signals, Policies, Decisions, Corrections, summaries, counts
that reveal their content, or other personal memory while paused. Resume uses
the same barrier and affects only later operations, so no personal memory is
stored, returned, or applied between the pause and resume acknowledgements.
Pause state takes precedence over ordinary mutation replay: while paused, a
retry of `observe`, `log`, or `correct` returns only a non-sensitive `paused`
error and never a cached result. The operation remains replayable after resume.

For a project-scoped `decide` or `explain`, the effective scope set is that
project plus the user's global scope; a global request uses only global scope.
Readers acquire shared leases for every effective scope in canonical scope-key
order and validate each returned record against that set. A paused participating
scope contributes no records, while other active scopes may still contribute.
Responses list every scope and generation actually consulted so callers can
explain whether global or project memory influenced the result. `memory list`
remains limited to the single envelope scope unless the caller makes separate
requests.

Before `log` or a proposal-based `correct` persists cross-scope `evidence_ids`,
it computes every referenced scope, acquires the destination scope's exclusive
lease and each other referenced scope's shared lease in canonical scope-key
order, then revalidates that every evidence record is present, active, and in an
allowed effective scope. Missing, paused, moved, or forgotten evidence returns
`evidence_conflict` without mutation. This prevents a concurrent forget or scope
move from creating dangling references.

The target `memory forget` operation is a hard deletion, not a permanent
tombstone containing the forgotten data. Forget and scope-changing operations
compute the provenance closure of affected scopes, acquire every scope's write
barrier in canonical scope-key order, then revalidate the closure and retry if
it expanded. This prevents deadlocks and covers dependencies such as a project
Signal supporting a global Policy.

Deletion linearizes only after every required write barrier is acquired. Readers
that already hold a shared lease may finish before that point; afterward no
reader can return or apply the pre-forget state. Under those barriers, forget
atomically rewrites JSONL without the selected records, removes legacy embedded
records, and follows provenance and record links through all dependent memory.
Policies, Decisions, and Corrections that contain or derive from forgotten
evidence are re-derived or redacted; if they cannot remain meaningful without
that evidence, they are deleted. Forgetting a Decision also removes its linked
Corrections.
For every deleted, redacted, or re-derived record, forget also replaces each
affected operation entry with the terminal `forgotten` marker and removes its
original payload, digest, result identity, and cached result; replay can never
return a pre-forget representation even when a sanitized record survives.
If an affected Decision is proposal-backed, the same transaction terminalizes
its proposal-consumption mapping and removes the proposal verifier and cached
result even when the sanitized Decision survives. Later proposal-ID requests
return only `forgotten: true` and cannot replay pre-forget fields.
Retrieval must exclude the selected IDs, dependent records, and derived content
from the deletion linearization point onward, with no dangling references. An
interrupted compaction resumes before any affected scope is
available again. Only a non-
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
decision-agent agent-v1 memory    # list, pause, resume, scope, or forget memory
decision-agent agent-v1 doctor    # report compatibility and runtime readiness
```

Each invocation reads exactly one UTF-8 JSON object from stdin and writes
exactly one JSON object to stdout. The common request envelope is:

```json
{
  "contract": "agent-v1",
  "request_id": "caller UUID",
  "scope": {"kind": "project", "id": "stable opaque ID"},
  "operation_id": "caller UUID for mutations only",
  "expected_generation": 4,
  "input": {}
}
```

`contract`, `request_id`, and `input` are always required. `scope` is required
except for `doctor`; global scope is `{"kind":"global","id":"user"}`.
`operation_id` is required only for `observe`, `log`, `correct`, and memory
`pause`, `resume`, `scope`, or `forget`. `expected_generation` is required for
pause and resume; `scope` instead requires source `expected_generation` plus
input `target_expected_generation`; forget omits it. Unknown fields or enum
values fail validation. UUIDs use canonical RFC 4122 text, generations are
unsigned 64-bit integers, opaque IDs are 1–256 UTF-8 bytes, each free-text field
is at most 16 KiB, arrays contain at most 100 items, and the complete request is
at most 256 KiB. Confidence is a JSON number from 0 through 1. Except where
marked optional or nullable below, every listed field is required and additional
input fields are rejected.

Command-specific `input` fields are:

- `observe`: `kind` (`choice`, `rejection`, `constraint`, `tradeoff`, `example`,
  or `reason`), `summary`, `provenance` (`source` is `user_statement`,
  `user_action`, or `agent_inference`, plus opaque `reference`), and
  `confidence`; inferred provenance must reference its user-authored basis and
  remains lower-priority evidence that cannot directly activate a Policy;
- `decide`: `context`, two or more `alternatives` (`id`, `label`, optional
  `details`) with unique IDs, and optional `constraints` string array;
- `log`: `selected_option`, `actor` (`user` or `agent`), `status` (`confirmed`
  or `executed`), `rationale`, `evidence_ids` string array, `confidence`, and
  either a complete `proposal` object or both `context` and `alternatives`; a
  proposal has the same fields defined for `correct`, and its confidence must
  match the top-level value; the two forms are mutually exclusive. Rejection is
  accepted only by `correct`, which atomically creates the linked Correction.
  The explicit non-proposal form also accepts optional `constraints`;
- `correct`: nullable `decision_id`, nullable `proposal` (`proposal_id`,
  `context`, `alternatives`, `recommended_option`, `rationale`, `evidence_ids`,
  `confidence`, optional `constraints`), nullable `corrected_choice`, and
  nullable `new_alternative` (`id`, `label`, optional `details`), and nullable
  `reason`; exactly one of `decision_id` or `proposal` is required, and either
  correction field may be null for a pure rejection;
- `explain`: `target_type` (`decision` or `policy`) and `target_id`;
- `memory`: `action` (`list`, `pause`, `resume`, `scope`, or `forget`); list
  accepts optional `limit` (1–100, default 50), nullable opaque `cursor`, and
  optional `types` array containing `signal`, `policy`, `decision`, or
  `correction`; `forget`
  requires a non-empty `record_ids` string array; `scope` requires non-empty
  `root_record_ids`, `target_scope`, and `target_expected_generation`; pause and
  resume take no other fields;
- `doctor`: no fields.

Successful responses use this envelope:

```json
{
  "contract": "agent-v1",
  "ok": true,
  "request_id": "echoed caller UUID",
  "scope": {"kind": "project", "id": "stable opaque ID"},
  "generation": 5,
  "consulted_scopes": [
    {"scope": {"kind": "project", "id": "stable opaque ID"}, "generation": 5}
  ],
  "result": {},
  "replayed": false
}
```

`scope` and `generation` are omitted only by `doctor`. `consulted_scopes` is a
required array of `{scope, generation}` pairs for `decide` and `explain`, in
canonical scope-key order, and omitted by other commands. Every mutation result
has `affected_scopes`, a canonical array of every changed scope and its post-
commit generation; single-scope mutations return one element, while scope moves
and cross-scope forget return all changed scopes. Mutation results also include
created record IDs; `decide` returns `proposal_id`, filtered proposal fields,
recommendation, evidence IDs, and confidence; `explain` and list return filtered
records; a successful active list returns `items` in ascending `(created_at,
id)` order and nullable `next_cursor`; memory controls return current state and
generation. Replays set `replayed` and obey the pause, forget, and generation
rules below.

Errors after envelope validation use the same `contract`, `request_id`, and
applicable scope metadata with `ok: false` and
`error: {"code", "message", "retryable"}`. For malformed JSON or an invalid or
missing common field, the server still emits one JSON error with
`contract: "agent-v1"`, `request_id: null` unless the supplied value is a valid
UUID, and no scope metadata. Stable codes are
`invalid_request`, `unsupported_contract`, `sensitive_rejected`, `paused`,
`not_found`, `forgotten`, `operation_conflict`, `generation_conflict`,
`scope_dependency_conflict`, `proposal_conflict`, `evidence_conflict`,
`stale_cursor`, `stale_control`, and `runtime_unavailable`.
Validation and contract errors exit 2; state, idempotency, pause, scope, and
generation conflicts exit 3; privacy rejection exits 4; missing or forgotten
targets exit 5; runtime failure exits 6. Success, including safe replay, exits
0. Diagnostics go to stderr; failures never emit a partial success or mutation.
A conflict response returns only non-sensitive identity and current control
metadata, never either payload.

The existing `decision-agent decide <profile> <request>` and `train` commands
remain the frozen numeric MVP and keep their positional-file contract. The
published Skill uses only `agent-v1`; a future incompatible agent contract gets
a new namespace instead of silently changing existing scripts.

`agent-v1 decide` must not imply `log`: proposing and confirming are distinct.
It returns a proposal ID and the filtered proposal fields needed for an atomic
`correct` if the proposal is immediately rejected; the proposal ID alone is not
a durable Decision. All responses include a contract version and machine-
readable IDs. Commands that store, retrieve, or apply memory use the relevant
scope's read/write barrier; proposal consumption also uses a unique proposal-ID
constraint.

Every `observe`, `log`, `correct`, and mutating `memory` request includes a
caller-generated `operation_id` (UUID) that is stable across retries of one
logical operation. The idempotency identity is `(scope, command, operation_id)`:

The compared canonical mutation payload is the filtered command-specific
`input` plus any expected-generation fields, serialized with RFC 8785 JSON
Canonicalization Scheme rules. It excludes `request_id`, `operation_id`, JSON
member order, whitespace, and other per-attempt transport metadata. A retry may
use a fresh `request_id`; changing any compared semantic field is a conflict.
Before canonicalization, `record_ids` and `root_record_ids` are treated as
unordered sets: reject duplicates and sort by opaque ID. Semantic arrays such as
`alternatives` retain their submitted order.

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

Scoped state has a monotonically increasing generation that advances on every
committed data or control mutation. `pause` and `resume` requests include the
caller's expected generation and perform a compare-and-set under the write
barrier. Their responses always include the current state and generation.
Replaying either control operation re-reads that state: it returns the original
success only while its resulting generation is still current; otherwise it
returns `stale: true` with non-sensitive current control metadata and never
claims that the old state is active.

`memory scope` moves records; it does not change a client default, copy records,
or change unrelated records. Every root must belong to the envelope scope and
the target must differ. The server expands those roots to the complete
referential closure, including any number of linked records, proposal mappings,
operation metadata, and prior move-lineage markers; callers never enumerate
internal state or the full closure. Under every discovered lineage, source, and
target barrier, the command revalidates the closure, compares the supplied
source and target generations, then atomically rewrites the scope of the full
closure. Original operation identities are never re-keyed into the target scope:
each becomes a non-
sensitive `moved: true` terminal marker in the source scope, and moved records
retain an internal provenance pointer to that marker. A delayed original retry
therefore cannot recreate the record, and an unrelated target-scope operation
with the same UUID cannot collide. If the server cannot resolve a complete,
consistent closure, it returns `scope_dependency_conflict` with non-sensitive
missing record IDs and moves nothing.

For a moved proposal-backed Decision, the same transaction leaves a non-
sensitive `moved: true` proposal marker in the source scope and creates the live
proposal-to-Decision mapping in the target. A delayed source `log` or `correct`
returns only the moved marker; it never returns target content or recreates the
Decision. Any existing target mapping for that proposal ID causes
`proposal_conflict` before mutation.

Every scope move also updates the non-sensitive move lineage for all earlier
source markers in the selected records' history. Replaying a scope move follows
that lineage under the applicable barriers and never returns cached generations.
If the records still reside in the requested target, it returns `replayed: true`
with freshly read `affected_scopes`; if they moved again, it returns
`stale_control` with only non-sensitive current scope and generation metadata;
if forgotten, the terminal forgotten rule takes precedence.

An active list cursor is an opaque, integrity-protected token bound to contract,
scope, generation, type filter, and the last `(created_at, id)` key; it contains
no record content. Pagination holds the shared lease only for one page. Reusing
a cursor after the scope generation changes returns `stale_cursor`, requiring a
restart, so a traversal never silently mixes snapshots. A paused list ignores
record pagination fields and returns only the control metadata defined above.

The target models are:

- `Signal`: kind, summary, provenance, scope, confidence, status, timestamps;
- `Policy`: text, scope, supporting and contradicting signal IDs, status;
- `Decision`: context, alternatives, selected option, actor, scope, status,
  rationale, evidence IDs, confidence, and optional constraints;
- `Correction`: decision ID, corrected choice, nullable reason, scope, status
  (`unresolved`, `explained`, or `applied`), resulting changes. Corrected choice
  is nullable for a pure rejection; the status remains `unresolved` while the
  reusable replacement or reason is unknown.

Alternative IDs are unique within each request and durable Decision.
`recommended_option` and `selected_option` must equal exactly one submitted
alternative ID. A non-null `corrected_choice` must equal one alternative ID on
the referenced Decision or submitted proposal, or the ID of the supplied
`new_alternative`. A new alternative ID must not collide with an existing one;
when supplied, `corrected_choice` must equal its ID. It is stored on the
Correction and added to the Decision's considered choices when the correction
is applied. Unknown, mismatched, or duplicate IDs fail with `invalid_request`
before engine use or mutation.

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
- schema conformance tests cover every request, success, error, exit code,
  unknown field, required field, and command-specific result in the JSON
  contract;
- JSONL/profile dual history persistence is resolved;
- concurrent mutation and retry tests pass;
- timed-out mutation retries deduplicate by `operation_id`, payload conflicts
  fail closed before forgetting, and any reuse of a forgotten operation identity
  returns only the terminal marker without recreating memory;
- idempotency canonicalization tests vary request IDs, member order, whitespace,
  record-ID permutations, duplicates, and semantic arrays or fields to
  distinguish replay, validation failure, and conflict;
- immediate proposal rejection atomically creates one rejected Decision and one
  linked Correction, and concurrent proposal consumption by `log` or `correct`
  creates no duplicate Decision across different operation IDs or after its
  terminal proposal marker is forgotten;
- scoped pause concurrency tests prove no memory is stored, retrieved, or
  applied after pause succeeds and before resume succeeds, including reads that
  began before pause;
- pause and resume replay tests prove stale operations report the current scope
  generation, ordinary cached mutation results stay hidden while paused, and
  paused list tests expose only non-sensitive control metadata;
- sensitive-data filtering and hard-deletion tests prove rejected or forgotten
  content and all dependent or derived content are absent from retrieval, every
  returned field is scope-checked and filtered, rejected decision inputs never
  reach an engine, and forgotten payload digests, cached results, and replay
  metadata for every affected record are removed or terminalized;
- proposal-backed re-derivation tests prove forget terminalizes proposal
  mappings and removes their verifiers and cached results;
- forget race tests cover readers that precede the deletion linearization point
  and deterministic barrier acquisition for cross-scope dependencies;
- scope tests prove explicitly selected roots and their server-expanded closure
  move atomically, including closures over 100 records; source replay markers
  prevent delayed recreation, target UUID and proposal collisions fail before
  mutation, and proposal mappings cannot recreate or expose moved Decisions;
- multi-scope response tests require complete, canonical `affected_scopes`, and
  scope replay tests cover unchanged targets, later moves, and forgetting;
- effective-scope tests cover project-plus-global reads, paused-scope exclusion,
  canonical multi-scope leasing, the `consulted_scopes` wire field, and reported
  generations;
- cross-scope mutation races prove `log` and proposal-based `correct` revalidate
  evidence under all leases and never commit dangling references;
- list pagination tests cover stable ordering, bounds, filters, paused output,
  tampered cursors, and generation changes between pages;
- trigger and non-trigger prompts pass fresh-agent tests;
- provenance and alternative-reference tests cover inferred evidence priority,
  duplicate IDs, explicit-log constraints, new correction alternatives, and
  every recommendation, selection, and correction path;
- an end-to-end test covers natural observation, decision, correction reason,
  and a changed later decision;
- documentation clearly distinguishes implemented behavior from target design.

A Plugin or MCP server is a later packaging option when reliable structured tool
discovery or one-step installation becomes more important than a standalone
Skill. It is not required for the first distributable version.
