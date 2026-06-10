# Formal Batch Configs

Checked-in formal batch configs define shared execution policy for multiple case ids.

Required fields:

- `batch_slug`
- `runtime_profile`
- `dataset_version`
- `mcp_contract_version`
- `execution`
- `cases`
- `acceptance_profile`

Rules:

- batch configs reference case ids instead of repeating case detail
- `execution.mode` is currently limited to `sequential` or `bounded_parallel`
- batch configs do not store run ids or timestamps
