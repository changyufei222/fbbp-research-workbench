---
name: fbtp-deep-research
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

## Preferred Tool Order
1. Use `search_knowledge` first for private FBBP/domain evidence.
2. If the question is literature-heavy, call `search_pubmed`.
3. If the question names a UniProt accession or protein entry, call `get_uniprot_entry`.
4. If the question names a PDB structure, call `get_pdb_entry`.
5. Use generic web tools only when the above sources still leave a gap.

## Preferred Output Shape
- Objective
- Sources Used
- Key Findings
- Evidence Summary
- Gaps / Uncertainties
- Recommended Next Steps

## Domain Guidance
- Prefer precise protein/scaffold terminology.
- Surface publication identifiers or database identifiers when available.
- If evidence conflicts, state that explicitly instead of blending claims.
- If evidence is insufficient, say so and recommend what to verify next.

## Good Prompts
- "调研 knottin scaffold 在 FBBP 场景中的典型特征和代表性证据"
- "总结某类 scaffold 的研究现状，并指出证据空白"
- "围绕某个 target 生成一份结构化研究摘要，附带引用"
- "先查私有 FBBP 知识，再补 PubMed 和 PDB 证据，写一份结构化研究备忘录"
