from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path("data")

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


def number(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)

    except (TypeError, ValueError):
        return default


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        print(f"Skipped missing file: {path}")
        return []

    with path.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as handle:
        return list(csv.DictReader(handle))


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

    if any(
        word in value
        for word in (
            "status",
            "404",
            "500",
            "crawl",
            "redirect",
            "server",
        )
    ):
        return "Technical"

    if any(
        word in value
        for word in (
            "title",
            "meta",
            "h1",
            "heading",
            "word count",
            "content",
        )
    ):
        return "Content"

    if any(
        word in value
        for word in (
            "canonical",
            "robots",
            "noindex",
            "index",
            "sitemap",
        )
    ):
        return "Indexing"

    if any(
        word in value
        for word in (
            "image",
            "alt",
        )
    ):
        return "Images"

    if any(
        word in value
        for word in (
            "link",
            "orphan",
        )
    ):
        return "Internal Links"

    return "SEO"


def main() -> int:
    generated_at = utc_now()

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
            clean_url,
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

    # -------------------------------------------------
    # Existing SEO audit issues
    # -------------------------------------------------

    for row in read_csv(ISSUES_FILE):
        issue = text(
            row.get("issue")
            or row.get("issue_type")
            or row.get("problem")
            or row.get("message")
        )

        action = text(
            row.get("action")
            or row.get("recommended_action")
            or row.get("recommendation")
            or row.get("fix")
        )

        if not action:
            action = (
                "Review the page and correct the reported "
                "SEO issue."
            )

        add(
            priority=text(
                row.get("severity")
                or row.get("priority")
                or row.get("level")
            ),
            category=classify_issue(issue),
            url=text(
                row.get("url")
                or row.get("page_url")
                or row.get("link")
            ),
            issue=issue or "SEO audit issue",
            recommendation=action,
            source="SEO Audit",
        )

    # -------------------------------------------------
    # Google URL Inspection recommendations
    # -------------------------------------------------

    for row in read_csv(INSPECTION_FILE):
        url = text(row.get("url"))
        index_status = text(
            row.get("index_status")
        )
        coverage = text(
            row.get("coverage_state")
        )
        error = text(row.get("error"))

        if error:
            add(
                priority="high",
                category="Indexing",
                url=url,
                issue="Google URL inspection failed",
                recommendation=(
                    "Review Search Console access and run "
                    "URL Inspection again."
                ),
                source="URL Inspection",
                metric=error,
            )

        elif index_status.lower() != "indexed":
            add(
                priority="high",
                category="Indexing",
                url=url,
                issue=(
                    coverage
                    or
                    "Page is not indexed by Google"
                ),
                recommendation=(
                    "Confirm that the page is indexable, "
                    "included in the XML sitemap and linked "
                    "internally. After correcting any issue, "
                    "request indexing in Google Search Console."
                ),
                source="URL Inspection",
                metric=index_status or "Not indexed",
            )

    # -------------------------------------------------
    # Search Console recommendations
    # -------------------------------------------------

    for row in read_csv(GSC_FILE):
        url = text(row.get("page"))

        clicks = number(
            row.get("current_clicks")
        )

        impressions = number(
            row.get("current_impressions")
        )

        previous_impressions = number(
            row.get("previous_impressions")
        )

        impressions_change = number(
            row.get("impressions_change")
        )

        position = number(
            row.get("current_position")
        )

        ctr = number(
            row.get("current_ctr_percent")
        )

        if impressions >= 20 and clicks == 0:
            add(
                priority="medium",
                category="Search Performance",
                url=url,
                issue=(
                    "Page receives impressions but no clicks"
                ),
                recommendation=(
                    "Improve the SEO title and meta description "
                    "so they better match search intent and "
                    "encourage users to click."
                ),
                source="Search Console",
                metric=(
                    f"{int(impressions)} impressions, "
                    "0 clicks"
                ),
            )

        if (
            impressions >= 20
            and 8 <= position <= 20
        ):
            add(
                priority="medium",
                category="Search Performance",
                url=url,
                issue=(
                    "Page is close to the first page "
                    "of Google"
                ),
                recommendation=(
                    "Expand the content, improve internal links "
                    "and strengthen relevance for the search "
                    "queries already generating impressions."
                ),
                source="Search Console",
                metric=f"Average position {position:.1f}",
            )

        if (
            impressions_change <= -20
            or (
                previous_impressions >= 50
                and impressions
                < previous_impressions * 0.7
            )
        ):
            add(
                priority="high",
                category="Search Performance",
                url=url,
                issue="Search impressions have dropped",
                recommendation=(
                    "Check whether rankings, content, title, "
                    "indexing or competing pages changed. "
                    "Compare the current page with the "
                    "previously successful version."
                ),
                source="Search Console",
                metric=(
                    f"Impressions change "
                    f"{impressions_change:+.0f}"
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
                    "Low click-through rate for a "
                    "high-visibility page"
                ),
                recommendation=(
                    "Rewrite the SEO title and description "
                    "to communicate a clearer benefit and "
                    "match the main search query."
                ),
                source="Search Console",
                metric=(
                    f"CTR {ctr:.2f}%, "
                    f"position {position:.1f}"
                ),
            )

    # -------------------------------------------------
    # PageSpeed recommendations
    # -------------------------------------------------

    for row in read_csv(PAGESPEED_FILE):
        url = text(row.get("url"))
        strategy = text(
            row.get("strategy")
        ).capitalize()

        error = text(row.get("error"))

        performance = number(
            row.get("performance_score")
        )

        accessibility = number(
            row.get("accessibility_score")
        )

        lcp = number(
            row.get(
                "largest_contentful_paint_ms"
            )
        )

        cls = number(
            row.get(
                "cumulative_layout_shift"
            )
        )

        tbt = number(
            row.get(
                "total_blocking_time_ms"
            )
        )

        opportunities = text(
            row.get("top_opportunities")
        )

        if error:
            add(
                priority="high",
                category="Performance",
                url=url,
                issue=f"{strategy} PageSpeed test failed",
                recommendation=(
                    "Review the PageSpeed API response and "
                    "run the performance test again."
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
                "Review the Lighthouse opportunities and "
                "reduce render-blocking resources, large "
                "images and unnecessary JavaScript."
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
                    f"{strategy} performance score "
                    f"is {performance:.0f}"
                ),
                recommendation=recommendation,
                source="PageSpeed",
                metric=f"Score {performance:.0f}",
            )

        if lcp > 4000:
            lcp_priority = "critical"

        elif lcp > 2500:
            lcp_priority = "high"

        else:
            lcp_priority = ""

        if lcp_priority:
            add(
                priority=lcp_priority,
                category="Core Web Vitals",
                url=url,
                issue=(
                    f"{strategy} Largest Contentful "
                    "Paint is slow"
                ),
                recommendation=(
                    "Optimize the main visible image or content, "
                    "preload the LCP resource and reduce server "
                    "and render-blocking delays."
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
                issue=(
                    f"{strategy} layout shift is too high"
                ),
                recommendation=(
                    "Reserve width and height for images, ads "
                    "and embedded content. Avoid inserting "
                    "content above existing page elements."
                ),
                source="PageSpeed",
                metric=f"CLS {cls:.3f}",
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
                issue=(
                    f"{strategy} Total Blocking Time "
                    "is too high"
                ),
                recommendation=(
                    "Reduce unused JavaScript, split long tasks "
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
                    f"{strategy} accessibility score "
                    f"is {accessibility:.0f}"
                ),
                recommendation=(
                    "Review Lighthouse accessibility audits, "
                    "including contrast, labels, link names "
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
            row["url"].lower(),
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

    for row in recommendations:
        category = row["category"]

        category_counts[category] = (
            category_counts.get(
                category,
                0,
            )
            + 1
        )

    affected_urls = {
        row["url"]
        for row in recommendations
        if row["url"]
    }

    summary = {
        "generated_at": generated_at,
        "total_recommendations": len(
            recommendations
        ),
        "affected_urls": len(
            affected_urls
        ),
        "priority_counts": priority_counts,
        "category_counts": dict(
            sorted(
                category_counts.items(),
                key=lambda item: (
                    -item[1],
                    item[0],
                ),
            )
        ),
        "source_files": {
            "seo_issues": str(ISSUES_FILE),
            "search_console": str(GSC_FILE),
            "url_inspection": str(
                INSPECTION_FILE
            ),
            "pagespeed": str(
                PAGESPEED_FILE
            ),
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
