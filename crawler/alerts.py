from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


DATA_DIR = Path("data")

AUDIT_FILE = DATA_DIR / "latest_audit.csv"
ISSUES_FILE = DATA_DIR / "issues.csv"
RECOMMENDATIONS_FILE = DATA_DIR / "recommendations.csv"
SEARCH_CONSOLE_FILE = DATA_DIR / "search_console_pages.csv"

CURRENT_ALERTS_FILE = DATA_DIR / "alerts_current.csv"
ALERTS_LOG_FILE = DATA_DIR / "alerts_log.csv"
ALERTS_SUMMARY_FILE = DATA_DIR / "alerts_summary.json"

PRIORITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}

ALERT_FIELDS = [
    "fingerprint",
    "priority",
    "alert_type",
    "url",
    "message",
    "recommended_action",
    "source",
    "metric",
    "first_detected",
    "last_seen",
    "occurrences",
    "status",
]


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
        "indexed",
        "index",
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


def fingerprint(
    alert_type: str,
    url: str,
    message: str,
) -> str:
    value = "|".join(
        (
            alert_type.lower(),
            normalize_url(url),
            message.lower(),
        )
    )

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:24]


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
        truthy(
            first(
                row,
                "is_noindex",
                "noindex",
            )
        )
        or
        "noindex" in robots
    )


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


def in_sitemap(row: dict[str, Any]) -> bool:
    return (
        truthy(
            first(
                row,
                "in_sitemap",
                "is_in_sitemap",
                "sitemap_present",
            )
        )
        or
        "sitemap"
        in
        text(
            first(
                row,
                "source",
                "url_source",
                "discovered_from",
            )
        ).lower()
    )


