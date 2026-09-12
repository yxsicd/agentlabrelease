#!/usr/bin/env python3
"""Scripted participant: propose actions and consume observations over JSONL."""
import json
import sys

request = json.loads(sys.stdin.readline())
for action in request["actions"]:
    print(json.dumps({"type": "tool_call", **action}), flush=True)
    observation = json.loads(sys.stdin.readline())
    if observation["type"] != "tool_result":
        raise ValueError("expected tool_result")
# Intentionally optimistic. The evaluator must use actual service/file evidence.
print(json.dumps({"type": "final", "claimedSuccess": True}), flush=True)
