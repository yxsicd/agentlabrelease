#!/usr/bin/env python3
"""Bind a pre-acquired OHPM seed to a fresh project and invoke its owning verifier."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--seed-source", type=Path, required=True)
    parser.add_argument("--seed-output", type=Path, required=True)
    parser.add_argument("--harmony", type=Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve(strict=True)
    source = args.seed_source.resolve(strict=True)
    output = args.seed_output.resolve()
    if output.exists() or output.is_symlink():
        raise SystemExit("seed output already exists; inspect the original operation")
    if output.is_relative_to(project) or output.is_relative_to(source):
        raise SystemExit("seed output must be outside the project and source")
    if (project / "oh_modules").exists() or (project / "oh_modules").is_symlink():
        raise SystemExit("project already contains oh_modules; use a fresh workspace")
    for path in source.rglob("*"):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise SystemExit("seed contains a symlink or special file")
    manifest = json.loads((source / "seed.json").read_text())
    if set(manifest) != {"schema", "inputs", "packages"} or manifest["schema"] != "harmony.offline_seed.v1":
        raise SystemExit("unsupported seed manifest")
    paths = [project / "oh-package.json5", *sorted(project.glob("*/oh-package.json5")),
             project / "oh-package-lock.json5"]
    if not paths[0].is_file() or not paths[-1].is_file():
        raise SystemExit("project manifest and lockfile are required")
    manifest["inputs"] = {str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in paths if p.is_file()}
    shutil.copytree(source, output)
    (output / "seed.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    # The owning build-kit verifies lock specs, archive hashes and exact extracted
    # files before it installs anything. A manifest alone is not qualification.
    result = subprocess.run([str(args.harmony), "deps", "--project", str(project),
                             "--ohpm-seed", str(output)], check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
    print(json.dumps({"schema": "agentlab.harmony_locked_deps_preflight.v1",
                      "status": "verified_by_build_kit", "inputs": manifest["inputs"]}, sort_keys=True))


if __name__ == "__main__":
    main()