def main() -> int:
    now = utc_now()

    audit_rows = read_csv(AUDIT_FILE)
    issue_rows = read_csv(ISSUES_FILE)
    recommendation_rows = read_csv(RECOMMENDATIONS_FILE)
    search_console_rows = read_csv(SEARCH_CONSOLE_FILE)
    previous_log_rows = read_csv(ALERTS_LOG_FILE)

    detected: dict[str, dict[str, Any]] = {}

    def add_alert(
        *,
        priority: str,
        alert_type: str,
        url: str,
        message: str,
        recommended_action: str,
        source: str,
        metric: str = "",
    ) -> None:
        clean_message = text(message)
        clean_url = text(url)

        if not clean_message:
            return

        alert_id = fingerprint(
            alert_type,
            clean_url,
            clean_message,
        )

        detected[alert_id] = {
            "fingerprint": alert_id,
            "priority": normalize_priority(priority),
            "alert_type": text(alert_type),
            "url": clean_url,
            "message": clean_message,
            "recommended_action": text(recommended_action),
            "source": text(source),
            "metric": text(metric),
            "first_detected": now,
            "last_seen": now,
            "occurrences": 1,
            "status": "open",
        }

    for row in audit_rows:
        url = text(
            first(
                row,
                "url",
                "page_url",
                "link",
            )
        )

        code = status_code(row)

        if code >= 500:
            add_alert(
                priority="critical",
                alert_type="server_error",
                url=url,
                message=f"Server error detected: HTTP {code}",
                recommended_action=(
                    "Check hosting, application logs and server availability "
                    "immediately. Restore a successful response and rerun the "
                    "SEO audit."
                ),
                source="SEO Audit",
                metric=f"HTTP {code}",
            )

        elif code == 404:
            add_alert(
                priority="high",
                alert_type="not_found",
                url=url,
                message="Page returns HTTP 404",
                recommended_action=(
                    "Restore the page, correct internal links or add a relevant "
                    "301 redirect. Remove the URL from the sitemap if it should "
                    "not exist."
                ),
                source="SEO Audit",
                metric="HTTP 404",
            )

        if is_noindex(row) and in_sitemap(row):
            add_alert(
                priority="critical",
                alert_type="noindex_in_sitemap",
                url=url,
                message="Noindex page is present in the XML sitemap",
                recommended_action=(
                    "Remove the noindex directive when the page should rank, "
                    "or remove the URL from the sitemap when it should remain "
                    "excluded."
                ),
                source="SEO Audit",
                metric="noindex + sitemap",
            )

    for row in issue_rows:
        priority = normalize_priority(
            first(
                row,
                "severity",
                "priority",
                "level",
            )
        )

        if priority != "critical":
            continue

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
        ) or "Review and correct this critical SEO issue immediately."

        add_alert(
            priority="critical",
            alert_type="critical_seo_issue",
            url=text(
                first(
                    row,
                    "url",
                    "page_url",
                    "link",
                )
            ),
            message=issue or "Critical SEO issue detected",
            recommended_action=action,
            source="SEO Issues",
        )

    for row in recommendation_rows:
        priority = normalize_priority(
            row.get("priority")
        )

        issue = text(row.get("issue"))
        issue_lower = issue.lower()

        alert_type = ""

        if (
            "noindex page is present"
            in issue_lower
        ):
            alert_type = "noindex_in_sitemap"

        elif (
            "search clicks have dropped significantly"
            in issue_lower
        ):
            alert_type = "major_click_drop"

        elif (
            "search impressions have dropped significantly"
            in issue_lower
        ):
            alert_type = "major_impression_drop"

        elif priority == "critical":
            alert_type = "critical_recommendation"

        if not alert_type:
            continue

        add_alert(
            priority=priority,
            alert_type=alert_type,
            url=text(row.get("url")),
            message=issue,
            recommended_action=text(
                row.get("recommendation")
            ),
            source=text(row.get("source"))
            or
            "Recommendations",
            metric=text(row.get("metric")),
        )

    for row in search_console_rows:
        url = text(row.get("page"))

        current_clicks = number(
            row.get("current_clicks")
        )
        previous_clicks = number(
            row.get("previous_clicks")
        )

        current_impressions = number(
            row.get("current_impressions")
        )
        previous_impressions = number(
            row.get("previous_impressions")
        )

        click_drop = (
            previous_clicks >= 10
            and
            current_clicks
            <=
            previous_clicks * 0.70
        )

        impression_drop = (
            previous_impressions >= 50
            and
            current_impressions
            <=
            previous_impressions * 0.70
        )

        if click_drop:
            percentage = (
                (
                    current_clicks
                    -
                    previous_clicks
                )
                /
                previous_clicks
                *
                100
            )

            add_alert(
                priority="high",
                alert_type="major_click_drop",
                url=url,
                message="Search clicks dropped by at least 30%",
                recommended_action=(
                    "Check indexing, ranking changes, query performance and "
                    "recent title or content changes."
                ),
                source="Search Console",
                metric=(
                    f"{previous_clicks:.0f} → "
                    f"{current_clicks:.0f} "
                    f"({percentage:+.0f}%)"
                ),
            )

        if impression_drop:
            percentage = (
                (
                    current_impressions
                    -
                    previous_impressions
                )
                /
                previous_impressions
                *
                100
            )

            add_alert(
                priority="high",
                alert_type="major_impression_drop",
                url=url,
                message="Search impressions dropped by at least 30%",
                recommended_action=(
                    "Check index status, ranking position, search demand and "
                    "recent page changes."
                ),
                source="Search Console",
                metric=(
                    f"{previous_impressions:.0f} → "
                    f"{current_impressions:.0f} "
                    f"({percentage:+.0f}%)"
                ),
            )

    previous_by_id = {
        text(row.get("fingerprint")): row
        for row in previous_log_rows
        if text(row.get("fingerprint"))
    }

    new_alert_count = 0

    for alert_id, alert in detected.items():
        previous = previous_by_id.get(alert_id)

        if previous:
            alert["first_detected"] = (
                text(
                    previous.get(
                        "first_detected"
                    )
                )
                or
                now
            )

            alert["occurrences"] = (
                integer(
                    previous.get(
                        "occurrences"
                    ),
                    0,
                )
                +
                1
            )

        else:
            new_alert_count += 1

    combined_log: list[dict[str, Any]] = []

    for alert_id, previous in previous_by_id.items():
        if alert_id in detected:
            continue

        resolved = {
            field: text(
                previous.get(field)
            )
            for field in ALERT_FIELDS
        }

        resolved["status"] = "resolved"
        combined_log.append(resolved)

    combined_log.extend(
        detected.values()
    )

    combined_log.sort(
        key=lambda row: (
            0
            if row["status"] == "open"
            else
            1,
            PRIORITY_ORDER.get(
                row["priority"],
                99,
            ),
            row["alert_type"],
            normalize_url(row["url"]),
        )
    )

    current_alerts = list(
        detected.values()
    )

    current_alerts.sort(
        key=lambda row: (
            PRIORITY_ORDER.get(
                row["priority"],
                99,
            ),
            row["alert_type"],
            normalize_url(row["url"]),
        )
    )

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with CURRENT_ALERTS_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=ALERT_FIELDS,
        )

        writer.writeheader()
        writer.writerows(current_alerts)

    with ALERTS_LOG_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=ALERT_FIELDS,
        )

        writer.writeheader()
        writer.writerows(combined_log)

    priority_counts = {
        priority: sum(
            1
            for row in current_alerts
            if row["priority"] == priority
        )
        for priority in PRIORITY_ORDER
    }

    type_counts: dict[str, int] = {}

    for row in current_alerts:
        alert_type = row["alert_type"]

        type_counts[alert_type] = (
            type_counts.get(alert_type, 0)
            +
            1
        )

    resolved_count = sum(
        1
        for row in combined_log
        if row["status"] == "resolved"
    )

    summary = {
        "generated_at": now,
        "delivery_method": "dashboard_only",
        "email_notifications_enabled": False,
        "current_alerts": len(current_alerts),
        "new_alerts_this_run": new_alert_count,
        "resolved_alerts": resolved_count,
        "priority_counts": priority_counts,
        "alert_type_counts": dict(
            sorted(
                type_counts.items(),
                key=lambda item: (
                    -item[1],
                    item[0],
                ),
            )
        ),
        "meaningful_alert_rules": [
            "critical SEO issue",
            "HTTP 404",
            "HTTP 5xx server error",
            "noindex page present in sitemap",
            "major search clicks drop",
            "major search impressions drop",
        ],
        "reports": {
            "current_alerts": str(
                CURRENT_ALERTS_FILE
            ),
            "alerts_log": str(
                ALERTS_LOG_FILE
            ),
        },
    }

    with ALERTS_SUMMARY_FILE.open(
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
        f"Detected {len(current_alerts)} current alerts."
    )
    print(
        f"New alerts this run: {new_alert_count}"
    )
    print(
        f"Resolved alerts: {resolved_count}"
    )
    print(f"Saved: {CURRENT_ALERTS_FILE}")
    print(f"Saved: {ALERTS_LOG_FILE}")
    print(f"Saved: {ALERTS_SUMMARY_FILE}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
