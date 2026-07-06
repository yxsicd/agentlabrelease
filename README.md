# AgentLab Release Packages

This repository is the publication target for AgentLab release packages.

## Purpose

- Store GitHub Releases for AgentLab distributable bundles.
- Keep release artifacts separate from the main development repository.
- Provide a stable URL surface for downloading release packages.

## Release Contract

A normal release should include:

- a Git tag such as `agentlab-vYYYYMMDD.N` or a future semver tag;
- release notes describing source commit, target tier, and validation evidence;
- uploaded release artifacts such as binary bundles, runtime bundle archives, manifests, or checksums;
- a manifest that records source repository commit, build profile, artifact names, and validation gates.

Do not use this repository for active source development. Source changes remain in the AgentLab development repository; this repository is for published packages and release metadata.
