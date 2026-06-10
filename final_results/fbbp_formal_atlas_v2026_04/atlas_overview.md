# FBBP Formal Atlas Overview

## Dataset Identity
- Dataset name: `FBBP`
- Dataset version: `fbbp_private_v2026_04`
- Runtime profile: `local_formal`
- DB identity: `fbbp_formal_pgvector`
- Build ID: `fbbp-2026-04-formal`
- Source registry version: `2026-04-16`
- Package version: `2026.04.18`

## Headline Metrics
- Scaffold classes: `12`
- Interaction cards analyzed: `1996`
- Protein cards analyzed: `1996`
- Raw records referenced: `86564`
- Target-linked interaction rows: `41`
- Registered sources in appendix: `34`

## Scaffold Atlas
| Scaffold | Interaction rows | Target-linked rows | Top targets | Representative proteins |
|---|---|---|---|---|
| adnectin | 456 | 37 | CD8A; EGFR; ICAM-2 | Tencon; 10Fn3; Fibronectin type III domain |
| cyclotide | 404 | 2 | OPRK1 | MCoTI-II; Momordica cochinchinensis trypsin inhibitor-II; Kalata B2 |
| knottin | 310 | 1 | SCN9A | MCoTI-II; Agouti-related protein; oMCoTI-II |
| obody | 268 | 0 | n/a | Sac7d; aspartyl tRNA synthetase; OBody AM1L10 |
| kunitz | 161 | 0 | n/a | LACI-K1; Aprotinin; TFPI-2 |
| centyrin | 73 | 0 | n/a | Tencon; Tenascin-C; Centyrin |
| affimer | 69 | 1 | ALB | GTPase KRas; Stefin A; Human Stefin A |
| EVH1domain | 68 | 0 | n/a | Sprouty related EVH1 domain containing 1; Sprouty-related, EVH1 domain-containing protein 2; Ena/VASP-like protein |
| betarolldomain | 65 | 0 | n/a | adenylate cyclase; Pectinesterase 1; Pectate lyase 1 |
| phdfingerdomain | 53 | 0 | n/a | PHD finger protein 11; Histone lysine demethylase PHF8; PHD finger protein 13 |
| avimer | 42 | 0 | n/a | 7; 2; 10 |
| Ibody | 27 | 0 | n/a | human neural cell adhesion molecule; NCAM Ig domain 1; 30S ribosomal protein S5 |

## Target-Linked Coverage
| Scaffold | Target-linked rows | Top supported targets |
|---|---|---|
| adnectin | 37 | CD8A (16); EGFR (11); ICAM-2 (4); TNFRSF9 (3); c-Met (2) |
| cyclotide | 2 | OPRK1 (2) |
| knottin | 1 | SCN9A (1) |
| affimer | 1 | ALB (1) |

## Source Registry Highlights
| Source | Chunk count | Category | Owner table |
|---|---|---|---|
| plmsearch_results.csv | 38079 | structure_screen | plmsearch_results |
| loop_annotations.csv | 3383 | structure_screen | loop_annotations |
| loop_flexibility_results.csv | 3383 | structure_screen | loop_flexibility_results |
| affinity_data.csv | 1996 | interaction_measurement | affinity_data |
| bcell_epitope_results.csv | 1996 | immunogenicity | bcell_epitope_results |
| cmc_data.csv | 1996 | developability | cmc_data |
| developability_results.csv | 1996 | developability | developability_results |
| domains.csv | 1996 | core_entity | domains |
| ecoli_expression_results.csv | 1996 | developability | ecoli_expression_results |
| foldseek_results.csv | 1996 | structure_screen | foldseek_results |

## Notes
- This package is generated deterministically from the checked-in formal FBBP snapshot under `fbbp-mcp-rag-server/formal_snapshots/fbbp_private_v2026_04/`.
- It is intended to be the canonical GitHub, resume, and demo result package for the current FBBP formal line.
- It avoids demo datasets and does not depend on temporary smoke outputs.
- The appendix contains `41` target-linked registry rows and `34` source-registry rows.
