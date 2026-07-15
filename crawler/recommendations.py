from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


DATA_DIR = Path("data")
URLS_FILE = DATA_DIR / "urls.csv"
AUDIT_FILE = DATA_DIR / "latest_audit.csv"
ISSUES_FILE = DATA_DIR / "issues.csv"
GSC_FILE = DATA_DIR / "search_console_pages.csv"
INSPECTION_FILE = DATA_DIR / "url_inspection.csv"
PAGESPEED_FILE = DATA_DIR / "pagespeed_results.csv"

OUTPUT_CSV = DATA_DIR / "recommendations.csv"
OUTPUT_JSON = DATA_DIR / "recommendations_summary.json"

PRIORITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def text(value: Any) -> str:
    return str(value or "").strip()


def number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def integer(value: Any, default: int = 0) -> int:
    return round(number(value, default))


def truthy(value: Any) -> bool:
    return text(value).lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
        "index",
        "indexed",
    }


def first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def normalize_url(value: Any) -> str:
    url = text(value)
    if not url:
        return ""

    try:
        parts = urlsplit(url)
        if not parts.scheme or not parts.netloc:
            return url.rstrip("/").lower()

        path = parts.path or "/"
        if path != "/":
            path = path.rstrip("/")

        return urlunsplit(
            (
                parts.scheme.lower(),
                parts.netloc.lower(),
                path,
                parts.query,
                "",
            )
        )
    except ValueError:
        return url.rstrip("/").lower()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        print(f"Skipped missing file: {path}")
        return []

    try:
        with path.open(
            "r",
            newline="",
            encoding="utf-8-sig",
        ) as handle:
            return list(csv.DictReader(handle))
    except OSError as error:
        print(f"Skipped unreadable file {path}: {error}")
        return []


def normalize_priority(value: Any) -> str:
    priority = text(value).lower()

    if priority in PRIORITY_ORDER:
        return priority
    if "critical" in priority:
        return "critical"
    if "high" in priority:
        return "high"
    if "low" in priority:
        return "low"
    return "medium"


def classify_issue(issue: str) -> str:
    value = issue.lower()

    groups = {
        "Technical": (
            "status",
            "404",
            "500",
            "crawl",
            "redirect",
            "server",
            "timeout",
        ),
        "Content": (
            "title",
            "meta",
            "h1",
            "heading",
            "word count",
            "content",
        ),
        "Indexing": (
            "canonical",
            "robots",
            "noindex",
            "index",
            "sitemap",
        ),
        "Images": (
            "image",
            "alt",
        ),
        "Internal Links": (
            "link",
            "orphan",
        ),
        "Performance": (
            "lcp",
            "cls",
            "inp",
            "speed",
            "performance",
            "blocking",
        ),
    }

    for category, keywords in groups.items():
        if any(keyword in value for keyword in keywords):
            return category

    return "SEO"


def status_code(row: dict[str, Any]) -> int:
    return integer(
        first(
            row,
            "status_code",
            "status",
            "http_status",
            "response_code",
        )
    )


def is_noindex(row: dict[str, Any]) -> bool:
    robots = text(
        first(
            row,
            "robots_directives",
            "robots",
            "x_robots_tag",
        )
    ).lower()

    return (
        truthy(first(row, "is_noindex", "noindex"))
        or "noindex" in robots
    )


def internal_links(row: dict[str, Any]) -> int:
    return integer(
        first(
            row,
            "internal_links_count",
            "internal_links",
            "links_internal",
        )
    )


def find_sitemap_urls(
    url_rows: list[dict[str, str]],
    inspection_rows: list[dict[str, str]],
) -> set[str]:
    found: set[str] = set()

    for row in url_rows:
        url = normalize_url(
            first(
                row,
                "url",
                "page_url",
                "link",
                "loc",
            )
        )
        source = text(
            first(
                row,
                "source",
                "url_source",
                "origin",
                "discovered_from",
                "type",
            )
        ).lower()
        explicit = first(
            row,
            "in_sitemap",
            "is_in_sitemap",
            "sitemap_present",
        )

        if url and (
            "sitemap" in source
            or truthy(explicit)
        ):
            found.add(url)

    for row in inspection_rows:
        url = normalize_url(row.get("url"))
        if url and text(row.get("sitemaps")):
            found.add(url)

    return found


