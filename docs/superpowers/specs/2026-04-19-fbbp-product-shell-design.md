# FBBP Product Shell Design

Date: 2026-04-19

## Goal

Reframe the current DeerFlow-based runtime as a user-facing `FBBP Research Workbench` so that GitHub readers, demo viewers, and resume reviewers first perceive it as an FBBP research product rather than an upstream showcase.

## Scope

This pass changes only the product shell:

- landing-page brand and metadata
- workspace navigation labels and outbound links
- primary README and supporting docs
- explicit upstream attribution placement

This pass does not rename compatibility-critical internals such as:

- repository directory names
- `/fbtp` route paths
- `fbtp-rag` MCP config keys
- existing script filenames

## User-Facing Direction

- Primary product name: `FBBP Research Workbench`
- Primary message: formal, private-knowledge-grounded FBBP research workflows
- Default user path should not foreground DeerFlow branding
- Upstream provenance should remain visible, but only in dedicated technical documentation

## Design Decisions

### 1. White-label the default surface

The landing page, metadata, hero copy, footer, and workspace menu should speak in FBBP product language. Direct links to `deerflow.tech` and `bytedance/deer-flow` should be removed from the default user path.

### 2. Preserve technical honesty

Instead of hiding the upstream origin, add a dedicated `docs/upstream-engine.md` note that explains the workbench is built on top of DeerFlow and highlights the FBBP-specific modifications.

### 3. Keep runtime compatibility stable

Internal route names and compatibility keys remain unchanged in this pass so the current runtime, scripts, and MCP wiring stay stable.

## Acceptance Criteria

- Browser title and description identify the app as FBBP-focused
- Landing page no longer presents itself as DeerFlow
- Workspace navigation no longer defaults to DeerFlow external properties
- The main workspace README presents the project as `FBBP Research Workbench`
- A dedicated upstream attribution document exists
- Existing frontend tests and runtime script tests still pass
