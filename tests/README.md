# Tests

Current integration checks cover the API's origin policy, secret-safe health response, and the separation between the API and demo services.

Run them through `pnpm run check`. The startup smoke check uses unused local ports and real HTTP requests rather than asserting only that modules import.

Later tests should cover workspace isolation, tool argument validation, worker recovery, bounded investigations, citation correctness, and inconclusive outcomes.
