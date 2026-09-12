# W1 generated-contract checkout correction

Bounded checkout-control maintenance at predecessor
`a36f5c0f5a68c85766222ef1c7945d470cf95f1c`; no product, contract-schema,
generator, acceptance, reference, security or gate change.
Predecessor `.gitattributes` SHA-256:
`b32f2224fc9e9d52552511349e3c7deadc122ae28f22739e8dafa9d40132d8e9`.

Supplemental attempt 02 passed all 21 workflow-executor tests, then rejected
`packages/contracts/domain/lifecycle.generated.ts` as stale. The isolated Git
checkout contained 828 CRLF line endings; the canonical generated file contained
none, and their text was identical after LF normalization. The generator correctly
compares exact expected bytes. Existing Git attributes pin the other two original
generated domain/API files to LF but omitted this generated lifecycle file.

Add one explicit LF attribute for the omitted file. Do not relax freshness
comparison or regenerate different contract semantics. A new regression checks
out only that indexed file into an owned temporary directory under an explicit
`core.autocrlf=true` override, then requires LF and exact committed bytes. It uses
no force/overwrite, changes no Git configuration/index/history and cleans only its
own fixture. The regression failed before the attribute correction.

Retained adverse records:

- `artifacts/tmp/W1.supplemental-02.json`, SHA-256
  `17a7422da1c4558caadd2d18ff24d8101d164d22fb3a2128acf7a6142e4f75e4`.
- Development RED `artifacts/tmp/W1.contract-eol-01.json`, SHA-256
  `6a8bf2c98862b3a063eee830194ed1d5e3bf4f9cc5f3053a71ee8e169f6d4dbb`.

Qualify the committed candidate with the lifecycle tests (including real fresh
Git checkout), governed Python quality and the complete TypeScript contracts
verification. Independently review before local integration. Refresh the isolated
checkout's previously converted generated file using its unchanged generator,
then continue fresh W1 checks. This repair is not structural refactoring, cached
Wave acceptance or a new product task. Prior failure receipts remain adverse.