def main() -> int:
    generated_at = utc_now()

    url_rows = read_csv(URLS_FILE)
    audit_rows = read_csv(AUDIT_FILE)
    issue_rows = read_csv(ISSUES_FILE)
    gsc_rows = read_csv(GSC_FILE)
    inspection_rows = read_csv(INSPECTION_FILE)
    pagespeed_rows = read_csv(PAGESPEED_FILE)

    sitemap_set = find_sitemap_urls(
        url_rows,
        inspection_rows,
    )

    recommendations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add(
        *,
        priority: str,
        category: str,
        url: str,
        issue: str,
        recommendation: str,
        source: str,
        metric: str = "",
    ) -> None:
        clean_url = text(url)
        clean_issue = text(issue)
        clean_recommendation = text(recommendation)

        if not clean_issue or not clean_recommendation:
            return

        key = (
            normalize_url(clean_url),
            category.lower(),
            clean_issue.lower(),
            clean_recommendation.lower(),
        )

        if key in seen:
            return

        seen.add(key)

        recommendations.append({
            "priority": normalize_priority(priority),
            "category": category,
            "url": clean_url,
            "issue": clean_issue,
            "recommendation": clean_recommendation,
            "source": source,
            "metric": metric,
            "detected_at": generated_at,
        })

    for row in issue_rows:
        issue = text(
            first(
                row,
                "issue",
                "issue_type",
                "problem",
                "message",
            )
        )
        action = text(
            first(
                row,
                "action",
                "recommended_action",
                "recommendation",
                "fix",
            )
        ) or "Review the page and correct the reported SEO issue."

        add(
            priority=text(
                first(
                    row,
                    "severity",
                    "priority",
                    "level",
                )
            ),
            category=classify_issue(issue),
            url=text(
                first(
                    row,
                    "url",
                    "page_url",
                    "link",
                )
            ),
            issue=issue or "SEO audit issue",
            recommendation=action,
            source="SEO Audit",
        )

    for row in audit_rows:
        url = text(
            first(
                row,
                "url",
                "page_url",
                "link",
            )
        )
        normalized = normalize_url(url)
        code = status_code(row)
        links = internal_links(row)

        if is_noindex(row) and normalized in sitemap_set:
            add(
                priority="critical",
                category="Indexing",
                url=url,
                issue="Noindex page is present in the XML sitemap",
                recommendation=(
                    "Decide whether this page should appear in Google. "
                    "If it should be indexed, remove the noindex directive. "
                    "If it should remain excluded, remove it from the XML "
                    "sitemap. Regenerate the sitemap and validate the URL "
                    "in Google Search Console."
                ),
                source="Audit + Sitemap",
                metric="noindex + sitemap",
            )

        if code == 200 and links == 0:
            add(
                priority="high",
                category="Internal Links",
                url=url,
                issue=(
                    "Orphan-risk page: HTTP 200 with zero internal links"
                ),
                recommendation=(
                    "Add at least two relevant internal links from existing "
                    "indexed pages, category pages or navigation. Use "
                    "descriptive anchor text and confirm the next crawl "
                    "reports more than zero internal links."
                ),
                source="SEO Audit",
                metric="200 status, 0 internal links",
            )

    for row in inspection_rows:
        url = text(row.get("url"))
        index_status = text(row.get("index_status"))
        coverage = text(row.get("coverage_state"))
        error = text(row.get("error"))

        if error:
            add(
                priority="high",
                category="Indexing",
                url=url,
                issue="Google URL inspection failed",
                recommendation=(
                    "Review Search Console access, confirm that the property "
                    "matches the URL and run URL Inspection again."
                ),
                source="URL Inspection",
                metric=error,
            )
        elif index_status.lower() != "indexed":
            add(
                priority="high",
                category="Indexing",
                url=url,
                issue=coverage or "Page is not indexed by Google",
                recommendation=(
                    "Confirm HTTP 200, indexability, canonical, XML sitemap "
                    "presence and internal links. Correct the cause and then "
                    "request indexing in Google Search Console."
                ),
                source="URL Inspection",
                metric=index_status or "Not indexed",
            )

    for row in gsc_rows:
        url = text(row.get("page"))

        clicks = number(row.get("current_clicks"))
        previous_clicks = number(row.get("previous_clicks"))
        clicks_change = number(row.get("clicks_change"))

        impressions = number(row.get("current_impressions"))
        previous_impressions = number(
            row.get("previous_impressions")
        )
        impressions_change = number(
            row.get("impressions_change")
        )

        position = number(row.get("current_position"))
        ctr = number(row.get("current_ctr_percent"))

        if impressions >= 20 and clicks == 0:
            add(
                priority="medium",
                category="Search Performance",
                url=url,
                issue="Page receives impressions but no clicks",
                recommendation=(
                    "Rewrite the SEO title and meta description to match "
                    "search intent, include the main topic and communicate "
                    "a clearer benefit. Recheck CTR after the next period."
                ),
                source="Search Console",
                metric=f"{int(impressions)} impressions, 0 clicks",
            )

        if impressions >= 20 and 8 <= position <= 20:
            add(
                priority="medium",
                category="Search Performance",
                url=url,
                issue="Page is close to the first page of Google",
                recommendation=(
                    "Refresh the page around queries already generating "
                    "impressions, answer missing subtopics and add relevant "
                    "internal links from stronger indexed pages."
                ),
                source="Search Console",
                metric=f"Average position {position:.1f}",
            )

        clicks_dropped = (
            clicks_change <= -5
            or (
                previous_clicks >= 10
                and clicks <= previous_clicks * 0.70
            )
        )

        if clicks_dropped:
            percentage = (
                (
                    clicks - previous_clicks
                )
                / previous_clicks
                * 100
                if previous_clicks > 0
                else 0
            )

            add(
                priority="high",
                category="Search Performance",
                url=url,
                issue="Search clicks have dropped significantly",
                recommendation=(
                    "Compare the current and previous page version, check "
                    "indexing and ranking changes, review the main queries "
                    "and inspect whether the title or search intent changed."
                ),
                source="Search Console",
                metric=(
                    f"Clicks {previous_clicks:.0f} → {clicks:.0f} "
                    f"({percentage:+.0f}%)"
                ),
            )

        impressions_dropped = (
            impressions_change <= -20
            or (
                previous_impressions >= 50
                and impressions
                <= previous_impressions * 0.70
            )
        )

        if impressions_dropped:
            percentage = (
                (
                    impressions - previous_impressions
                )
                / previous_impressions
                * 100
                if previous_impressions > 0
                else 0
            )

            add(
                priority="high",
                category="Search Performance",
                url=url,
                issue="Search impressions have dropped significantly",
                recommendation=(
                    "Check indexing, ranking position, query relevance and "
                    "recent content changes. Compare the page with competing "
                    "results and restore or expand useful sections."
                ),
                source="Search Console",
                metric=(
                    f"Impressions {previous_impressions:.0f} → "
                    f"{impressions:.0f} ({percentage:+.0f}%)"
                ),
            )

        if (
            impressions >= 100
            and ctr < 1
            and position <= 10
        ):
            add(
                priority="high",
                category="Search Performance",
                url=url,
                issue=(
                    "Low click-through rate for a high-visibility page"
                ),
                recommendation=(
                    "Rewrite the title and meta description to match the "
                    "main query, show a specific benefit and differentiate "
                    "the result from competing pages."
                ),
                source="Search Console",
                metric=f"CTR {ctr:.2f}%, position {position:.1f}",
            )

    for row in pagespeed_rows:
        url = text(row.get("url"))
        strategy = text(row.get("strategy")).capitalize()
        error = text(row.get("error"))

        performance = number(row.get("performance_score"))
        accessibility = number(row.get("accessibility_score"))
        lcp = number(row.get("largest_contentful_paint_ms"))
        cls = number(row.get("cumulative_layout_shift"))
        tbt = number(row.get("total_blocking_time_ms"))
        inp = number(
            row.get("interaction_to_next_paint_ms")
        )
        inp_source = text(row.get("inp_source"))
        opportunities = text(row.get("top_opportunities"))

        if error:
            add(
                priority="high",
                category="Performance",
                url=url,
                issue=f"{strategy} PageSpeed test failed",
                recommendation=(
                    "Review the PageSpeed error, confirm the URL is publicly "
                    "accessible and run the test again. The remaining SEO "
                    "workflow should continue even when this test fails."
                ),
                source="PageSpeed",
                metric=error,
            )
            continue

        if performance < 50:
            priority = "critical"
        elif performance < 75:
            priority = "high"
        elif performance < 90:
            priority = "medium"
        else:
            priority = ""

        if priority:
            recommendation = (
                "Reduce render-blocking resources, optimize large images "
                "and remove or delay unnecessary JavaScript."
            )
            if opportunities:
                recommendation += (
                    f" Main opportunities: {opportunities}."
                )

            add(
                priority=priority,
                category="Performance",
                url=url,
                issue=(
                    f"{strategy} performance score is "
                    f"{performance:.0f}"
                ),
                recommendation=recommendation,
                source="PageSpeed",
                metric=f"Score {performance:.0f}",
            )

        if lcp > 2500:
            add(
                priority=(
                    "critical"
                    if lcp > 4000
                    else "high"
                ),
                category="Core Web Vitals",
                url=url,
                issue=f"{strategy} Largest Contentful Paint is slow",
                recommendation=(
                    "Identify the LCP element, optimize and correctly size "
                    "its image, preload the critical resource and reduce "
                    "server or render-blocking delays."
                ),
                source="PageSpeed",
                metric=f"LCP {lcp / 1000:.2f}s",
            )

        if cls > 0.10:
            add(
                priority=(
                    "high"
                    if cls > 0.25
                    else "medium"
                ),
                category="Core Web Vitals",
                url=url,
                issue=f"{strategy} layout shift is too high",
                recommendation=(
                    "Reserve width and height for images, ads and embeds. "
                    "Avoid inserting late-loading content above existing "
                    "elements and stabilize web-font loading."
                ),
                source="PageSpeed",
                metric=f"CLS {cls:.3f}",
            )

        if (
            inp > 200
            and inp_source in {"page", "origin"}
        ):
            add(
                priority=(
                    "high"
                    if inp > 500
                    else "medium"
                ),
                category="Core Web Vitals",
                url=url,
                issue=(
                    f"{strategy} Interaction to Next Paint is slow"
                ),
                recommendation=(
                    "Reduce long JavaScript tasks, split heavy event handlers, "
                    "defer non-essential scripts and update the page quickly "
                    "after user input. Recheck INP using field data."
                ),
                source="PageSpeed",
                metric=f"INP {inp:.0f}ms ({inp_source} data)",
            )

        if tbt > 300:
            add(
                priority=(
                    "high"
                    if tbt > 600
                    else "medium"
                ),
                category="Performance",
                url=url,
                issue=f"{strategy} Total Blocking Time is too high",
                recommendation=(
                    "Reduce unused JavaScript, split long main-thread tasks "
                    "and delay non-essential third-party scripts."
                ),
                source="PageSpeed",
                metric=f"TBT {tbt:.0f}ms",
            )

        if accessibility < 90:
            add(
                priority="medium",
                category="Accessibility",
                url=url,
                issue=(
                    f"{strategy} accessibility score is "
                    f"{accessibility:.0f}"
                ),
                recommendation=(
                    "Review Lighthouse accessibility audits, especially "
                    "contrast, form labels, link names, image alternatives "
                    "and heading structure."
                ),
                source="PageSpeed",
                metric=f"Score {accessibility:.0f}",
            )

    recommendations.sort(
        key=lambda row: (
            PRIORITY_ORDER.get(
                row["priority"],
                99,
            ),
            row["category"].lower(),
            normalize_url(row["url"]),
            row["issue"].lower(),
        )
    )

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    fields = [
        "priority",
        "category",
        "url",
        "issue",
        "recommendation",
        "source",
        "metric",
        "detected_at",
    ]

    with OUTPUT_CSV.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )
        writer.writeheader()
        writer.writerows(recommendations)

    priority_counts = {
        priority: sum(
            1
            for row in recommendations
            if row["priority"] == priority
        )
        for priority in PRIORITY_ORDER
    }

    category_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}

    for row in recommendations:
        category = row["category"]
        source = row["source"]

        category_counts[category] = (
            category_counts.get(category, 0)
            + 1
        )
        source_counts[source] = (
            source_counts.get(source, 0)
            + 1
        )

    affected_urls = {
        normalize_url(row["url"])
        for row in recommendations
        if row["url"]
    }

    summary = {
        "generated_at": generated_at,
        "total_recommendations": len(recommendations),
        "affected_urls": len(affected_urls),
        "priority_counts": priority_counts,
        "category_counts": dict(
            sorted(
                category_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ),
        "source_counts": dict(
            sorted(
                source_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ),
        "special_rule_counts": {
            "noindex_in_sitemap": sum(
                1
                for row in recommendations
                if row["metric"] == "noindex + sitemap"
            ),
            "orphan_risk": sum(
                1
                for row in recommendations
                if row["metric"]
                == "200 status, 0 internal links"
            ),
            "major_click_drops": sum(
                1
                for row in recommendations
                if row["issue"]
                == "Search clicks have dropped significantly"
            ),
            "major_impression_drops": sum(
                1
                for row in recommendations
                if row["issue"]
                == "Search impressions have dropped significantly"
            ),
            "slow_inp": sum(
                1
                for row in recommendations
                if "Interaction to Next Paint" in row["issue"]
            ),
        },
        "source_files": {
            "url_collection": str(URLS_FILE),
            "seo_audit": str(AUDIT_FILE),
            "seo_issues": str(ISSUES_FILE),
            "search_console": str(GSC_FILE),
            "url_inspection": str(INSPECTION_FILE),
            "pagespeed": str(PAGESPEED_FILE),
        },
    }

    with OUTPUT_JSON.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            summary,
            handle,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"Generated {len(recommendations)} "
        "automatic recommendations."
    )
    print(f"Saved: {OUTPUT_CSV}")
    print(f"Saved: {OUTPUT_JSON}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
