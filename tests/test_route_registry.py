"""Route registry (web/lib/routes.json) — T5 of the Oct 2026 work order.

  * every live/hidden page resolves: a Next.js page.tsx, or a page the API serves
  * every Next.js page is IN the registry (a new page cannot be forgotten)
  * removed pages are not listed; /articles/ is removed
  * admin / seo_lead / viewer each see only their pages (same rule as web/lib/registry.ts)
  * if web/out exists (after `npm run build`), each slug has a built index.html

Run:  python tests/test_route_registry.py      (or pytest)
"""
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
REG = json.load(open(os.path.join(ROOT, "web", "lib", "routes.json"), encoding="utf-8"))
ROUTES = REG["routes"]
ROLES = {"owner", "admin", "seo", "seo_lead", "writer", "viewer"}
# Pages served by the API through nginx, by mount prefix (module URL prefixes).
SERVER_PREFIXES = ("/seo/backlink-ops/", "/invoices/")


def path_of(slug):
    return slug.split("?")[0].split("#")[0].rstrip("/") or "/"


def allowed(r, role):            # mirror of registry.ts allowed()
    return r["roles"] == "all" or role == "owner" or role in r["roles"]


def home(role, flags):           # mirror of registry.ts homeGroups()
    return [r["slug"] for r in ROUTES if r["status"] == "live" and allowed(r, role)
            and (not r.get("requires") or flags.get(r["requires"]))]


def test_shape():
    seen = set()
    for r in ROUTES:
        assert r["slug"].startswith("/") and r["slug"] not in seen, r["slug"]
        seen.add(r["slug"])
        assert r["group"] in REG["groups"], r
        assert r["status"] in ("live", "hidden", "planned", "removed"), r
        assert r["roles"] == "all" or (r["roles"] and set(r["roles"]) <= ROLES), r
        assert r["title"] and r["purpose"] and r["icon"], r
        assert path_of(r["slug"]) == "/" or r["slug"].split("?")[0].split("#")[0].endswith("/"), \
            f"{r['slug']}: use the trailing slash (the export is trailingSlash: true)"
    assert set(REG["groups"]) == {"SEO", "Content", "Team", "Finance", "Admin"}


def next_pages():
    base = os.path.join(ROOT, "web", "app")
    out = set()
    for d, _, files in os.walk(base):
        if "page.tsx" in files:
            out.add("/" + os.path.relpath(d, base).replace(os.sep, "/").strip("."))
    return {p.rstrip("/") or "/" for p in out}


def test_every_slug_resolves():
    pages = next_pages()
    for r in ROUTES:
        if r["status"] in ("planned",):
            continue
        if r.get("server"):
            assert r["slug"].startswith(SERVER_PREFIXES), r["slug"]
        else:
            assert path_of(r["slug"]) in pages, f"{r['slug']} has no web/app page"


def test_every_page_is_registered():
    listed = {path_of(r["slug"]) for r in ROUTES}
    missing = sorted(p for p in next_pages() if p not in listed and p != "/")
    assert not missing, f"pages missing from web/lib/routes.json: {missing}"


def test_removed_and_planned_never_listed():
    arts = [r for r in ROUTES if path_of(r["slug"]) == "/articles"]
    assert arts and all(r["status"] == "removed" for r in arts)
    everything = home("owner", {"tracker": 1, "ideas": 1, "taskManager": 1})
    assert "/articles/" not in everything
    assert all(r["slug"] not in everything for r in ROUTES if r["status"] in ("planned", "removed", "hidden"))


def test_roles():
    flags = {"tracker": True, "ideas": True, "taskManager": True}
    admin, lead, viewer, jai = (home(x, flags) for x in ("admin", "seo_lead", "viewer", "owner"))
    assert "/invoices/" in admin and "/settings/users/" in admin
    assert "/invoices/" not in lead and "/settings/users/" not in lead
    assert "/invoices/" not in viewer and "/dashboard/seo/articles/new/" not in viewer
    assert "/dashboard/seo/articles/new/" in lead
    assert set(admin) <= set(jai) and set(lead) <= set(jai)
    assert len(jai) == len([r for r in ROUTES if r["status"] == "live"]), "Jai sees everything live"
    off = home("seo_lead", {})
    assert "/tasks/?tab=ideas" not in off and "/tasks/" in off, "flagged pages hide when the flag is off"


def test_nav_and_tabs_come_from_registry():
    nav = [r["slug"] for r in ROUTES if r.get("nav")]
    assert nav[:5] == ["/dashboard/", "/dashboard/seo/", "/keywords/", "/seo/backlink-ops/", "/tasks/"]
    tabs = sorted((r for r in ROUTES if r.get("tab")), key=lambda r: r["tab"])
    assert [r.get("tabTitle", r["title"]) for r in tabs] == [
        "Inbox", "Articles", "Calendar", "Team", "Backlinks", "Recommendations",
        "Technical audit", "Playbook guide"]
    src = open(os.path.join(ROOT, "web", "components", "Nav.tsx"), encoding="utf-8").read()
    assert "navRoutes(" in src and "seoTabs(" in src and "href: '/" not in src, "Nav must not hand-list links"


def test_built_pages_exist_if_built():
    out = os.path.join(ROOT, "web", "out")
    if not os.path.isdir(out):
        return
    for r in ROUTES:
        if r["status"] in ("live", "hidden") and not r.get("server"):
            p = path_of(r["slug"]).strip("/")
            assert os.path.isfile(os.path.join(out, p, "index.html")), f"{r['slug']} not in the build"


if __name__ == "__main__":
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            n += 1
            print("  PASS ", name)
    print(f"All {n} registry checks passed.")
