# CoVUniBind Structured Demo Queries

These queries are intended for the **structured-analysis** path, either through:
- `ragkb ask --engine direct --filter ...`
- DeerFlow + `fbtp-rag` MCP tools

They are based on the converted sample file:
- `llm-rag-knowledge-base/data/hf_covunibind_sample/covunibind_covabdab_binding_ingest.csv`

## Direct `ragkb` Examples

### 1. Show RBD-focused examples
```bash
ragkb ask --question "Show examples of antibodies targeting the RBD domain" --engine direct --filter "epitope_domain=RBD"
```

### 2. Focus on NTD cases
```bash
ragkb ask --question "List NTD-targeting antibody examples with evidence" --engine direct --filter "epitope_domain=NTD"
```

### 3. Restrict by lineage
```bash
ragkb ask --question "Which entries involve BA.2 lineage?" --engine direct --filter "Targets_gene_name=BA.2"
```

### 4. Filter by structure quality
```bash
ragkb ask --question "Show entries with structure resolution under 3.0 A" --engine direct --filter "PDB_Resolution_A<3.0"
```

### 5. Focus on a specific structure
```bash
ragkb ask --question "Summarize the evidence around pdb 8gjm" --engine direct --filter "pdb_id=8gjm"
```

## MCP Tool Examples

### `search_knowledge`
```json
{
  "query": "Show examples of antibodies targeting the RBD domain with structural evidence.",
  "record_type": "csv",
  "filters": ["epitope_domain=RBD"],
  "top_k": 5,
  "include_answer": true,
  "include_evidence": true
}
```

### `search_knowledge` with structure threshold
```json
{
  "query": "Find high-quality structures with strong epitope annotations.",
  "record_type": "csv",
  "filters": ["PDB_Resolution_A<3.0", "target_type=binding"],
  "top_k": 5,
  "include_answer": true,
  "include_evidence": true
}
```

## DeerFlow Prompt Templates

### Prompt 1: Epitope-focused summary
"请基于私有知识库，总结 CoVUniBind 样本中 RBD 表位相关抗体的典型证据模式。请列出代表性结构条目、来源 DOI、结构分辨率，并指出证据空白。"

### Prompt 2: Lineage comparison
"请比较 BA.1、BA.2 和 BA.5 三个 lineage 在当前样本中的抗体证据分布，重点说明表位域、PDB 结构支持和来源文献差异。"

### Prompt 3: Structure quality review
"请筛选出结构分辨率优于 3.0 A 的条目，并总结这些条目在 epitope annotation 上的共同特点。请用表格输出。"

## Notes
- Current sample characteristics:
  - `epitope_domain`: mainly `RBD`, some `NTD`
  - `target_type`: all `binding`
  - `Targets_species_name`: SARS-CoV-2 host entries
- This dataset is best used for **structured retrieval demos**, not as the main RAG evaluation benchmark.

