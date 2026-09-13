# Engineering knowledge seed

Run `python3 examples/knowledge-seed/run.py --root /tmp/knowledge-experiment`.
The `knowledge-seed.yml` Action uses published AgentLab Session provisioning and
MCPGit services, not a local database substitute. It creates six AgentLab-owned
business tables: knowledge_skills, knowledge_nodes, knowledge_edges,
knowledge_links, knowledge_tasks and knowledge_evaluations. Markdown knowledge
lives in stable Skill rows. The Action inserts an initial cut, updates those same
rows, restarts storage and independently queries both immutable versions.

The deterministic builder is a replaceable Mock participant. It parses a small
cross-file Python fixture, records syntactic call facts without claiming resolved
semantic dependencies, constructs a discount task and verifies baseline failure,
reference success, boundary mutation failure and regression mutation failure.
All compiler/test output and source observations are captured without redaction.
`--source PATH` can extract Python facts from an existing project; it does not
invent calibrated tasks for that source.

The Action also accepts `builder=mini` to run the real captured builder using
its isolated runtime and operator Gateway. It reads the source/fact/vocabulary
seed and proposes Markdown for the frozen Skill identities. Source facts remain
operator-generated. Semantic draft quality is not declared verified merely because
the Agent submits. Model transport and tool evidence enter the same capture path.

This first executable tier establishes the data/iteration contract. It does not
claim Harmony analysis, a qualified strong-model Harmony builder, native MCPGit SkillDocument
format, full SessionFS Workspace capture or an autonomous improving flywheel.
The Markdown business-row representation is canonical for this experiment;
knowledge-package.json is the builder's captured proposal, not a second live
knowledge authority.

Next adapters must bind both HarmonyOS_Samples repositories to exact commits,
extract ArkTS symbols and dependencies, have a strong builder consume the facts
and vocabulary seed, then independently calibrate candidate tasks before freezing
assessment inputs. Evaluation feedback revises the same Skill identities in the
next cut; active assessment versions remain frozen. The release repository owns
public adapters and workflows; AgentLab owns execution, lineage and capture.
