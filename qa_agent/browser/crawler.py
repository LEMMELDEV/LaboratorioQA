"""Deterministic BFS crawler: discovers the site without being given any routes.

Policies:
- BFS from BASE_URL only; never visits /api/*, /lab/*, /static/* (exclude_prefixes).
- Records per-page observations (refs, forms, links), the link graph and broken links.
- No LLM, no heuristics about the app: pure DOM/link exploration.
"""
from __future__ import annotations

from urllib.parse import urljoin, urlsplit

from qa_agent.browser.models import Link, PageRecord, SiteMap
from qa_agent.browser.session import BrowserSession
from qa_agent.config import agent_settings


def normalize_url(url: str) -> str:
    """Strip fragments; keep path+query so ?pagina=2 stays distinct."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}" + (f"?{parts.query}" if parts.query else "")


def path_of(url: str) -> str:
    parts = urlsplit(url)
    return parts.path + (f"?{parts.query}" if parts.query else "")


def should_exclude(url: str, base_url: str, exclude_prefixes: list[str]) -> bool:
    if not url.startswith(("http://", "https://")):
        return True
    base = urlsplit(base_url)
    other = urlsplit(url)
    if (base.scheme, base.netloc) != (other.scheme, other.netloc):
        return True
    path = other.path
    return any(path.startswith(prefix) or path == prefix for prefix in exclude_prefixes)


def crawl(
    base_url: str | None = None,
    *,
    bug_profile: str = "none",
    max_pages: int | None = None,
    max_depth: int | None = None,
    headless: bool = True,
    verbose: bool = False,
) -> SiteMap:
    settings = agent_settings
    base_url = (base_url or settings.base_url).rstrip("/")
    max_pages = max_pages or settings.max_pages
    max_depth = max_depth if max_depth is not None else settings.max_depth
    exclude_prefixes = [p.strip() for p in settings.exclude_prefixes.split(",") if p.strip()]

    sitemap = SiteMap(base_url=base_url, bug_profile=bug_profile)
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(base_url + "/", 0)]

    with BrowserSession(base_url=base_url, headless=headless) as session:
        while queue and len(visited) < max_pages:
            raw_url, depth = queue.pop(0)
            url = normalize_url(raw_url)
            if url in visited:
                continue
            visited.add(url)

            record = PageRecord(url=url, final_url=url, status=0, depth=depth)
            try:
                session.goto(url)
                record.status = session.last_status
                record.final_url = normalize_url(session.current_url())
                obs = session.observation
                record.title = obs.title
                record.headings = obs.headings
                record.elements = obs.elements
                record.forms = obs.forms
                record.h1 = next(
                    (h.split(":", 1)[1].strip() for h in obs.headings if h.lower().startswith("h1:")),
                    "",
                )
                if record.status >= 400:
                    record.error = f"HTTP {record.status}"

                # Collect internal links and enqueue them.
                graph_urls: list[str] = []
                for el in obs.elements:
                    if el.role != "link" or not el.href:
                        continue
                    abs_url = normalize_url(urljoin(record.final_url, el.href))
                    link = Link(href=path_of(abs_url), text=el.name)
                    record.links.append(link)
                    if should_exclude(abs_url, base_url, exclude_prefixes):
                        sitemap.excluded.append(path_of(abs_url))
                        continue
                    if abs_url not in visited and depth + 1 <= max_depth:
                        queue.append((abs_url, depth + 1))
                    graph_urls.append(path_of(abs_url))
                # dedupe preserving order
                seen: set[str] = set()
                record.links = [l for l in record.links if not (l.href in seen or seen.add(l.href))]
                sitemap.graph[path_of(record.final_url)] = list(dict.fromkeys(graph_urls))
            except Exception as exc:  # navigation crash -> record and continue
                record.error = str(exc)[:300]
                if verbose:
                    print(f"  [error] {url}: {exc}")

            sitemap.pages.append(record)
            if verbose:
                print(f"  [{record.status or '??'}] {path_of(url)} -> {path_of(record.final_url)} "
                      f"({len(record.links)} links)")

    # Broken links: any recorded link whose target page resolved to >= 400.
    status_by_url = {p.url: p.status for p in sitemap.pages}
    broken_index: dict[str, Link] = {}
    for page in sitemap.pages:
        for link in page.links:
            abs_url = normalize_url(urljoin(page.final_url, link.href))
            target_status = status_by_url.get(abs_url)
            if target_status is not None and target_status >= 400:
                link.status = target_status
                entry = broken_index.setdefault(link.href, Link(href=link.href, text=link.text, status=target_status))
                entry.found_on.append(path_of(page.final_url))
    sitemap.broken_links = list(broken_index.values())

    sitemap.stats = {
        "pages_visited": len(sitemap.pages),
        "unique_urls": len(visited),
        "broken_links": len(sitemap.broken_links),
        "max_depth_reached": max((p.depth for p in sitemap.pages), default=0),
    }
    return sitemap
