# Proposed experience reference: Application Security & sign-in

- Intended reference: `RO-UI-ACADEMIC-MINIMAL-1.4`
- Supersedes after approval: `RO-UI-ACADEMIC-MINIMAL-1.3`
- Status: proposed; non-executable until ECR-0004/W1.A05 exact-commit approval
- Owning capability: `CAP-02`
- Proposed route: `application-settings.html#security-sign-in`

## Experience decision

Add an application-level **Settings** destination distinct from **Project
Settings**. The first governed section is **Security & sign-in**. It controls
the local Research Observatory application on this Windows account, not one
project and not remote/university identity.

The sign-in mode is one of exactly three values:

1. **No login — default.** Research Observatory opens without an additional
   app prompt. The signed-in Windows account is the local access boundary for
   the average user.
2. **Windows password.** Preserve the existing native same-user credential
   prompt. A returned Windows token must identify the same account as the
   desktop process.
3. **Windows Hello.** Use an OS-owned Windows Hello consent prompt for current
   user presence. Research Observatory never receives or stores a PIN or
   biometric template.

`No login` disables only Research Observatory startup/manual/idle
reauthentication. It does not disable Windows account isolation, filesystem
permissions, DPAPI/SQLCipher or project encryption, Core capability isolation,
project privacy and egress policy, audit/lineage, or later remote OIDC.

## Page contract

The application shell exposes **Application Settings** in the user/local-profile
menu and makes its app-wide scope explicit. The page requires:

- current mode, default marker, scope, and plain-language protection summary;
- three keyboard-selectable mode cards with availability state;
- Windows Hello states: checking, available, not present, not configured,
  disabled by policy, busy, cancelled, denied, and failed;
- inactivity choices only when a reauthentication mode is enabled;
- a preview of startup, manual lock, idle lock, restart, and recovery behavior;
- explicit confirmation before any protection-reducing transition;
- no silent fallback from Hello to password or no login;
- a disclosed recovery action when Windows reports Hello unavailable;
- success/error announcements, focus restoration, logical tab order, and no
  color-only meaning; and
- a link back to Project Settings for project-specific storage, backup,
  privacy, and portability controls.

## Transition and recovery behavior

- Enabling password or Hello verifies the selected provider before publishing
  the new versioned configuration.
- Changing between enabled providers authenticates the current mode and verifies
  the destination provider before atomic publication.
- Changing an enabled mode to `No login` first requires successful verification
  by the currently configured provider. If that provider is unavailable or its
  configuration is unreadable, the only recovery proof is an explicit native
  Windows-password prompt whose returned token matches the desktop process user
  SID. The protection-reduction warning and deliberate confirmation follow that
  same-user proof. Possession of the signed-in session alone is insufficient.
- If Hello is unavailable after it was configured, the locked view stays
  locked and explains the OS-reported availability class. The user may retry or
  choose an explicit same-user Windows-password recovery prompt. Resetting app
  sign-in to `No login` is offered only after that prompt proves the same SID,
  followed by explicit confirmation, atomic persistence, and local audit. If no
  approved same-user proof is available, the app remains locked and directs the
  user to Windows/provider recovery; it does not reset policy.
- Cancellation and denial leave the application and configuration unchanged.
- A missing legacy profile migrates to explicit `No login`, matching current
  first-run behavior. Every valid persisted
  `application-lock-profile.v1.json` migrates to `Windows password`, preserving
  its profile name and inactivity timeout. A zero-minute timeout remains a
  password/manual-lock profile with inactivity locking disabled; a nonzero
  timeout preserves restart and inactivity locking. A malformed, unreadable,
  corrupt, or unknown-version protected profile fails locked and can be
  reconfigured only after the same native same-user recovery proof above.

## Style-guide delta

Treat app-wide security settings as a governance-form archetype. Consequential
choices use radio-card semantics, not a low-context dropdown. Each option shows
what it protects, its prerequisites, and its recovery consequences. The default
is labeled in text. Protection-reducing confirmation uses warning language but
does not exaggerate the app lock into a second Windows-account boundary.

The locked view names the configured provider in its primary action, provides
provider-specific availability guidance, and continues to exclude project
names, paths, commands, and research content. Academic Minimal light/dark,
responsive, keyboard, focus, reduced-motion, and WCAG AA obligations are
unchanged.

## Workflow delta

This app-wide setting is not a scholarly workflow step and does not alter the
fourteen Research Intent workflows. It remains reachable from the application
shell while preserving the current project and guided-workflow position.

## Approval and materialization

Exact approval of ECR-0004 approves this proposed experience decision and
reserves reference ID `RO-UI-ACADEMIC-MINIMAL-1.4`. W1.A05.B00 must then
materialize the canonical generated reference, page contract, inventory,
manifest, approval record, and validation report in a separate commit before
any renderer implementation. The canonical `APPROVAL.yaml` must cite the
immutable W1.A05 approval and identify `human:repository-owner`; it may not be
created before that approval exists.
