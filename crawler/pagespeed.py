from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
SITE_URL = os.getenv(
    "GSC_SITE_URL",
    "https://engineerwala.com/",
).strip()

API_KEY = os.getenv(
    "PAGESPEED_API_KEY",
    "",
).strip()

URL_LIMIT = max(
    1,
    min(
        int(
            os.getenv(
                "PAGESPEED_URL_LIMIT",
                "5",
            )
        ),
        20,
    ),
)

STRATEGIES = (
    "mobile",
    "desktop",
)

CATEGORIES = (
    "performance",
    "accessibility",
    "best-practices",
    "seo",
)

DATA_DIR = Path("data")

AUDIT_JSON = (
    DATA_DIR /
    "latest_audit.json"
)

GSC_CSV = (
    DATA_DIR /
    "search_console_pages.csv"
)

OUTPUT_CSV = (
    DATA_DIR /
    "pagespeed_results.csv"
)

OUTPUT_JSON = (
    DATA_DIR /
    "pagespeed_summary.json"
)


def now_utc() -> str:
    return (
        datetime
        .now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace(
            "+00:00",
            "Z",
        )
    )


def number(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return default


def valid_url(url: str) -> bool:
    try:
        page = urlparse(url)
        site = urlparse(SITE_URL)

        return (
            page.scheme in {
                "http",
                "https",
            }
            and
            page.netloc.lower()
            ==
            site.netloc.lower()
        )

    except ValueError:
        return False


def read_audit_pages() -> list[
    dict[str, Any]
]:
    if not AUDIT_JSON.exists():
        return []

    with AUDIT_JSON.open(
        "r",
        encoding="utf-8",
    ) as handle:
        raw = json.load(handle)

    if isinstance(raw, list):
        return [
            row
            for row in raw
            if isinstance(
                row,
                dict,
            )
        ]

    if isinstance(raw, dict):
        for key in (
            "pages",
            "results",
            "data",
            "urls",
        ):
            rows = raw.get(key)

            if isinstance(
                rows,
                list,
            ):
                return [
                    row
                    for row in rows
                    if isinstance(
                        row,
                        dict,
                    )
                ]

    return []


def read_gsc_pages() -> list[
    dict[str, str]
]:
    if not GSC_CSV.exists():
        return []

    with GSC_CSV.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as handle:
        return list(
            csv.DictReader(handle)
        )


def select_urls() -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        url = str(
            value or ""
        ).strip()

        if (
            url
            and
            url not in seen
            and
            valid_url(url)
            and
            len(selected) < URL_LIMIT
        ):
            selected.append(url)
            seen.add(url)

    add(SITE_URL)

    gsc_rows = read_gsc_pages()

    gsc_rows.sort(
        key=lambda row: number(
            row.get(
                "current_impressions"
            )
        ),
        reverse=True,
    )

    for row in gsc_rows:
        add(
            row.get("page")
        )

    audit_rows = read_audit_pages()

    def audit_order(
        row: dict[str, Any],
    ) -> tuple[int, float]:
        priority = str(
            row.get("priority")
            or
            row.get("severity")
            or
            row.get("level")
            or
            ""
        ).lower()

        priority_order = (
            0
            if "critical" in priority
            else
            1
            if "high" in priority
            else
            2
            if "medium" in priority
            else
            3
        )

        score = number(
            row.get("seo_score")
            or
            row.get("score")
            or
            row.get("audit_score"),
            100,
        )

        return (
            priority_order,
            score,
        )

    audit_rows.sort(
        key=audit_order
    )

    for row in audit_rows:
        add(
            row.get("url")
            or
            row.get("page_url")
            or
            row.get("link")
        )

    return selected


def category_score(
    lighthouse: dict[str, Any],
    name: str,
) -> int:
    score = (
        lighthouse
        .get(
            "categories",
            {},
        )
        .get(
            name,
            {},
        )
        .get("score")
    )

    if score is None:
        return 0

    return round(
        number(score) * 100
    )


def audit_value(
    lighthouse: dict[str, Any],
    name: str,
) -> float:
    return number(
        lighthouse
        .get(
            "audits",
            {},
        )
        .get(
            name,
            {},
        )
        .get(
            "numericValue"
        )
    )


def top_opportunities(
    lighthouse: dict[str, Any],
) -> str:
    audits = lighthouse.get(
        "audits",
        {},
    )

    references = (
        lighthouse
        .get(
            "categories",
            {},
        )
        .get(
            "performance",
            {},
        )
        .get(
            "auditRefs",
            [],
        )
    )

    items: list[
        tuple[float, str]
    ] = []

    for reference in references:
        audit = audits.get(
            reference.get("id"),
            {},
        )

        if (
            not audit
            or
            audit.get("score")
            in (
                1,
                None,
            )
        ):
            continue

        title = str(
            audit.get(
                "title",
                "",
            )
        ).strip()

        details = audit.get(
            "details",
            {},
        )

        weight = (
            number(
                details.get(
                    "overallSavingsMs"
                )
            )
            +
            number(
                details.get(
                    "overallSavingsBytes"
                )
            )
            /
            1000
        )

        if title:
            items.append(
                (
                    weight,
                    title,
                )
            )

    items.sort(
        reverse=True
    )

    titles: list[str] = []

    for _, title in items:
        if title not in titles:
            titles.append(title)

        if len(titles) == 5:
            break

    return " | ".join(
        titles
    )


def fetch_pagespeed(
    url: str,
    strategy: str,
) -> dict[str, Any]:
    params: list[
        tuple[str, str]
    ] = [
        (
            "url",
            url,
        ),
        (
            "strategy",
            strategy,
        ),
        (
            "key",
            API_KEY,
        ),
    ]

    params.extend(
        (
            "category",
            category,
        )
        for category in CATEGORIES
    )

    last_error: Exception | None = None

    for attempt in range(
        1,
        4,
    ):
        try:
            response = requests.get(
                API_URL,
                params=params,
                timeout=180,
            )

            if response.status_code in {
                429,
                500,
                502,
                503,
                504,
            }:
                raise requests.HTTPError(
                    (
                        "Temporary PageSpeed "
                        f"API error "
                        f"{response.status_code}"
                    ),
                    response=response,
                )

            response.raise_for_status()

            return response.json()

        except requests.RequestException as error:
            last_error = error

            if attempt < 3:
                time.sleep(
                    2 ** attempt
                )

    raise RuntimeError(
        str(
            last_error
            or
            "PageSpeed request failed"
        )
    )


def analyze(
    url: str,
    strategy: str,
) -> dict[str, Any]:
    checked_at = now_utc()

    try:
        response = fetch_pagespeed(
            url,
            strategy,
        )

        lighthouse = response.get(
            "lighthouseResult",
            {},
        )

        runtime_error = lighthouse.get(
            "runtimeError"
        )

        if runtime_error:
            raise RuntimeError(
                runtime_error.get(
                    "message",
                    (
                        "Lighthouse "
                        "runtime error"
                    ),
                )
            )

        return {
            "url": url,
            "strategy": strategy,

            "performance_score":
                category_score(
                    lighthouse,
                    "performance",
                ),

            "accessibility_score":
                category_score(
                    lighthouse,
                    "accessibility",
                ),

            "best_practices_score":
                category_score(
                    lighthouse,
                    "best-practices",
                ),

            "seo_score":
                category_score(
                    lighthouse,
                    "seo",
                ),

            "first_contentful_paint_ms":
                round(
                    audit_value(
                        lighthouse,
                        (
                            "first-"
                            "contentful-paint"
                        ),
                    )
                ),

            "largest_contentful_paint_ms":
                round(
                    audit_value(
                        lighthouse,
                        (
                            "largest-"
                            "contentful-paint"
                        ),
                    )
                ),

            "speed_index_ms":
                round(
                    audit_value(
                        lighthouse,
                        "speed-index",
                    )
                ),

            "total_blocking_time_ms":
                round(
                    audit_value(
                        lighthouse,
                        (
                            "total-"
                            "blocking-time"
                        ),
                    )
                ),

            "cumulative_layout_shift":
                round(
                    audit_value(
                        lighthouse,
                        (
                            "cumulative-"
                            "layout-shift"
                        ),
                    ),
                    3,
                ),

            "server_response_time_ms":
                round(
                    audit_value(
                        lighthouse,
                        (
                            "server-"
                            "response-time"
                        ),
                    )
                ),

            "top_opportunities":
                top_opportunities(
                    lighthouse
                ),

            "final_url":
                str(
                    lighthouse.get(
                        "finalDisplayedUrl"
                    )
                    or
                    lighthouse.get(
                        "finalUrl"
                    )
                    or
                    url
                ),

            "lighthouse_version":
                str(
                    lighthouse.get(
                        "lighthouseVersion",
                        "",
                    )
                ),

            "checked_at":
                checked_at,

            "error":
                "",
        }

    except Exception as error:
        return {
            "url": url,
            "strategy": strategy,
            "performance_score": 0,
            "accessibility_score": 0,
            "best_practices_score": 0,
            "seo_score": 0,
            "first_contentful_paint_ms": 0,
            "largest_contentful_paint_ms": 0,
            "speed_index_ms": 0,
            "total_blocking_time_ms": 0,
            "cumulative_layout_shift": 0,
            "server_response_time_ms": 0,
            "top_opportunities": "",
            "final_url": "",
            "lighthouse_version": "",
            "checked_at": checked_at,
            "error": str(error),
        }


def average(
    rows: list[dict[str, Any]],
    strategy: str,
    field: str,
) -> int:
    values = [
        int(row[field])
        for row in rows
        if (
            row["strategy"] == strategy
            and
            not row["error"]
        )
    ]

    if not values:
        return 0

    return round(
        sum(values) /
        len(values)
    )


def save_reports(
    urls: list[str],
    rows: list[dict[str, Any]],
) -> None:
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    fields = [
        "url",
        "strategy",
        "performance_score",
        "accessibility_score",
        "best_practices_score",
        "seo_score",
        "first_contentful_paint_ms",
        "largest_contentful_paint_ms",
        "speed_index_ms",
        "total_blocking_time_ms",
        "cumulative_layout_shift",
        "server_response_time_ms",
        "top_opportunities",
        "final_url",
        "lighthouse_version",
        "checked_at",
        "error",
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
        writer.writerows(rows)

    successful = [
        row
        for row in rows
        if not row["error"]
    ]

    summary = {
        "generated_at":
            now_utc(),

        "site_url":
            SITE_URL,

        "url_limit":
            URL_LIMIT,

        "selected_urls":
            len(urls),

        "total_tests":
            len(rows),

        "successful_tests":
            len(successful),

        "failed_tests":
            (
                len(rows) -
                len(successful)
            ),

        "mobile": {
            "average_performance_score":
                average(
                    rows,
                    "mobile",
                    "performance_score",
                ),

            "average_accessibility_score":
                average(
                    rows,
                    "mobile",
                    "accessibility_score",
                ),

            "average_best_practices_score":
                average(
                    rows,
                    "mobile",
                    "best_practices_score",
                ),

            "average_seo_score":
                average(
                    rows,
                    "mobile",
                    "seo_score",
                ),
        },

        "desktop": {
            "average_performance_score":
                average(
                    rows,
                    "desktop",
                    "performance_score",
                ),

            "average_accessibility_score":
                average(
                    rows,
                    "desktop",
                    "accessibility_score",
                ),

            "average_best_practices_score":
                average(
                    rows,
                    "desktop",
                    "best_practices_score",
                ),

            "average_seo_score":
                average(
                    rows,
                    "desktop",
                    "seo_score",
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


def main() -> int:
    if not API_KEY:
        raise RuntimeError(
            (
                "PAGESPEED_API_KEY is "
                "missing from GitHub "
                "Actions secrets."
            )
        )

    urls = select_urls()

    if not urls:
        raise RuntimeError(
            (
                "No valid URLs found "
                "for PageSpeed testing."
            )
        )

    rows: list[
        dict[str, Any]
    ] = []

    total_tests = (
        len(urls) *
        len(STRATEGIES)
    )

    current_test = 0

    for url in urls:
        for strategy in STRATEGIES:
            current_test += 1

            print(
                (
                    f"[{current_test}/"
                    f"{total_tests}] "
                    f"Testing {strategy}: "
                    f"{url}"
                )
            )

            rows.append(
                analyze(
                    url,
                    strategy,
                )
            )

            time.sleep(0.4)

    save_reports(
        urls,
        rows,
    )

    print(
        f"Saved: {OUTPUT_CSV}"
    )

    print(
        f"Saved: {OUTPUT_JSON}"
    )

    if not any(
        not row["error"]
        for row in rows
    ):
        raise RuntimeError(
            (
                "Every PageSpeed "
                "request failed."
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
