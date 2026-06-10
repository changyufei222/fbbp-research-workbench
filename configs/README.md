# Configuration Notes

This workspace does not replace DeerFlow's full `config.yaml`. Instead, it generates runtime-owned config files under `generated/` and points DeerFlow at this workspace's custom skills and MCP extensions by default.

## Recommended Setup Flow
1. Run `scripts/prepare_deerflow_config.ps1`
2. Open `generated/fbbp.config.yaml`
3. Fill in the required model settings and API keys
4. Review `generated/extensions_config.fbbp.json` only if you want to add or remove MCP servers
5. Start DeerFlow with `DEER_FLOW_CONFIG_PATH` and `DEER_FLOW_EXTENSIONS_CONFIG_PATH`

## Formal Run Configs
- `formal_cases/` contains stable case definitions
- `formal_batches/` contains stable batch definitions
- `runtime_profiles/` contains shared runtime profiles for formal runs

## DeerFlow Extension Config
- Template file: `extensions_config.fbbp.example.json`
- Generated runtime file: `../generated/extensions_config.fbbp.json`
- The startup helpers now point DeerFlow at the generated extension config automatically.
- Adjust the generated file only if you need optional MCP integrations beyond the built-in FBBP private knowledge server.

## Minimum Configuration Checklist
- At least one working model in `models:`
- A valid sandbox mode for your environment
- `skills.path` pointing to this workspace's `skills` directory
- `generated/extensions_config.fbbp.json` containing the MCP servers you want active

## Phase 1 Tooling Recommendation
- Keep the toolchain narrow at the beginning:
  - built-in web search / fetch
  - file read / write tools
  - one private MCP source (`fbbp-mcp-rag-server`) once available

## Notes
- Keep your generated config out of version control
- Prefer adding one real knowledge connector first, then expanding later

