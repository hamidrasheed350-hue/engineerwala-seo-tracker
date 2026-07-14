"""
Inspect a limited set of EngineerWala URLs with the Google Search Console
URL Inspection API.

Required environment variable:
- GSC_SERVICE_ACCOUNT_JSON

Optional environment variables:
- GSC_SITE_URL (default: https://engineerwala.com/)
- URL_INSPECTION_LIMIT (default: 20, maximum: 100)

Generated files:
- data/url_inspection.csv
- data/url_inspection_summary.json
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
DEFAULT_SITE_URL = "https://engineerwala.com/"
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

DATA_DIRECTORY = Path("data")
AUDIT_JSON = DATA_DIRECTORY / "latest_audit.json"
GSC_PAGES_CSV = DATA_DIRECTORY / "search_console_pages.csv"
OUTPUT_CSV = DATA_DIRECTORY / "url_inspection.csv"
OUTPUT_SUMMARY = DATA_DIRECTORY / "url_inspection_summary.json"


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def load_credentials():
    raw_json = os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "").strip()

    if not raw_json:
        raise RuntimeError(
            "GSC_SERVICE_ACCOUNT_JSON is missing from GitHub Actions secrets."
        )

    try:
        credentials_info = json.loads(raw_json)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "GSC_SERVICE_ACCOUNT_JSON does not contain valid JSON."
        ) from error

    return service_account.Credentials.from_service_account_info(
        credentials_info,
        scopes=SCOPES,
    )


def build_service():
    return build(
        "searchconsole",
        "v1",
        credentials=load_credentials(),
        cache_discovery=False,
    )


def read_audit_pages() -> list[dict[str, Any]]:
    if not AUDIT_JSON.exists():
        return []

    with AUDIT_JSON.open("r", encoding="utf-8") as file:
        raw = json.load(file)

    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]

    if isinstance(raw, dict):
        for key in ("pages", "results", "data", "urls"):
            value = raw.get(key)

            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

    return []


def read_search_console_pages() -> list[dict[str, str]]:
    if not GSC_PAGES_CSV.exists():
        return []

    with GSC_PAGES_CSV.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        return list(csv.DictReader(file))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return default


def normalize_priority(value: Any) -> int:
    priority = str(value or "").strip().lower()

    if "critical" in priority:
        return 0

    if "high" in priority:
        return 1

    if "medium" in priority:
        return 2

    return 3


def normalize_url(url: Any) -> str:
    return str(url or "").strip()


def url_belongs_to_property(url: str, site_url: str) -> bool:
    try:
        inspected = urlparse(url)
        property_url = urlparse(site_url)

        return (
            inspected.scheme in {"http", "https"}
            and inspected.netloc.lower()
            == property_url.netloc.lower()
        )

    except ValueError:
        return False


def add_unique_url(
    selected: list[str],
    seen: set[str],
    url: Any,
    site_url: str,
    limit: int,
) -> None:
    clean_url = normalize_url(url)

    if (
        clean_url
        and clean_url not in seen
        and url_belongs_to_property(clean_url, site_url)
        and len(selected) < limit
    ):
        selected.append(clean_url)
        seen.add(clean_url)


def select_urls(site_url: str, limit: int) -> list[str]:
    audit_pages = read_audit_pages()
    performance_pages = read_search_console_pages()

    selected: list[str] = []
    seen: set[str] = set()

    # Homepage sab se pehle inspect hogi.
    add_unique_url(
        selected,
        seen,
        site_url,
        site_url,
        limit,
    )

    # Pehle Critical aur High priority pages.
    priority_pages = sorted(
        audit_pages,
        key=lambda page: (
            normalize_priority(
                page.get("priority")
                or page.get("severity")
                or page.get("level")
            ),
            safe_float(
                page.get("seo_score")
                or page.get("score")
                or page.get("audit_score"),
                100.0,
            ),
        ),
    )

    for page in priority_pages:
        priority_value = normalize_priority(
            page.get("priority")
            or page.get("severity")
            or page.get("level")
        )

        if priority_value <= 1:
            add_unique_url(
                selected,
                seen,
                page.get("url")
                or page.get("page_url")
                or page.get("link"),
                site_url,
                limit,
            )

    # Phir Search Console mein zyada impressions wale pages.
    performance_pages.sort(
        key=lambda row: safe_float(
            row.get("current_impressions")
        ),
        reverse=True,
    )

    for row in performance_pages:
        add_unique_url(
            selected,
            seen,
            row.get("page"),
            site_url,
            limit,
        )

    # Remaining space mein baqi audit pages.
    for page in priority_pages:
        add_unique_url(
            selected,
            seen,
            page.get("url")
            or page.get("page_url")
            or page.get("link"),
            site_url,
            limit,
        )

    return selected


def execute_inspection(
    service,
    site_url: str,
    inspection_url: str,
    max_attempts: int = 3,
) -> dict[str, Any]:
    body = {
        "inspectionUrl": inspection_url,
        "siteUrl": site_url,
        "languageCode": "en-US",
    }

    for attempt in range(1, max_attempts + 1):
        try:
            return (
                service.urlInspection()
                .index()
                .inspect(body=body)
                .execute()
            )

        except HttpError as error:
            status_code = getattr(
                error.resp,
                "status",
                None,
            )

            if (
                status_code in RETRYABLE_STATUS_CODES
                and attempt < max_attempts
            ):
                time.sleep(2 ** attempt)
                continue

            raise

    raise RuntimeError(
        f"Inspection failed for {inspection_url}"
    )


def human_index_status(
    verdict: str,
    coverage_state: str,
) -> str:
    if verdict == "PASS":
        return "Indexed"

    if verdict in {"NEUTRAL", "FAIL"}:
        return "Not indexed"

    if coverage_state:
        return "Unknown"

    return "Inspection unavailable"


def inspect_url(
    service,
    site_url: str,
    inspection_url: str,
) -> dict[str, Any]:
    checked_at = utc_now()

    try:
        response = execute_inspection(
            service,
            site_url,
            inspection_url,
        )

        inspection_result = response.get(
            "inspectionResult",
            {},
        )

        index_result = inspection_result.get(
            "indexStatusResult",
            {},
        )

        verdict = str(
            index_result.get("verdict", "")
        )

        coverage_state = str(
            index_result.get("coverageState", "")
        )

        return {
            "url": inspection_url,
            "index_status": human_index_status(
                verdict,
                coverage_state,
            ),
            "verdict": verdict or "UNKNOWN",
            "coverage_state": (
                coverage_state or "Unavailable"
            ),
            "robots_txt_state": index_result.get(
                "robotsTxtState",
                "UNKNOWN",
            ),
            "indexing_state": index_result.get(
                "indexingState",
                "UNKNOWN",
            ),
            "page_fetch_state": index_result.get(
                "pageFetchState",
                "UNKNOWN",
            ),
            "last_crawl_time": index_result.get(
                "lastCrawlTime",
                "",
            ),
            "google_canonical": index_result.get(
                "googleCanonical",
                "",
            ),
            "user_canonical": index_result.get(
                "userCanonical",
                "",
            ),
            "crawled_as": index_result.get(
                "crawledAs",
                "UNKNOWN",
            ),
            "sitemaps": " | ".join(
                index_result.get("sitemap", [])
            ),
            "inspection_result_link": (
                inspection_result.get(
                    "inspectionResultLink",
                    "",
                )
            ),
            "checked_at": checked_at,
            "error": "",
        }

    except Exception as error:
        return {
            "url": inspection_url,
            "index_status": "Inspection unavailable",
            "verdict": "ERROR",
            "coverage_state": "Unavailable",
            "robots_txt_state": "UNKNOWN",
            "indexing_state": "UNKNOWN",
            "page_fetch_state": "UNKNOWN",
            "last_crawl_time": "",
            "google_canonical": "",
            "user_canonical": "",
            "crawled_as": "UNKNOWN",
            "sitemaps": "",
            "inspection_result_link": "",
            "checked_at": checked_at,
            "error": str(error),
        }


def save_csv(rows: list[dict[str, Any]]) -> None:
    DATA_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = [
        "url",
        "index_status",
        "verdict",
        "coverage_state",
        "robots_txt_state",
        "indexing_state",
        "page_fetch_state",
        "last_crawl_time",
        "google_canonical",
        "user_canonical",
        "crawled_as",
        "sitemaps",
        "inspection_result_link",
        "checked_at",
        "error",
    ]

    with OUTPUT_CSV.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)


def save_summary(
    site_url: str,
    limit: int,
    rows: list[dict[str, Any]],
) -> None:
    summary = {
        "generated_at": utc_now(),
        "site_url": site_url,
        "inspection_limit": limit,
        "inspected_urls": len(rows),
        "indexed": sum(
            row["index_status"] == "Indexed"
            for row in rows
        ),
        "not_indexed": sum(
            row["index_status"] == "Not indexed"
            for row in rows
        ),
        "inspection_unavailable": sum(
            row["index_status"]
            == "Inspection unavailable"
            for row in rows
        ),
        "unknown": sum(
            row["index_status"] == "Unknown"
            for row in rows
        ),
    }

    with OUTPUT_SUMMARY.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            summary,
            file,
            ensure_ascii=False,
            indent=2,
        )


def main() -> int:
    site_url = os.environ.get(
        "GSC_SITE_URL",
        DEFAULT_SITE_URL,
    ).strip()

    try:
        requested_limit = int(
            os.environ.get(
                "URL_INSPECTION_LIMIT",
                str(DEFAULT_LIMIT),
            )
        )

    except ValueError:
        requested_limit = DEFAULT_LIMIT

    limit = max(
        1,
        min(requested_limit, MAX_LIMIT),
    )

    urls = select_urls(
        site_url,
        limit,
    )

    if not urls:
        print(
            "No valid URLs were found for inspection.",
            file=sys.stderr,
        )
        return 1

    print(f"URL Inspection property: {site_url}")
    print(f"URLs selected: {len(urls)}")

    service = build_service()
    rows: list[dict[str, Any]] = []

    for position, url in enumerate(
        urls,
        start=1,
    ):
        print(
            f"[{position}/{len(urls)}] "
            f"Inspecting {url}"
        )

        rows.append(
            inspect_url(
                service,
                site_url,
                url,
            )
        )

        time.sleep(0.15)

    save_csv(rows)

    save_summary(
        site_url,
        limit,
        rows,
    )

    print(f"Saved: {OUTPUT_CSV}")
    print(f"Saved: {OUTPUT_SUMMARY}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
