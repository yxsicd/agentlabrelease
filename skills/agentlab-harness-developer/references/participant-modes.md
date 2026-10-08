# Supervisor and assessed Agent modes

Select independent axes; never infer capabilities from the Agent's name.

| Journey | Participant identity | Meaning |
| --- | --- | --- |
| A: supervisor + AgentLab | Supervisor-managed subagent | The supervisor dispatches an isolated subagent, explicitly selects its input context and controls its lifecycle; the subagent is the assessed remote participant. No separately provisioned model-key-driven Agent service is required. |
| B: supervisor + AgentLab + assessed Agent | `external_brain` | Assessed Agent outside execution sandbox; workspace actions are mediated by Participant MCP. |
| B: supervisor + AgentLab + assessed Agent | `in_sandbox` | Complete assessed Agent runtime inside the declared sandbox, with bounded workspace/tool access. |

## Preferred lightweight A

```text
Supervisor A (Control) -> explicit context cut -> isolated subagent
                                               -> Participant MCP (remote)
                                               -> independent Harness verdict
Supervisor A <- bounded evidence/feedback <------+
```

Use this as the default lightweight flywheel. The supervisor controls dispatch,
admitted tools, budgets, cancellation and continuation, but does not solve the
participant task in its place. Give the subagent a task-only context by default:
the frozen task, declared source/workspace cut, admitted public Skills and tool
contract. Additional knowledge must be explicitly selected and recorded. Do not
fork the entire supervisor conversation; it may contain checker answers, other
Attempts, repair hints, credentials or unpublished evidence.

Record the supervisor/subagent identities, context artifact and digest, parent
Attempt/Session, effective Participant capabilities and every intervention. The
subagent uses only the Attempt-scoped remote interface, never Control or a host
shell. Collect its remote workspace/tool trace and an independent checker result
before returning a lesson. A successful subagent dispatch alone is not a pass.

Subagent delegation is supplied by the supervising Agent framework; it is not a
new AgentLab adapter enum or proof that a particular instance supports remote
assessment. Validate those capabilities first. No second provider key is required
by A; the subagent may use the supervisor's configured model route without
receiving upstream keys. B separately provisions an assessed Agent's independent
model/credential route.

Direct remote assessment of the supervisor can be a separately named experiment,
but is not the preferred A mode and must not be mixed into its subagent scores.
An Agent that has seen private evaluator information is not a blind participant,
even if its token later changes.

The runtime configuration axis is separate:

- `sandbox_remote`: MCP-mediated workspace actions; Session-scoped runtime.
- `sandbox_shared`: process/service reuse within one declared Owner trust domain;
  separate Session threads, contexts and workspaces. No sharing of task state.
- `sandbox_native`: complete runtime in the sandbox with explicitly bounded
  direct workspace access.

Topology, runtime configuration, Agent adapter, provider/model, credential route,
context inheritance and environment restoration are orthogonal. Admit only the
combinations advertised by the exact deployed adapter; these definitions are
not evidence that every combination has been implemented or qualified.

Control MCP owns orchestration and evidence. Participant MCP is restricted to
one Attempt's declared actions and cannot call Control, inspect other Attempts,
read private checker answers or widen credentials. Operator/provider keys remain
in their owning gateways; independently driven participants select an independent
credential route without receiving raw upstream secrets.

Context choices include original Agent/context restoration, a new Agent with
portable integrated context, and a fresh task-only Agent. Choose environment
restoration separately and require its exact/semantic acceptance evidence.

Record interventions, budgets, capability sets and immutable task/source cuts.
Keep direct, mediated and native results separately attributable. Supervisor
repair is not unaided participant success; Agent completion is not independent
evaluation; a remote pass is not native-runtime qualification.
