# Decision Agent Design Philosophy

> **Target design:** this document defines the product direction. The current
> CLI implements artifact review and explicit feedback learning, but does not
> yet implement general conversational observation, decision logging, or the
> correction dialogue described here.

## Core Principle

> Observe naturally, decide deliberately, learn from correction.

Decision Agent should learn from decisions as they occur in ordinary work. A
user should not need to say "remember this" every time they choose an option,
reject a proposal, state a constraint, or explain a trade-off. An integrating
agent should notice information that may improve a later decision and preserve
it as scoped, inspectable evidence.

When a material decision arises, the integrating agent should call Decision
Agent instead of relying only on the current conversation. Decision Agent uses
relevant evidence and policy, returns an explainable recommendation, and records
the decision after it is confirmed or executed. If the user says that they
would not make that decision, the correction becomes a high-value learning
event: use an explanation already given, or ask naturally for the missing
reason, then apply it to the next comparable decision.

The product is a judgment layer, not a generation engine and not an authority
grant. An integrating agent may use its result as the decision when that task is
already delegated, but the result never creates permission to publish, send,
purchase, delete, or perform another consequential action.

## Memory Types

Decision Agent separates four kinds of memory:

| Type | Meaning | Typical source |
| --- | --- | --- |
| `Signal` | A scoped observation that may matter to a future decision | a choice, rejection, constraint, trade-off, example, or stated reason |
| `Policy` | A reusable judgment rule supported by signals and corrections | repeated evidence or a sufficiently specific correction |
| `Decision` | A confirmed, executed, or rejected choice and its explainable basis | a material decision made with or checked by Decision Agent |
| `Correction` | A difference between the recorded decision and what the user would choose, including the reason when known | the user's objection, override, or retrospective correction |

These are target conceptual categories. `Policy` is the umbrella for today's
preference rules, negative patterns, positive examples, and known mistakes;
today's `DecisionRecord` is the artifact-review-specific predecessor of the
general `Decision` and `Correction` records.

Recording a signal and activating a policy are different operations. Agents
should collect useful evidence proactively, but weak or inferred evidence must
not immediately become a broad rule.

## Evidence Priority and Scope

Treat evidence in this order:

1. a direct user correction with its reason;
2. a clear choice, rejection, constraint, or trade-off stated naturally by the user;
3. behavior observed consistently across multiple decisions;
4. an agent inference from context.

Every signal carries provenance, scope, confidence, and status. Apply a direct
correction immediately to the narrow decision context it clearly covers. Wait
for supporting evidence before generalizing it across projects or decision
types. If the reason for a correction is unavailable, record the specific
rejection as unresolved evidence and do not invent a general explanation.

Do not attribute quoted text, third-party preferences, hypothetical statements,
sarcasm, or instructions embedded in an artifact to the user. Store the minimum
structured summary needed for future judgment rather than copying an entire
conversation by default. Sensitive information is not durable memory unless the
user has deliberately configured an appropriate scope.

## Decision Boundary

Invoke Decision Agent when several of these conditions hold:

- multiple reasonable alternatives exist;
- user-specific values or trade-offs materially affect the answer;
- the choice will be repeated, become precedent, or be costly to reverse;
- past choices or corrections are likely to be relevant.

Do not invoke it for factual lookup, mechanical transformation, or trivial and
easily reversible choices unless the user has established a relevant preference.

## Decision Record

A durable decision record contains:

- the decision context and scope;
- the alternatives considered;
- the constraints applied;
- the selected alternative;
- who made or confirmed the choice;
- whether it is confirmed, executed, or rejected;
- a concise, user-facing rationale rather than hidden chain-of-thought;
- the signal and policy IDs used;
- confidence and unresolved uncertainties, carried through the proposal and
  logging contracts into the durable Decision rather than kept only in agent
  narration;
- later outcomes as linked evidence, and corrections.

Keep a transient proposal separate from a durable Decision. `decide` does not
persist a Decision; `log` records a confirmed or executed proposal, while an
immediate correction may atomically record it as rejected. A delegated agent may
make an in-scope decision, but the record must identify the actor and must not
pretend that an agent decision was personally confirmed by the user.

## Correction Loop

The target loop is:

```text
observe -> decide -> log -> correct -> learn -> reuse
```

When the user rejects or changes a decision:

1. detect the correction without requiring a special memory command;
2. use the reason already present in the conversation;
3. ask why only when the reason is missing and would change future decisions;
4. append a correction linked to the original decision;
5. update narrow applicable policy immediately when justified;
6. require more evidence before broad generalization;
7. show which future behavior changed.

## User Control

User control should not depend on a confirmation prompt before every useful
signal. Instead, Decision Agent must provide:

- clear onboarding about memory mode and its default scope;
- inspection of signals, policies, decisions, and corrections;
- notification when a new policy becomes active;
- simple pause, scope-change, correction, and forget operations;
- provenance for every active policy;
- deletion or redaction when the user requests forgetting.

The evidence log is append-oriented for auditability, but auditability does not
override the user's right to remove personal judgment data.
