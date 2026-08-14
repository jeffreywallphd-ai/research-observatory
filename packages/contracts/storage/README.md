# Local storage contracts

`sqlite-profile.v1.json` is the exact portable profile for the first canonical
local database. It fixes the database identity, version, scalar storage domain,
connection controls, checkpoint authority, integrity checks, and normalized
table inventory. `sqlite-profile.schema.json` fails closed on any undeclared
override.

The profile is not an API for issuing SQL. Core owns the SQLite adapter, the
desktop never opens the database, and downstream modules consume repository
ports introduced by the storage slice. Migration files and prior-version
database fixtures belong to the next task rather than being hidden in this
initial profile.
