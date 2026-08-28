import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  DOMAIN_LIFECYCLE_PROFILE_SHA256,
  DOMAIN_LIFECYCLE_SCHEMA_SHA256,
  DomainLifecycleProblem,
  applyLifecycleTransition,
  domainLifecycleProfile,
  lifecycleTransitionErrors,
  lifecycleTransitionJson,
  prepareLifecycleTransition,
  type LifecycleCommand,
  type LifecycleSnapshot,
  type LifecycleSubjectKind,
} from "./lifecycle.generated";

const aggregateId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a1";

function snapshot(subjectKind: LifecycleSubjectKind, state: string, revision = 0): LifecycleSnapshot {
  return {
    schemaVersion: "1.0",
    documentType: "research-observatory-domain-lifecycle-snapshot",
    profileVersion: "1.0.0",
    subjectKind,
    aggregateId,
    state,
    revision,
  };
}

function command(subjectKind: LifecycleSubjectKind, name: string, expectedRevision = 0): LifecycleCommand {
  return {
    schemaVersion: "1.0",
    documentType: "research-observatory-domain-lifecycle-command",
    profileVersion: "1.0.0",
    subjectKind,
    aggregateId,
    expectedRevision,
    command: name,
    actor: { kind: "human", id: "researcher:local-owner" },
    reason: { code: "researcher-judgment", detail: "Researcher recorded the bounded lifecycle decision." },
    occurredAt: "2026-08-28T13:45:00.000Z",
    idempotencyKey: `${subjectKind}.${name}.${expectedRevision}`,
  };
}

describe("portable domain lifecycle contract", () => {
  it("binds eight exact profiles and generated code to the language-neutral bytes", () => {
    const root = new URL("./", import.meta.url);
    const schema = readFileSync(fileURLToPath(new URL("domain-lifecycle.schema.json", root)));
    const profile = readFileSync(fileURLToPath(new URL("domain-lifecycle.v1.json", root)));
    expect(createHash("sha256").update(schema).digest("hex")).toBe(DOMAIN_LIFECYCLE_SCHEMA_SHA256);
    expect(createHash("sha256").update(profile).digest("hex")).toBe(DOMAIN_LIFECYCLE_PROFILE_SHA256);
    expect(domainLifecycleProfile().subjects.map((subject) => subject.subjectKind)).toEqual([
      "project",
      "corpus-item",
      "document",
      "evidence-record",
      "decision",
      "task",
      "dossier",
      "export",
    ]);
  });

  it("derives every destination deterministically and retains actor and reason", () => {
    for (const subject of domainLifecycleProfile().subjects) {
      for (const rule of subject.transitions) {
        const current = snapshot(subject.subjectKind, rule.from, 7);
        const requested = command(subject.subjectKind, rule.command, 7);
        const first = prepareLifecycleTransition(current, requested);
        const second = prepareLifecycleTransition(current, requested);
        expect(lifecycleTransitionJson(first)).toBe(lifecycleTransitionJson(second));
        expect(first.toState).toBe(rule.to);
        expect(first.transitionKind).toBe(rule.kind);
        expect(first.priorRevision).toBe(7);
        expect(first.revision).toBe(8);
        expect(first.actor).toEqual(requested.actor);
        expect(first.reason).toEqual(requested.reason);
        expect(Object.isFrozen(first)).toBe(true);
        expect(Object.isFrozen(first.actor)).toBe(true);
      }
    }
  });

  it("rejects illegal, stale, mismatched, path-bearing and extra-field commands", () => {
    const writes: unknown[] = [];
    expect(() => applyLifecycleTransition(snapshot("project", "active"), command("project", "publish"), (item) => writes.push(item)))
      .toThrowError(DomainLifecycleProblem);
    expect(writes).toEqual([]);
    expect(lifecycleTransitionErrors(snapshot("project", "active"), command("project", "publish"))).toEqual([
      "lifecycle-command-not-allowed",
    ]);
    expect(lifecycleTransitionErrors(snapshot("task", "ready", 5), command("task", "start", 4))).toEqual([
      "lifecycle-revision-conflict",
    ]);

    const mismatched = { ...command("document", "make-available"), aggregateId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a2" };
    expect(lifecycleTransitionErrors(snapshot("document", "registered"), mismatched)).toEqual([
      "lifecycle-subject-mismatch",
    ]);

    const pathActor = structuredClone(command("document", "make-available")) as unknown as { actor: { id: string } };
    pathActor.actor.id = "C:\\private\\researcher";
    expect(lifecycleTransitionErrors(snapshot("document", "registered"), pathActor)).toEqual([
      "lifecycle-command-invalid",
    ]);

    const extra = { ...command("document", "make-available"), credential: "secret" };
    expect(lifecycleTransitionErrors(snapshot("document", "registered"), extra)).toEqual([
      "lifecycle-command-invalid",
    ]);

    expect(() => prepareLifecycleTransition(snapshot("project", "deleted", 2), command("project", "reopen", 2)))
      .toThrowError(DomainLifecycleProblem);
  });

  it("requires explicit terminal reopen and composes restart from the emitted revision", () => {
    expect(lifecycleTransitionErrors(snapshot("task", "completed", 2), command("task", "start", 2))).toEqual([
      "lifecycle-command-not-allowed",
    ]);
    const reopened = prepareLifecycleTransition(snapshot("task", "completed", 2), command("task", "reopen", 2));
    expect(reopened.toState).toBe("ready");
    expect(reopened.transitionKind).toBe("reopen");
    const restarted = snapshot("task", reopened.toState, reopened.revision);
    expect(prepareLifecycleTransition(restarted, command("task", "start", reopened.revision)).toState).toBe("in-progress");
  });

  it("emits the maximum safe revision exactly and denies overflow before persistence", () => {
    const maximum = Number.MAX_SAFE_INTEGER;
    const emitted = prepareLifecycleTransition(
      snapshot("project", "active", maximum - 1),
      command("project", "archive", maximum - 1),
    );
    expect(emitted.revision).toBe(maximum);
    expect(JSON.parse(lifecycleTransitionJson(emitted)).revision).toBe(maximum);

    const writes: unknown[] = [];
    const restarted = snapshot("project", emitted.toState, emitted.revision);
    const requested = command("project", "reopen", emitted.revision);
    expect(lifecycleTransitionErrors(restarted, requested)).toEqual(["lifecycle-revision-exhausted"]);
    expect(() => applyLifecycleTransition(restarted, requested, (item) => writes.push(item))).toThrowError(
      DomainLifecycleProblem,
    );
    expect(writes).toEqual([]);
  });
});
