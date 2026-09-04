const ROUTE_VIEWS = new Set(["onboarding", "plan", "queue"]);

function routeFromPath(pathname = "/") {
  if (pathname.startsWith("/onboarding")) return "onboarding";
  if (pathname.startsWith("/plan")) return "plan";
  if (pathname.startsWith("/review/")) return "review";
  if (pathname.startsWith("/queue")) return "queue";
  return "overview";
}

export function readRouteLocation(pathname = "/", search = "") {
  const params = new URLSearchParams(search);
  const view = params.get("view");
  if (ROUTE_VIEWS.has(view)) return { route: view, path: `/${view}` };
  if (view === "review" && /^[1-9]\d*$/.test(params.get("job") ?? "")) {
    return { route: "review", path: `/review/${params.get("job")}` };
  }
  return { route: routeFromPath(pathname), path: pathname };
}

export function hostedRouteHref(path, currentSearch = "") {
  const target = new URL(path, "https://commerce.navarna.ai");
  const params = new URLSearchParams(target.search);
  const currentClient = new URLSearchParams(currentSearch).get("client");
  if (currentClient && !params.has("client")) params.set("client", currentClient);

  const review = /^\/review\/([1-9]\d*)\/?$/.exec(target.pathname);
  if (review) {
    params.set("view", "review");
    params.set("job", review[1]);
  } else {
    const view = routeFromPath(target.pathname);
    if (view === "overview") {
      params.delete("view");
      params.delete("job");
    } else {
      params.set("view", view);
      params.delete("job");
    }
  }

  const query = params.toString();
  return query ? `/?${query}` : "/";
}
