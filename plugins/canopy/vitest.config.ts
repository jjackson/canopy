import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // Two suites live under the plugin dir:
    //   test/gws/       — canopy-gws MCP server (registration drift gate,
    //                     identity fail-loud contract, handler unit tests
    //                     with mocked Google clients; fully offline)
    //   scripts/test/   — plugin script tests (canopy-web-pat-mint)
    include: ['test/**/*.test.ts', 'scripts/test/**/*.test.ts'],
  },
});
