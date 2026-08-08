# Governed benchmark prompts

Nontrivial benchmark prompts live here as UTF-8 `.txt` files. A registry entry
must use the canonical `evaluation/prompts/<id>-<version>.txt` path and pin the
file's exact SHA-256. Benchmarks without a prompt use the exact `none`,
`not-applicable`, `null`, `null` identity declared by the registry schema.
