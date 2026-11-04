# Compact visual evidence

Group related screenshots as an animated AVIF and a frame index for the
evaluation report. This is a Harness/evaluator operation, not a student action
or teacher help. Keep the recorded participant input and structured evidence
intact; a lossy thumbnail is a derived view and is not an exact original.

Each manifest frame must contain `stepId`, `caseId`, `operationId`,
`observationRef`, a relative `path` and the source `sha256`; `capturedAt` is
optional. Paths are relative to the manifest, and images must have the same
aspect ratio. A sequence accepts 1–64 frames and up to 128 MiB of inputs;
use separate batches for longer sequences or different aspect ratios.

```json
{"frames":[{"stepId":"step-1","caseId":"case-1","operationId":"op-1","observationRef":"observation-1","path":"frame-1.png","sha256":"<sha256-of-file>"}]}
```

With Python and an AVIF-enabled Pillow installed, run:

```sh
python3 scripts/agentlab-visual-evidence.py self-check
python3 scripts/agentlab-visual-evidence.py encode --manifest visual-input.json --output visual-preview --width 512
python3 scripts/agentlab-visual-evidence.py verify --index visual-preview/index.json
```

The output contains `sequence.avif` and `index.json`, including source and
decoded-frame hashes, operation links, dimensions, codec and encoding policy.
The default width is 256 pixels, quality 35 and 4:4:4 colour. Increase width or
quality and check a representative frame when text must be readable; the
default is not a legibility guarantee. The fixed one-second playback interval
is only for navigation, not evidence of execution timing.

For an offline Linux tools-pack candidate, use
`scripts/agentlab-visual-evidence-stage.py --wheel <pillow-cp312-manylinux.whl> --wheel-sha256 <verified-sha256> --platform linux-x64 --output <new-directory>`
(or `linux-arm64`). The tool verifies the wheel digest, stages the private
Python dependencies and a `/tools/bin/agentlab-visual-evidence` wrapper; it
does not download packages, publish or activate a pack. Merge into a new full
tools pack without replacing existing tools, then self-check and verify using
the actual target runtime and normal release process. CPython 3.12 is required
by this staged wheel; verify the runtime supplies it. Never modify active
read-only tools in place. A source script, a staged candidate and a deployed
tool are separate states; do not claim availability before a runtime check.

The encoder never deletes or rewrites screenshots and refuses to overwrite an
existing output. Retention and deletion follow the evaluation's evidence and
recovery requirements. Do not substitute previews for byte-exact evidence or
declare successful visual verification from an encoded image alone.
