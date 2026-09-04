import assert from "node:assert/strict";
import test from "node:test";
import { hostedRouteHref, readRouteLocation } from "../src/routeLocation.js";

test("reads reload-safe hosted views from the root query", () => {
  assert.deepEqual(readRouteLocation("/", "?view=onboarding&client=hcs_gadgets"), {
    route: "onboarding",
    path: "/onboarding",
  });
  assert.deepEqual(readRouteLocation("/", "?view=review&job=2&client=orin_oauth_test"), {
    route: "review",
    path: "/review/2",
  });
});

test("converts app paths to root-query routes and preserves the tenant", () => {
  assert.equal(
    hostedRouteHref("/queue", "?client=orin_oauth_test"),
    "/?client=orin_oauth_test&view=queue",
  );
  assert.equal(
    hostedRouteHref("/review/12", "?client=orin_oauth_test"),
    "/?client=orin_oauth_test&view=review&job=12",
  );
  assert.equal(hostedRouteHref("/?client=hcs_gadgets", "?view=plan"), "/?client=hcs_gadgets");
});
