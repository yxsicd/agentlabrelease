# Calendar sample: preserve draft and evaluated state across restart

Given the admitted Calendar recurrence-inspector ArkUI sample, preserve the free
input draft separately from the last evaluated input/result across own-app process
restart. Reuse its existing parser, retain original example controls, compile and
deploy changed implementation using the supplied offline toolchain, then verify
on the operator-bound Linux emulator. Do not change other applications/settings,
clear application data, or install new tools. Stop and record unadmitted setup.

Acceptance:
1. Evaluate +03,-2 as integers; observe Input:+03,-2 and Result:[3,-2].
2. Edit only draft to TU,+02FR without evaluating. Restart the own app and verify
   draft TU,+02FR separately from Input:+03,-2 / Result:[3,-2].
3. Evaluate that restored draft as weekdays, expecting
   Result:[week=3,ordinal=0;week=6,ordinal=2]. Restart again; verify latest pair.
4. Verify invalid integer 1,0,2 -> Result:[] and one original example button.

Choose your plan and commands. The actual app/device/tool selectors and writable
paths come from admitted run inputs, not this Git branch. If provided a verified
already-installed implementation for a verification-only continuation, do not
reimplement/build/install merely to repeat prior work; disclose supplied inputs.

Produce incremental nonempty verification and raw-evidence JSON with actual
inputs/actions/results, source/build identities, process transitions, errors and
unexecuted checks. Preserve original output or label excerpts. These are task
artifacts, not your final grade. The system independently checks captured traces,
attributes any teacher help and generates the assessment under a frozen policy.
No fixed number of learner-visible phases or mandatory teacher interventions.
