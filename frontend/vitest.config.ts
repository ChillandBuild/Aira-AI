import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  oxc: {
    jsx: "react-jsx",
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "node",
    include: ["**/*.test.ts", "**/*.test.tsx"],
    exclude: ["node_modules/**", "tests/e2e/**"],
  },
});
