---
name: fbbp-deep-research
description: Use when the user asks for FBBP literature review, scaffold landscape analysis, evidence synthesis, or a cited research summary about flexible-backbone binding proteins.
metadata:
  author: local
  version: "0.1.0"
---

# FBBP Deep Research

Use this skill for multi-step research tasks about flexible-backbone binding proteins (FBBP), scaffold families, target classes, structural evidence, or methodology-related questions.

## When To Use
- Literature review requests
- Domain landscape summaries
- Research memos or cited reports
- Questions that require combining structured facts and narrative evidence

## Workflow
1. Clarify the research objective and scope.
2. Identify which evidence sources are needed:
   - private RAG / MCP knowledge
   - PubMed for literature grounding
   - UniProt / PDB for protein or structure metadata
   - generic web search only if the above do not cover the request
3. Gather evidence and keep source provenance visible.
4. Separate supported findings from open hypotheses.
5. Produce a concise report with clear sections and next steps.
