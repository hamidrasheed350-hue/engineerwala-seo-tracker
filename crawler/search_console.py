"""
Fetch page-level Google Search Console data for EngineerWala.

Required environment variable:
- GSC_SERVICE_ACCOUNT_JSON: complete service-account JSON stored as a GitHub Secret

Optional environment variable:
- GSC_SITE_URL: exact Search Console property name
  Default: https://engineerwala.com/

Generated files:
- data/search_console_pages.csv
- data/search_console_summary.json
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
DEFAULT_SITE_URL = "https://engineerwala.com/"
OUTPUT_DIRECTORY = Path("data")
PAGES_OUTPUT = OUTPUT_DIRECTORY / "search_console_pages.csv"
SUMMARY_OUTPUT = OUTPUT_DIRECTORY / "search_console_summary.json"
ROW_LIMIT = 25_000
FINAL_DATA_DELAY_DAYS = 3


def load_credentials():
    raw_credentials = os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw_credentials:
        raise RuntimeError(
            "GSC_SERVICE_ACCOUNT_JSON secret is missing. "
            "Add it in GitHub Settings > Secrets and variables > Actions."
        )

    try:
        credentials_info = json.loads(raw_credentials)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "GSC_SERVICE_ACCOUNT_JSON is not valid JSON. "
            "Copy the complete JSON key into the GitHub Secret."
        ) from error

    required_fields = {"client_email", "private_key", "token_uri"}
    missing_fields = required_fields.difference(credentials_info)
    if missing_fields:
        raise RuntimeError(
            "Service-account JSON is missing required fields: "
            + ", ".join(sorted(missing_fields))
        )

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


def verify_property_access(service, site_url: str) -> str:
    site = service.sites().get(siteUrl=site_url).execute()
    permission_level = str(site.get("permissionLevel", "unknown"))
    if permission_level in {"siteUnverifiedUser", "unknown"}:
        raise RuntimeError(
            f"Service account does not have usable access to {site_url}. "
            "Add its email in Search Console > Settings > Users and permissions."
        )
    return permission_level


def query_search_analytics(
    service,
    site_url: str,
    start_date: date,
    end_date: date,
    dimensions: list[str] | None = None,
) -> list[dict[str, Any]]:
    dimensions = dimensions or []
    all_rows: list[dict[str, Any]] = []
    start_row = 0

    while True:
        request_body: dict[str, Any] = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "type": "web",
            "dataState": "final",
            "rowLimit": ROW_LIMIT,
            "startRow": start_row,
        }
        if dimensions:
            request_body["dimensions"] = dimensions

        response = (
            service.searchanalytics()
            .query(siteUrl=site_url, body=request_body)
            .execute()
        )
        rows = response.get("rows", [])
        all_rows.extend(rows)
        if len(rows) < ROW_LIMIT:
            break
        start_row += ROW_LIMIT

    return all_rows


def metric_value(row: dict[str, Any] | None, key: str) -> float:
    if not row:
        return 0.0
    try:
        return float(row.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def percent_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return ((current - previous) / previous) * 100


def round_metric(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def page_rows_by_url(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        keys = row.get("keys", [])
        if not keys:
            continue
        page_url = str(keys[0]).strip()
        if page_url:
            result[page_url] = row
    return result


def build_page_comparison(
    current_rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current_by_page = page_rows_by_url(current_rows)
    previous_by_page = page_rows_by_url(previous_rows)
    all_pages = sorted(set(current_by_page) | set(previous_by_page))
    report_rows: list[dict[str, Any]] = []

    for page_url in all_pages:
        current = current_by_page.get(page_url)
        previous = previous_by_page.get(page_url)

        current_clicks = metric_value(current, "clicks")
        previous_clicks = metric_value(previous, "clicks")
        current_impressions = metric_value(current, "impressions")
        previous_impressions = metric_value(previous, "impressions")
        current_ctr = metric_value(current, "ctr")
        previous_ctr = metric_value(previous, "ctr")
        current_position = metric_value(current, "position")
        previous_position = metric_value(previous, "position")

        clicks_change_pct = percent_change(current_clicks, previous_clicks)
        impressions_change_pct = percent_change(current_impressions, previous_impressions)

        report_rows.append(
            {
                "page": page_url,
                "current_clicks": round_metric(current_clicks),
                "previous_clicks": round_metric(previous_clicks),
                "clicks_change": round_metric(current_clicks - previous_clicks),
                "clicks_change_percent": "" if clicks_change_pct is None else round_metric(clicks_change_pct),
                "current_impressions": round_metric(current_impressions),
                "previous_impressions": round_metric(previous_impressions),
                "impressions_change": round_metric(current_impressions - previous_impressions),
                "impressions_change_percent": "" if impressions_change_pct is None else round_metric(impressions_change_pct),
                "current_ctr_percent": round_metric(current_ctr * 100),
                "previous_ctr_percent": round_metric(previous_ctr * 100),
                "ctr_change_points": round_metric((current_ctr - previous_ctr) * 100),
                "current_position": round_metric(current_position),
                "previous_position": round_metric(previous_position),
                "position_change": round_metric(current_position - previous_position),
            }
        )

    report_rows.sort(
        key=lambda row: (
            -float(row["current_clicks"]),
            -float(row["current_impressions"]),
            row["page"],
        )
    )
    return report_rows


def summarize_period(rows: list[dict[str, Any]]) -> dict[str, float]:
    row = rows[0] if rows else {}
    return {
        "clicks": round_metric(metric_value(row, "clicks")),
        "impressions": round_metric(metric_value(row, "impressions")),
        "ctr_percent": round_metric(metric_value(row, "ctr") * 100),
        "position": round_metric(metric_value(row, "position")),
    }


def save_pages_csv(rows: list[dict[str, Any]]) -> None:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "page",
        "current_clicks",
        "previous_clicks",
        "clicks_change",
        "clicks_change_percent",
        "current_impressions",
        "previous_impressions",
        "impressions_change",
        "impressions_change_percent",
        "current_ctr_percent",
        "previous_ctr_percent",
        "ctr_change_points",
        "current_position",
        "previous_position",
        "position_change",
    ]
    with PAGES_OUTPUT.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def save_summary_json(summary: dict[str, Any]) -> None:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with SUMMARY_OUTPUT.open("w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)


def main() -> int:
    site_url = os.environ.get("GSC_SITE_URL", DEFAULT_SITE_URL).strip()
    stable_end_date = date.today() - timedelta(days=FINAL_DATA_DELAY_DAYS)
    current_start = stable_end_date - timedelta(days=6)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)

    print("Google Search Console data fetch started.")
    print(f"Property: {site_url}")
    print(f"Current period: {current_start} to {stable_end_date}")
    print(f"Previous period: {previous_start} to {previous_end}")

    try:
        service = build_service()
        permission_level = verify_property_access(service, site_url)

        current_page_rows = query_search_analytics(
            service, site_url, current_start, stable_end_date, dimensions=["page"]
        )
        previous_page_rows = query_search_analytics(
            service, site_url, previous_start, previous_end, dimensions=["page"]
        )
        current_summary_rows = query_search_analytics(
            service, site_url, current_start, stable_end_date
        )
        previous_summary_rows = query_search_analytics(
            service, site_url, previous_start, previous_end
        )

        page_report = build_page_comparison(current_page_rows, previous_page_rows)
        summary = {
            "generated_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "site_url": site_url,
            "permission_level": permission_level,
            "data_state": "final",
            "final_data_delay_days": FINAL_DATA_DELAY_DAYS,
            "current_period": {
                "start_date": current_start.isoformat(),
                "end_date": stable_end_date.isoformat(),
                **summarize_period(current_summary_rows),
            },
            "previous_period": {
                "start_date": previous_start.isoformat(),
                "end_date": previous_end.isoformat(),
                **summarize_period(previous_summary_rows),
            },
            "page_count": len(page_report),
        }

        save_pages_csv(page_report)
        save_summary_json(summary)

        print(f"Property access: {permission_level}")
        print(f"Page rows saved: {len(page_report)}")
        print(f"Saved: {PAGES_OUTPUT}")
        print(f"Saved: {SUMMARY_OUTPUT}")
        return 0

    except HttpError as error:
        print(
            "Search Console API request failed. Check the property URL, "
            "service-account access and API status.",
            file=sys.stderr,
        )
        print(str(error), file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Search Console integration failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
