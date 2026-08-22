# Local security verification

Owner: Security reviewers. Boundary: secrets, dependencies, licenses,
vulnerabilities, privacy, rights, and local attack-surface tests.

The controlled Trivy JSON fixtures contain no live credentials. Tests must prove
known violations fail, approved exceptions are exact and time-bounded, unsafe
installer inputs fail closed, and normalized reports never retain secret match
values. Live scanner/database behavior is exercised by the `security-local`
verification profile and CI security job.

The W1 application-lock checks additionally pin the non-persisting Windows
credential prompt, same-SID token comparison, handle and transient-buffer
cleanup, native idle authority, and before/after generation checks on every
protected renderer-to-native bridge. Renderer tests separately prove that the
locked document tree contains no project, command, diagnostics, or Core view.
