import test from "node:test";
import assert from "node:assert/strict";
import config from "../vite.config.js";
test("development proxy preserves same-origin Host without weakening API origin checks", () => {
  assert.equal(config.server.port, 5173);
  assert.equal(config.server.strictPort, true);
  assert.equal(config.server.proxy["/api"].changeOrigin, false);
  assert.equal(config.server.proxy["/api"].target, "http://127.0.0.1:8766");
});
