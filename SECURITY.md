# Security and Sensitive Data

## Reporting

Do not post credentials, private datasets, unpublished confidential material, or exploitable deployment details in a public issue. Contact the repository owner through the GitHub profile and provide only a minimal non-sensitive summary until a private channel is established.

## Secrets

- Use environment variables or an untracked `.env` file for credentials.
- Treat example tokens and local endpoints as placeholders.
- Revoke and rotate any credential that is committed accidentally.

## Research-use boundary

This repository contains research software and/or research data. It is not a clinical decision system and should not be used as a substitute for expert review, experimental validation, or applicable institutional governance.

## Supported surface

The current `main` branch and tagged releases are the only supported public surfaces. Historical intermediate artifacts are retained for auditability and may not receive security backports.
