import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";

export default defineConfig([
  ...nextVitals,
  {
    rules: {
      // BuildTrack client workspaces intentionally load authenticated API data
      // after mount. React 19's broad set-state-in-effect rule flags that
      // established fetch pattern even when cancellation/error handling is
      // correct, so keep the rule off while retaining purity, immutability,
      // hook-order, dependency and JSX-key checks.
      "react-hooks/set-state-in-effect": "off",
    },
  },
  globalIgnores([".next/**", "node_modules/**", "out/**"]),
]);
