# Test fixtures

Captured on 2026-10-24 from the real sources, so the parity tests compare against what the current
api.linuxserver.io actually serves.

- `repos.json`: repository snapshots (as `src/sources/github.ts` produces them) for a dozen images that
  between them use every config field, plus `lsio-api` (categorised Internal, so excluded). `stars`,
  `latest_release` and `pushed_at` are set to the values the live API reported, and `scarf` holds its
  monthly pulls, so the expected output is exact.
- `live-v1.json`: those images from
  `https://api.linuxserver.io/api/v1/images?include_config=true&include_deprecated=true`.

To refresh: run `npm run refresh`, fetch the live endpoint, and rebuild both files for the same names.
