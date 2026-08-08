# Local security verification

Owner: Security reviewers. Boundary: secrets, dependencies, licenses,
vulnerabilities, privacy, rights, and local attack-surface tests.

The controlled Trivy JSON fixtures contain no live credentials. Tests must prove
known violations fail, approved exceptions are exact and time-bounded, unsafe
installer inputs fail closed, and normalized reports never retain secret match
values. Live scanner/database behavior is exercised by the `security-local`
verification profile and CI security job.
