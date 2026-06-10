# Formal Case Configs

Checked-in formal case configs define stable research intent.

Required fields:

- `case_id`
- `title`
- `task_type`
- `runtime_profile`
- `dataset_version`
- `mcp_contract_version`
- `prompt_file`
- `acceptance_profile`

Rules:

- file name must match `<case_id>.yaml`
- case configs do not store timestamps
- case configs do not store output paths
- case configs define the research question, not execution state
