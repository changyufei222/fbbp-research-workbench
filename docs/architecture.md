# Architecture Overview

## Goal
Turn generic DeerFlow into a domain-specific research assistant for real FBBP tasks.

## Layering Strategy
- **Upstream DeerFlow** provides the agent runtime, sub-agent orchestration, memory, sandboxing, and generic tools.
- **This workspace** provides domain-specific skills, prompts, report templates, and setup conventions.
- **The real-data connector layer** provides private FBBP knowledge, structured records, and literature sources.

## Planned Runtime Flow
1. User submits a research request
2. DeerFlow routes the task to one or more FBBP-specific skills
3. The agent gathers evidence from:
   - browser/web tools
   - local/private MCP servers
   - future domain APIs or structured sources
4. The agent synthesizes findings into a research-style report
5. Output includes citations, unknowns, and suggested follow-up actions

## Phase 1 Deliverable
- One working research path:
  `research request -> evidence collection -> synthesis -> report`

## Phase 2 Expansion
- Add task-specific sub-agents
- Add domain memories for recurring papers/entities
- Add report evaluation and regression cases
