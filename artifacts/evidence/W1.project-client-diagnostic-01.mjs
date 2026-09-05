// No I/O transport: prove validation and emitted request shape only.
import { createCoreApiClient } from '../../packages/contracts/core-api/generated.ts';

const cases = [];
for (const researchObjective of ['First line.', 'First line.\nSecond line.']) {
  const requests = [];
  const client = createCoreApiClient(async request => {
    requests.push(request);
    throw new Error('DIAGNOSTIC-TRANSPORT-REACHED');
  });
  let result;
  try {
    await client.createProject({parentDirectory: 'C:/Research', directoryName: 'diagnostic-study',
      displayName: 'Diagnostic Study', primaryUseCase: 'theory-synthesis', researchObjective});
    result = 'unexpected completion';
  } catch (error) { result = error.message; }
  cases.push({researchObjective, transportCalls: requests.length, result});
}
let catalog;
const client = createCoreApiClient(async request => {
  catalog = request;
  throw new Error('DIAGNOSTIC-TRANSPORT-REACHED');
});
try { await client.workflowProfileCatalog(); } catch {}
console.log(JSON.stringify({documentType: 'no-io-project-client-diagnostic', cases, catalog}, null, 2));
