import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  decodeApplicationLockSnapshot,
  decodePolicyTransitionResult,
} from "./applicationLock";
import {
  ApplicationSettingsController,
  type ApplicationSettingsTransport,
} from "./applicationSettings";

interface NativeWitness {
  readonly enablePassword: { readonly prepared: unknown; readonly committed: unknown; readonly statusAfterCommit: unknown };
  readonly protectedCancellation: { readonly prepared: unknown; readonly cancelled: unknown; readonly statusAfterCancel: unknown };
  readonly helloUnavailable: unknown;
  readonly invalidPolicyRecovery: { readonly ordinaryDenied: unknown; readonly prepared: unknown; readonly committed: unknown };
}

class NativeQueueTransport implements ApplicationSettingsTransport {
  public readonly commands: string[] = [];

  public constructor(private readonly values: Array<unknown | Error>) {}

  public async invoke(command: string): Promise<unknown> {
    this.commands.push(command);
    const value = this.values.shift();
    if (value instanceof Error) throw value;
    return value;
  }
}

const fixturePath = process.env.RO_LOCK_CONTRACT_FIXTURE;
const nativeDescribe = fixturePath ? describe : describe.skip;
const nativeWitness = fixturePath
  ? JSON.parse(readFileSync(fixturePath, "utf8")) as NativeWitness
  : null;

nativeDescribe("native application-lock JSON through the production renderer controller", () => {
  const witness = nativeWitness!;

  it("consumes actual native enable, commit, cancel, unavailable, and recovery shapes", () => {
    expect(decodePolicyTransitionResult(witness.enablePassword.prepared)).toMatchObject({
      outcome: "prepared",
      sourceMode: "none",
      targetMode: "windows-password",
      warningRequired: false,
    });
    expect(decodePolicyTransitionResult(witness.enablePassword.committed)).toMatchObject({
      outcome: "committed",
      snapshot: { signInMode: "windows-password" },
    });
    expect(decodePolicyTransitionResult(witness.protectedCancellation.prepared)).toMatchObject({
      outcome: "prepared",
      targetMode: "none",
      warningRequired: true,
    });
    expect(decodePolicyTransitionResult(witness.protectedCancellation.cancelled)).toMatchObject({
      outcome: "cancelled",
      snapshot: { signInMode: "windows-password" },
    });
    expect(decodePolicyTransitionResult(witness.helloUnavailable)).toMatchObject({
      outcome: "unavailable",
      sourceMode: "windows-hello",
      targetMode: "none",
    });
    expect(decodePolicyTransitionResult(witness.invalidPolicyRecovery.ordinaryDenied)).toMatchObject({
      outcome: "denied",
      reasonCode: "RO-SIGN-IN-TRANSITION-RECOVERY-REQUIRED",
      sourceMode: null,
    });
    expect(decodePolicyTransitionResult(witness.invalidPolicyRecovery.prepared)).toMatchObject({
      outcome: "prepared",
      reasonCode: "RO-SIGN-IN-RECOVERY-PREPARED",
      sourceMode: null,
      warningRequired: true,
    });
    expect(decodePolicyTransitionResult(witness.invalidPolicyRecovery.committed)).toMatchObject({
      outcome: "committed",
      reasonCode: "RO-SIGN-IN-RECOVERY-COMMITTED",
      snapshot: { signInMode: "none", configurationState: "valid" },
    });
    expect(decodeApplicationLockSnapshot(witness.protectedCancellation.statusAfterCancel))
      .toMatchObject({ signInMode: "windows-password" });
  });

  it("drives the production controller with native JSON and exact command ordering", async () => {
    const enableTransport = new NativeQueueTransport([
      witness.enablePassword.prepared,
      witness.enablePassword.committed,
    ]);
    const enabled = await new ApplicationSettingsController(enableTransport).prepare({
      mode: "windows-password",
      profileName: "Native fixture",
      inactivityTimeoutMinutes: 5,
    });
    expect(enabled).toMatchObject({ kind: "committed", snapshot: { signInMode: "windows-password" } });
    expect(enableTransport.commands).toEqual([
      "application_sign_in_transition_prepare",
      "application_sign_in_transition_commit",
    ]);

    const cancellationTransport = new NativeQueueTransport([
      witness.protectedCancellation.prepared,
      witness.protectedCancellation.cancelled,
    ]);
    const cancellation = new ApplicationSettingsController(cancellationTransport);
    await expect(cancellation.prepare({ mode: "none", profileName: "", inactivityTimeoutMinutes: 0 }))
      .resolves.toMatchObject({ kind: "confirmation-required" });
    await expect(cancellation.confirm(false)).resolves.toMatchObject({ kind: "cancelled" });

    const unavailable = await new ApplicationSettingsController(
      new NativeQueueTransport([witness.helloUnavailable]),
    ).prepare({ mode: "none", profileName: "", inactivityTimeoutMinutes: 0 });
    expect(unavailable).toMatchObject({ kind: "rejected" });

    const recoveryTransport = new NativeQueueTransport([
      witness.invalidPolicyRecovery.prepared,
      witness.invalidPolicyRecovery.committed,
    ]);
    const recovery = new ApplicationSettingsController(recoveryTransport);
    await expect(recovery.prepareRecovery()).resolves.toMatchObject({ kind: "confirmation-required" });
    await expect(recovery.confirm(true)).resolves.toMatchObject({ kind: "committed" });
    expect(recoveryTransport.commands).toEqual([
      "application_sign_in_password_recovery_prepare",
      "application_sign_in_transition_commit",
    ]);
  });

  it("reconciles a simulated lost commit response from native committed status", async () => {
    const transport = new NativeQueueTransport([
      witness.enablePassword.prepared,
      new Error("simulated response loss"),
      witness.enablePassword.statusAfterCommit,
    ]);
    const result = await new ApplicationSettingsController(transport).prepare({
      mode: "windows-password",
      profileName: "Native fixture",
      inactivityTimeoutMinutes: 5,
    });

    expect(result).toMatchObject({ kind: "reconciled-committed", snapshot: { signInMode: "windows-password" } });
    expect(transport.commands).toEqual([
      "application_sign_in_transition_prepare",
      "application_sign_in_transition_commit",
      "application_lock_status",
    ]);
  });
});
