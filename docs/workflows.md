# Workflow Design

## Primary Research Modes

### 1. Landscape Review
- Goal: summarize a scaffold family, target class, or methodology theme
- Inputs: topic, time range, optional source constraints
- Output: concise research memo with key findings and evidence list

### 2. Candidate Comparison
- Goal: compare multiple binders/scaffolds/targets across evidence dimensions
- Inputs: candidate list, target, criteria
- Output: comparison table + recommendation notes + evidence gaps

### 3. Methodology Explainer
- Goal: explain how a database field, structural metric, or annotation method is used
- Inputs: concept, dataset or methodology context
- Output: explanatory note with source-backed definitions and caveats

## Shared Output Rules
- Always separate evidence-backed claims from open hypotheses
- Prefer structured sections over long prose dumps
- Surface missing information and next-step research questions
- Keep source provenance visible whenever possible

## Preferred Evidence Order
1. `search_knowledge`
2. `search_pubmed`
3. `get_uniprot_entry` / `get_pdb_entry`
4. generic web tools only for unresolved gaps

## Suggested Execution Template

### A. Private-first landscape review
1. Query the private FBBP knowledge base for scaffold/target facts.
2. Pull 1-3 PubMed records that confirm or update the private summary.
3. Validate named proteins or structures through UniProt / PDB when identifiers are present.
4. Write a memo with:
   - supported findings
   - evidence table
   - unresolved questions

### B. Candidate comparison
1. Use `search_knowledge` with explicit filters or candidate names.
2. For each candidate:
   - validate the protein accession with UniProt if needed
   - validate structure evidence with PDB if needed
3. Produce a comparison table with:
   - evidence coverage
   - quality caveats
   - recommendation

### C. Methodology explainer
1. Pull the private methodology explanation from `search_knowledge`.
2. If the concept names a structure metric, validate field meaning through PDB references.
3. If the concept names a protein or sequence entity, validate naming through UniProt.
4. End with an explicit "how to use this field" note.
