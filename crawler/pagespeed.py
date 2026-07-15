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


def integer_env(
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(
            os.getenv(
                name,
                str(default),
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        value = default

    return max(
        minimum,
        min(
            value,
            maximum,
        ),
    )


URL_LIMIT = integer_env(
    "PAGESPEED_URL_LIMIT",
    5,
    1,
    20,
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

RESULT_FIELDS = [
    "url",
    "strategy",
    "performance_score",
    "accessibility_score",
    "best_practices_score",
    "seo_score",
    "first_contentful_paint_ms",
    "largest_contentful_paint_ms",
    "interaction_to_next_paint_ms",
    "inp_source",
    "field_data_category",
    "origin_field_data_category",
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


def now_utc() -> str:
    return (
        datetime
        .now(timezone.utc)
        .isoformat(
            timespec="seconds"
        )
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


def valid_url(
    url: str,
) -> bool:
    try:
        page = urlparse(url)
        site = urlparse(SITE_URL)

        return (
            page.scheme in {
                "http",
                "https",
            }
            and
            bool(page.netloc)
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

    try:
        with AUDIT_JSON.open(
            "r",
            encoding="utf-8",
        ) as handle:
            raw = json.load(handle)

    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        print(
            (
                f"Warning: could not read "
                f"{AUDIT_JSON}: {error}"
            )
        )

        return []

    if isinstance(
        raw,
        list,
    ):
        return [
            row
            for row in raw
            if isinstance(
                row,
                dict,
            )
        ]

    if isinstance(
        raw,
        dict,
    ):
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

    try:
        with GSC_CSV.open(
            "r",
            newline="",
            encoding="utf-8-sig",
        ) as handle:
            return list(
                csv.DictReader(
                    handle
                )
            )

    except OSError as error:
        print(
            (
                f"Warning: could not read "
                f"{GSC_CSV}: {error}"
            )
        )

        return []


def select_urls() -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()

    def add(
        value: Any,
    ) -> None:
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
            len(selected)
            <
            URL_LIMIT
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
            row.get(
                "audit_score"
            ),
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
        number(score) *
        100
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


def experience_category(
    response: dict[str, Any],
    key: str,
) -> str:
    category = (
        response
        .get(
            key,
            {},
        )
        .get(
            "overall_category"
        )
    )

    return str(
        category
        or
        "UNAVAILABLE"
    ).strip()


def field_metric(
    response: dict[str, Any],
    metric_name: str,
) -> tuple[int, str]:
    page_metric = (
        response
        .get(
            "loadingExperience",
            {},
        )
        .get(
            "metrics",
            {},
        )
        .get(
            metric_name,
            {},
        )
    )

    page_percentile = (
        page_metric.get(
            "percentile"
        )
    )

    if page_percentile is not None:
        return (
            round(
                number(
                    page_percentile
                )
            ),
            "page",
        )

    origin_metric = (
        response
        .get(
            "originLoadingExperience",
            {},
        )
        .get(
            "metrics",
            {},
        )
        .get(
            metric_name,
            {},
        )
    )

    origin_percentile = (
        origin_metric.get(
            "percentile"
        )
    )

    if origin_percentile is not None:
        return (
            round(
                number(
                    origin_percentile
                )
            ),
            "origin",
        )

    return (
        0,
        "unavailable",
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
    ]

    if API_KEY:
        params.append(
            (
                "key",
                API_KEY,
            )
        )

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
                        "API error "
                        f"{response.status_code}"
                    ),
                    response=response,
                )

            response.raise_for_status()

            return response.json()

        except (
            requests.RequestException,
            ValueError,
        ) as error:
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


def empty_result(
    url: str,
    strategy: str,
    checked_at: str,
    error: str,
) -> dict[str, Any]:
    return {
        "url":
            url,

        "strategy":
            strategy,

        "performance_score":
            0,

        "accessibility_score":
            0,

        "best_practices_score":
            0,

        "seo_score":
            0,

        "first_contentful_paint_ms":
            0,

        "largest_contentful_paint_ms":
            0,

        "interaction_to_next_paint_ms":
            0,

        "inp_source":
            "unavailable",

        "field_data_category":
            "UNAVAILABLE",

        "origin_field_data_category":
            "UNAVAILABLE",

        "speed_index_ms":
            0,

        "total_blocking_time_ms":
            0,

        "cumulative_layout_shift":
            0,

        "server_response_time_ms":
            0,

        "top_opportunities":
            "",

        "final_url":
            "",

        "lighthouse_version":
            "",

        "checked_at":
            checked_at,

        "error":
            error,
    }


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

        inp_ms, inp_source = (
            field_metric(
                response,
                (
                    "INTERACTION_"
                    "TO_NEXT_PAINT"
                ),
            )
        )

        return {
            "url":
                url,

            "strategy":
                strategy,

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

            "interaction_to_next_paint_ms":
                inp_ms,

            "inp_source":
                inp_source,

            "field_data_category":
                experience_category(
                    response,
                    (
                        "loadingExperience"
                    ),
                ),

            "origin_field_data_category":
                experience_category(
                    response,
                    (
                        "originLoadingExperience"
                    ),
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
        return empty_result(
            url,
            strategy,
            checked_at,
            str(error),
        )


def average(
    rows: list[dict[str, Any]],
    strategy: str,
    field: str,
) -> int:
    values = [
        number(
            row.get(field)
        )
        for row in rows
        if (
            row.get("strategy")
            ==
            strategy
            and
            not row.get("error")
        )
    ]

    if not values:
        return 0

    return round(
        sum(values)
        /
        len(values)
    )


def average_inp(
    rows: list[dict[str, Any]],
    strategy: str,
) -> int:
    values = [
        number(
            row.get(
                "interaction_to_next_paint_ms"
            )
        )
        for row in rows
        if (
            row.get("strategy")
            ==
            strategy
            and
            not row.get("error")
            and
            row.get("inp_source")
            in {
                "page",
                "origin",
            }
            and
            number(
                row.get(
                    "interaction_to_next_paint_ms"
                )
            )
            >
            0
        )
    ]

    if not values:
        return 0

    return round(
        sum(values)
        /
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

    with OUTPUT_CSV.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=RESULT_FIELDS,
        )

        writer.writeheader()
        writer.writerows(rows)

    successful = [
        row
        for row in rows
        if not row.get("error")
    ]

    failed = [
        row
        for row in rows
        if row.get("error")
    ]

    inp_available = [
        row
        for row in successful
        if (
            row.get("inp_source")
            in {
                "page",
                "origin",
            }
            and
            number(
                row.get(
                    "interaction_to_next_paint_ms"
                )
            )
            >
            0
        )
    ]

    if (
        len(successful)
        ==
        len(rows)
        and
        rows
    ):
        run_status = "healthy"

    elif successful:
        run_status = "degraded"

    else:
        run_status = "unavailable"

    summary = {
        "generated_at":
            now_utc(),

        "site_url":
            SITE_URL,

        "run_status":
            run_status,

        "api_key_configured":
            bool(API_KEY),

        "url_limit":
            URL_LIMIT,

        "selected_urls":
            len(urls),

        "total_tests":
            len(rows),

        "successful_tests":
            len(successful),

        "failed_tests":
            len(failed),

        "inp_available_tests":
            len(inp_available),

        "inp_unavailable_tests":
            (
                len(successful)
                -
                len(inp_available)
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

            "average_inp_ms":
                average_inp(
                    rows,
                    "mobile",
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

            "average_inp_ms":
                average_inp(
                    rows,
                    "desktop",
                ),
        },

        "errors": [
            {
                "url":
                    row.get(
                        "url",
                        "",
                    ),

                "strategy":
                    row.get(
                        "strategy",
                        "",
                    ),

                "message":
                    row.get(
                        "error",
                        "",
                    ),
            }
            for row in failed
        ],
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
        print(
            (
                "Warning: PAGESPEED_API_KEY "
                "is missing. The API request "
                "will be attempted without "
                "a key."
            )
        )

    urls = select_urls()

    if not urls:
        fallback_url = (
            SITE_URL
            or
            "https://engineerwala.com/"
        )

        urls = [
            fallback_url
        ]

        print(
            (
                "Warning: no priority URLs "
                "were found; using fallback "
                f"URL {fallback_url}"
            )
        )

    rows: list[
        dict[str, Any]
    ] = []

    total_tests = (
        len(urls)
        *
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

            result = analyze(
                url,
                strategy,
            )

            rows.append(result)

            if result.get("error"):
                print(
                    (
                        "Warning: PageSpeed "
                        "test failed but the "
                        "workflow will continue: "
                        f"{result['error']}"
                    )
                )

            time.sleep(0.4)

    save_reports(
        urls,
        rows,
    )

    successful_tests = sum(
        1
        for row in rows
        if not row.get("error")
    )

    print(
        f"Saved: {OUTPUT_CSV}"
    )

    print(
        f"Saved: {OUTPUT_JSON}"
    )

    print(
        (
            "PageSpeed completed without "
            "blocking the workflow: "
            f"{successful_tests}/"
            f"{len(rows)} tests successful."
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
