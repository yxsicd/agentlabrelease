#!/usr/bin/env python3
"""Validate one frozen case's qualification matrix against calibration authority."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from case_qualification import validate_matrix
from case_supply import validate_case_supply


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    args = parser.parse_args()
    case = json.loads(args.case.read_text())
    calibration = json.loads(args.calibration.read_text())
    digest = hashlib.sha256(args.calibration.read_bytes()).hexdigest()
    result = validate_matrix(case, calibration, digest)
    result["caseSupply"] = validate_case_supply(case)
    result["qualificationMatrixSha256"] = hashlib.sha256(
        json.dumps(case["qualificationMatrix"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
