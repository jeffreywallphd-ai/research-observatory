import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { RIGHTS_POLICY_SCHEMA_SHA256, decodeRightsDocument, rightsContractErrors } from "./generated";

function fixture(name: string): Record<string, any> {
  return JSON.parse(readFileSync(fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url)), "utf8")) as Record<string, any>;
}

describe("portable rights policy contract", () => {
  it("pins exact schema bytes and accepts versioned policy and historical decision", () => {
    const schema = readFileSync(fileURLToPath(new URL("./rights-policy.schema.json", import.meta.url)));
    expect(createHash("sha256").update(schema).digest("hex")).toBe(RIGHTS_POLICY_SCHEMA_SHA256);
    for (const name of ["valid-policy.v1.json", "valid-decision.v1.json"]) {
      const source = fixture(name);
      expect(rightsContractErrors(source)).toEqual([]);
      const parsed = decodeRightsDocument(source);
      expect(parsed).toEqual(source);
      expect(parsed).not.toBe(source);
      expect(Object.isFrozen(parsed)).toBe(true);
    }
  });

  it("rejects extra fields, invalid version, and mismatched record or copy", () => {
    const policy = fixture("valid-policy.v1.json");
    const permission = policy.permissions[0];
    expect(rightsContractErrors({ ...policy, contractVersion: "2.0.0" })).toEqual(["rights-contract-schema-invalid"]);
    expect(rightsContractErrors({ ...policy, privatePath: "C:/private/file.pdf" })).toEqual(["rights-contract-schema-invalid"]);
    expect(rightsContractErrors({ ...policy, subject: { ...policy.subject, copyId: "C:/private/file.pdf" } }))
      .toEqual(["rights-contract-schema-invalid"]);
    expect(rightsContractErrors({ ...policy, permissions: [{ ...permission,
      subject: { ...permission.subject, address: { ...permission.subject.address, ordinal: 1 } },
    }] })).toEqual(["rights-permission-invalid"]);
    expect(rightsContractErrors({ ...policy, permissions: [{ ...permission,
      subject: { ...permission.subject, sourceAssertionRevisionId: policy.revisionId },
    }] })).toEqual(["rights-permission-invalid"]);
  });

  it("keeps action, resource, destination, and provenance restrictions explicit", () => {
    const policy = fixture("valid-policy.v1.json");
    const permission = policy.permissions[0];
    expect(rightsContractErrors({ ...policy, subject: { ...policy.subject, resourceClass: "full-text" } }))
      .toEqual(["rights-permission-invalid"]);
    expect(rightsContractErrors({ ...policy, permissions: [{ ...permission,
      use: { ...permission.use, action: "model-use", destinationKind: "remote-model",
        provider: null, region: null } }] })).toEqual(["rights-permission-invalid"]);
    expect(rightsContractErrors({ ...policy, permissions: [{ ...permission,
      basis: "source-observation", confidence: "reported", assertedByActorId: null,
      confirmationRequired: true }] })).toEqual(["rights-permission-invalid"]);
    expect(rightsContractErrors({ ...policy, permissions: [{ ...permission,
      basis: "verified-entitlement", confidence: "verified", entitlementRevisionId: null }] }))
      .toEqual(["rights-permission-invalid"]);
    expect(rightsContractErrors({ ...policy, permissions: [{ ...permission,
      use: { ...permission.use, action: "acquire" } }] })).toEqual(["rights-contract-schema-invalid"]);
  });

  it("keeps a reported license bound to one source record without granting an action", () => {
    const policy = fixture("valid-policy.v1.json");
    const observation = {
      projectId: policy.subject.projectId,
      sourceAssertionRevisionId: policy.subject.sourceAssertionRevisionId,
      address: policy.subject.address,
      sourceRevisionId: policy.subject.address.revisionId,
      sourceSha256: "a".repeat(64),
      provider: "openalex",
      terms: {
        license: { state: "reported", value: "CC BY 4.0" },
        terms: { state: "not-reported", value: null },
        access: "open",
      },
      retrievedAt: "2026-09-30T18:00:00.000Z",
    };
    expect(rightsContractErrors({ ...policy, sourceObservation: observation })).toEqual([]);
    expect(rightsContractErrors({ ...policy, sourceObservation: {
      ...observation, address: { ...observation.address, ordinal: 1 },
    } })).toEqual(["rights-observation-invalid"]);
    expect(rightsContractErrors({ ...policy, sourceObservation: {
      ...observation, sourceRevisionId: policy.revisionId,
    } })).toEqual(["rights-observation-invalid"]);
    expect(rightsContractErrors({ ...policy, sourceObservation: {
      ...observation, terms: { ...observation.terms, license: { state: "reported", value: null } },
    } })).toEqual(["rights-observation-invalid"]);
    expect(rightsContractErrors({ ...policy, sourceObservation: {
      ...observation, retrievedAt: "2026-02-30T18:00:00.000Z",
    } })).toEqual(["rights-observation-invalid"]);
  });

  it("rejects invalid calendar dates, chronology, duplicate assertions, and forged allow shape", () => {
    const policy = fixture("valid-policy.v1.json");
    const permission = policy.permissions[0];
    expect(rightsContractErrors({ ...policy, permissions: [{ ...permission,
      expiresAt: permission.recordedAt }] })).toEqual(["rights-permission-invalid"]);
    expect(rightsContractErrors({ ...policy, permissions: [{ ...permission,
      recordedAt: "2026-02-30T19:00:00.000Z" }] })).toEqual(["rights-permission-invalid"]);
    expect(rightsContractErrors({ ...policy, permissions: [permission, permission] }))
      .toEqual(["rights-permission-invalid"]);
    const decision = fixture("valid-decision.v1.json");
    expect(rightsContractErrors({ ...decision, policyRevisionId: null })).toEqual(["rights-decision-invalid"]);
    expect(rightsContractErrors({ ...decision, authorityKind: "none" })).toEqual(["rights-decision-invalid"]);
    expect(rightsContractErrors({ ...decision, authorityKind: "legacy-import-bridge" }))
      .toEqual(["rights-decision-invalid"]);
    expect(rightsContractErrors({ ...decision, governingAssertionIds: [] })).toEqual(["rights-decision-invalid"]);
    expect(rightsContractErrors({ ...decision, expiresAt: decision.evaluatedAt })).toEqual(["rights-decision-invalid"]);
  });

  it("bounds the legacy import bridge to one retained local metadata assertion", () => {
    const decision = fixture("valid-decision.v1.json");
    const assertionId = decision.subject.sourceAssertionRevisionId;
    const subject = {
      ...decision.subject,
      address: {
        ...decision.subject.address,
        kind: "import-member",
        ordinal: 1,
        recordKey: "b".repeat(64),
      },
      copyId: assertionId,
      copyLocation: "local-source",
    };
    const bridge = {
      ...decision,
      reasonCode: "rights-legacy-import-confirmed",
      authorityKind: "legacy-import-bridge",
      subject,
      use: { ...decision.use, action: "store", purpose: "corpus-membership" },
      policyRevisionId: null,
      governingAssertionIds: [assertionId],
      sourceAssertionSha256: "a".repeat(64),
      expiresAt: null,
    };
    expect(rightsContractErrors(bridge)).toEqual([]);
    for (const action of ["store", "inspect", "derive", "index"])
      expect(rightsContractErrors({ ...bridge, use: { ...bridge.use, action } })).toEqual([]);
    for (const forged of [
      { ...bridge, authorityKind: "none" },
      { ...bridge, sourceAssertionSha256: null },
      { ...bridge, governingAssertionIds: [decision.governingAssertionIds[0]] },
      { ...bridge, policyRevisionId: decision.policyRevisionId },
      { ...bridge, reasonCode: "rights-explicit-permission" },
      { ...bridge, subject: { ...subject, resourceClass: "full-text" } },
      { ...bridge, subject: { ...subject, copyLocation: "provider-hosted" } },
      { ...bridge, subject: { ...subject, copyId: decision.subject.copyId } },
      { ...bridge, subject: { ...subject, address: decision.subject.address } },
      { ...bridge, use: { ...bridge.use, action: "quote" } },
      { ...bridge, use: { ...bridge.use, purpose: "manuscript-drafting" } },
    ]) expect(rightsContractErrors(forged)).toEqual(["rights-decision-invalid"]);
  });
});
