---
name: fbtp-structured-analysis
description: Use when the user asks for database-style analysis over FBBP structured records, such as comparing candidates, filtering by evidence fields, or explaining annotation fields.
metadata:
  author: local
  version: "0.1.0"
---

# FBBP Structured Analysis

Use this skill for questions that are better answered from structured records than from general literature summaries.

## When To Use
- Field-level filtering or candidate selection
- Comparison across scaffold / target / affinity / structure fields
- Explaining how a structured field is used in downstream analysis
- Requests that resemble database querying or evidence table generation

## Workflow
1. Identify the structured question type.
2. Prefer private knowledge or RAG tools over generic web search when a local dataset is available.
3. If a field or identifier needs public validation, use:
   - `search_pubmed` for paper-level support
   - `get_uniprot_entry` for protein metadata
   - `get_pdb_entry` for structure metadata
3. Extract fields relevant to the request.
4. Present results in a compact table when possible.
5. Note missing fields, low coverage, or uncertain mappings.

## Preferred Output Shape
- Query intent
- Filters or criteria used
- Result table
- Interpretation
- Gaps / caveats

## Domain Guidance
- Keep field names explicit when discussing database logic.
- Distinguish between observed evidence and inferred interpretation.
- If the dataset does not support a claim directly, say what additional source is required.
- Prefer `search_knowledge` for ranking/filtering, then use PubMed/UniProt/PDB tools only to validate or enrich the final explanation.
