# Upstream Notes

- Intended portfolio repo name: `fbbp-research-workbench`
- Current local workspace name: `fbbp-research-workbench`
- Legacy compatibility shell: `../deerflow-fbtp-research-agent`
- Reason for keeping the legacy shell: this exFAT workspace cannot host NTFS junctions or symlinks, so compatibility is preserved with wrapper files instead
- Clean upstream baseline: `../upstream-deerflow`
- Upstream repository: `https://github.com/bytedance/deer-flow`
- Current upstream local HEAD: `6ae7f0c`
- Upstream license: `MIT`

## What This Workspace Owns
- FBBP-specific skills
- research prompts and templates
- setup scripts and config guidance
- future report examples and evaluation assets

## What Stays Upstream
- DeerFlow core backend/frontend implementation
- generic skill/tool/runtime framework
- sandbox, memory, and orchestration primitives

