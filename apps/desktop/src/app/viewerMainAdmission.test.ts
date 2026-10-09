import { describe, expect, it } from "vitest";
import { ViewerBufferBudget, ViewerMainAdmission, viewerCoreAllowance, viewerWorkerAllowance } from "./documentViewer";

describe("bounded main-thread anchor context ownership", () => {
  it("shares the existing main allowance at the maximum source, retaining it until the last context settles", () => {
    const budget = new ViewerBufferBudget();
    const size = 128 * 1024 * 1024;
    const other = budget.reserve(viewerWorkerAllowance(size) + viewerCoreAllowance(size) + 16 * 1024 * 1024);
    const main = new ViewerMainAdmission(budget);
    const decoder = main.retain();
    const a = main.context(), b = main.context();
    expect(budget.used).toBe(256 * 1024 * 1024);
    decoder(); expect(budget.used).toBe(256 * 1024 * 1024);
    a(); b(); expect(budget.used).toBe(192 * 1024 * 1024);
    other(); expect(budget.used).toBe(0);
  });
  it("denies context overage before issue and does not release another owner's unknown read", () => {
    const budget = new ViewerBufferBudget(), main = new ViewerMainAdmission(budget);
    const contexts = Array.from({ length: 4 }, () => main.context());
    expect(() => main.context()).toThrow("viewer-resource-limit");
    contexts[0]!(); contexts[1]!(); contexts[2]!();
    expect(budget.used).toBe(64 * 1024 * 1024);
    const next = main.context(); next();
    expect(budget.used).toBe(64 * 1024 * 1024);
    contexts[3]!(); contexts[3]!(); expect(budget.used).toBe(0);
  });
});
