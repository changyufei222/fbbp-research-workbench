# Upstream Engine Provenance

## Summary

`FBBP Research Workbench` is the product-facing layer for this project. Its runtime is built on top of an upstream DeerFlow-based engine, but the default user experience, formal workflows, private retrieval path, and domain-facing outputs are defined in this repository.

## What Stays Upstream

The following engine capabilities remain upstream-aligned:

- LangGraph-based agent runtime
- gateway and thread execution model
- frontend workspace shell and app routing foundation
- sandbox, skills, memory, and MCP integration plumbing

## What Becomes Product-Specific Here

This repository owns the FBBP-facing layer:

- FBBP assistant prompt and custom skills
- formal cases, formal batches, and runtime profiles
- formal console and atlas-oriented outputs
- private FBBP MCP integration and live query workflow
- product-facing docs, summaries, and acceptance artifacts

## Boundary Rule

For GitHub, demos, CVs, and paper material, the project should be described as `FBBP Research Workbench`.

For engineering transparency, the implementation can be described as:

> Built on a DeerFlow-based research engine, with an FBBP-specific product shell, private retrieval contract, and formal research workflow layer.

## Why This Split Exists

This split keeps the project honest and maintainable:

- readers immediately understand the product is yours
- the technical origin is still documented
- compatibility-critical internals do not need risky renaming during the current stabilization phase
