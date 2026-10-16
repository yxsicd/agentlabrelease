# Native Host network preparation

Use the fixed public controller descriptor selected by the deployment Skill.
This prepares a local Docker network before a complete instance exists. Actual
local Host/operator permission, a qualified component registry and fresh kernel,
DNS and selected-daemon inventory are required. It grants no application Owner,
Session, authentication or Ready authority.

Select the intended daemon explicitly through the operator's existing private
Docker endpoint configuration. Never switch the shared default context or adopt
a resource from another daemon because its name matches.

Prepare a new caller-owned private mode0700 input directory. The request file
is private mode0600. Its exact contract is `agentlab.deploy_preparation_request.v1`
with these required fields and no extra fields:

| Field | Required value |
| --- | --- |
| `schema` | `agentlab.deploy_preparation_request.v1` |
| `project` | The selected instance's native safe name |
| `target` | Exact `current.target` from the actual qualified registry: `daemonId`, `platform`, `lockSha256` |
| `inventorySha256` | The actual registry's `qualifiedInventoryHashes[target.lockSha256]` |
| `network.name` | The intended native safe network name |
| `network.requiredAddresses` | Integer from 1 through 250 |
| `network.identity` | `{"state":"absent"}` for this new creation workflow |

The existing identity form is `{"state":"existing","networkId":"ACTUAL_64_HEX_ID"}`
for binding an observed existing identity; it does not authorize creation,
adoption or migration. Do not invent target or digest values. Registry values,
request fields and an intent file select scope; they are never Host permission.
The input directory, component registry and new journal must be separate private
roots. Preserve the request bytes and operation ID throughout.

Run the original intent once at generation0, then the SAME original operation's
Host preparation at generation1. These are the selected executable's declared
commands; replace all uppercase paths/IDs with the actual private values:

```text
CONTROLLER deploy prepare-network-intent REQUEST --registry REGISTRY --journal NEW_JOURNAL --operation NEW_OPERATION --expected-generation 0
CONTROLLER deploy prepare-network REQUEST --registry REGISTRY --journal NEW_JOURNAL --operation NEW_OPERATION --expected-generation 1
```

The controller captures live inventory itself and performs fresh checks before
creation. It records generation2 durably before its one create attempt and
records the returned physical ID separately at generation3. Generation4 means
that exact newly created network passed the owning physical/policy checks.
Record the actual result, independently inspect that physical ID and routes,
and bind it into later full-instance inputs. Do not create it again.

A timeout or lost result requires original-operation readback. Do not change the
request, reuse another operation ID, adopt labels as a missing success receipt,
retry creation or delete a resource to force success. The declared
`observe-network-preparation` command reads that same request/journal/operation
at its actual recorded generation. A generation3 result may be completed only
through the existing `finish-network-preparation` action after its real policy
and Host prerequisites pass; it does not create another network. Generation2
with no recorded successful ID cannot be promoted from labels.

The [actual native Linux receipt](evidence/hwlinux-isolated-network-prepared-20261016.json)
records an isolated-daemon generation4 result and independent bridge/routes.
The older default-daemon generation3 network and its extra route stay intact.
Neither result qualifies an application login, SessionFS Ready, a complete
instance, two-host cold installation or Harmony feedback.
