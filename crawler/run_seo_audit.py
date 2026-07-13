import csv
import json
import os
from datetime import datetime, timezone

from seo_rules import analyse_page


INPUT_FILE = "data/basic_crawl.csv"
OUTPUT_DIRECTORY = "data"

LATEST_AUDIT_CSV = os.path.join(
    OUTPUT_DIRECTORY,
    "latest_audit.csv"
)

LATEST_AUDIT_JSON = os.path.join(
    OUTPUT_DIRECTORY,
    "latest_audit.json"
)

ISSUES_FILE = os.path.join(
    OUTPUT_DIRECTORY,
    "issues.csv"
)

SEVERITY_FILES = {
    "Critical": os.path.join(
        OUTPUT_DIRECTORY,
        "critical_issues.csv"
    ),
    "High": os.path.join(
        OUTPUT_DIRECTORY,
        "high_issues.csv"
    ),
    "Medium": os.path.join(
        OUTPUT_DIRECTORY,
        "medium_issues.csv"
    ),
    "Low": os.path.join(
        OUTPUT_DIRECTORY,
        "low_issues.csv"
    )
}

ISSUE_FIELDNAMES = [
    "crawl_timestamp",
    "url",
    "title",
    "seo_score",
    "page_priority",
    "severity",
    "issue",
    "explanation",
    "action"
]


def get_current_timestamp():
    """
    Current UTC time ko standard ISO format mein return karta hai.
    """
    current_time = datetime.now(
        timezone.utc
    )

    return current_time.isoformat(
        timespec="seconds"
    ).replace(
        "+00:00",
        "Z"
    )


def read_basic_crawl():
    """
    basic_crawl.csv se tamam crawled pages read karta hai.
    """
    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(
            f"Required file nahi mili: {INPUT_FILE}"
        )

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as file:
        reader = csv.DictReader(file)

        return list(reader)


def analyse_all_pages(
    pages,
    crawl_timestamp
):
    """
    Har crawled page par SEO rules run karta hai.
    """
    audit_results = []
    all_issues = []

    for page in pages:
        analysis = analyse_page(page)

        audit_row = dict(page)

        audit_row["crawl_timestamp"] = (
            crawl_timestamp
        )

        audit_row["seo_score"] = analysis[
            "seo_score"
        ]

        audit_row["priority"] = analysis[
            "priority"
        ]

        audit_row["issue_count"] = analysis[
            "issue_count"
        ]

        audit_row["exact_actions"] = analysis[
            "exact_actions"
        ]

        audit_results.append(
            audit_row
        )

        for issue in analysis["issues"]:
            issue_row = {
                "crawl_timestamp": crawl_timestamp,
                "url": page.get(
                    "url",
                    ""
                ),
                "title": page.get(
                    "title",
                    ""
                ),
                "seo_score": analysis[
                    "seo_score"
                ],
                "page_priority": analysis[
                    "priority"
                ],
                "severity": issue.get(
                    "severity",
                    ""
                ),
                "issue": issue.get(
                    "issue",
                    ""
                ),
                "explanation": issue.get(
                    "explanation",
                    ""
                ),
                "action": issue.get(
                    "action",
                    ""
                )
            }

            all_issues.append(
                issue_row
            )

        print(
            f"Analysed: {page.get('url', '')} | "
            f"Score: {analysis['seo_score']} | "
            f"Priority: {analysis['priority']} | "
            f"Issues: {analysis['issue_count']}"
        )

    return audit_results, all_issues


def save_latest_audit_csv(audit_results):
    """
    Page-wise audit ko latest_audit.csv mein save karta hai.
    """
    if not audit_results:
        print("Audit results empty hain.")
        return

    os.makedirs(
        OUTPUT_DIRECTORY,
        exist_ok=True
    )

    fieldnames = list(
        audit_results[0].keys()
    )

    with open(
        LATEST_AUDIT_CSV,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore"
        )

        writer.writeheader()

        writer.writerows(
            audit_results
        )

    print(
        f"Latest audit CSV saved: "
        f"{LATEST_AUDIT_CSV}"
    )


def save_latest_audit_json(
    audit_results,
    crawl_timestamp
):
    """
    Dashboard ke liye complete audit JSON format mein save karta hai.
    """
    report_data = {
        "generated_at": crawl_timestamp,
        "total_pages": len(
            audit_results
        ),
        "pages": audit_results
    }

    with open(
        LATEST_AUDIT_JSON,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            report_data,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"Latest audit JSON saved: "
        f"{LATEST_AUDIT_JSON}"
    )


def save_issues(all_issues):
    """
    Tamam SEO issues ko issues.csv mein save karta hai.
    """
    with open(
        ISSUES_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=ISSUE_FIELDNAMES
        )

        writer.writeheader()

        writer.writerows(
            all_issues
        )

    print(
        f"All SEO issues saved: "
        f"{ISSUES_FILE}"
    )


def save_severity_files(all_issues):
    """
    Critical, High, Medium aur Low issues ko
    separate CSV files mein save karta hai.
    """
    for severity, output_file in (
        SEVERITY_FILES.items()
    ):
        filtered_issues = [
            issue
            for issue in all_issues
            if issue.get(
                "severity"
            ) == severity
        ]

        with open(
            output_file,
            "w",
            newline="",
            encoding="utf-8"
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=ISSUE_FIELDNAMES
            )

            writer.writeheader()

            writer.writerows(
                filtered_issues
            )

        print(
            f"{severity} issues saved: "
            f"{output_file} | "
            f"Total: {len(filtered_issues)}"
        )


def print_summary(
    audit_results,
    all_issues,
    crawl_timestamp
):
    """
    Workflow log mein audit summary show karta hai.
    """
    total_pages = len(
        audit_results
    )

    severity_counts = {
        "Critical": 0,
        "High": 0,
        "Medium": 0,
        "Low": 0
    }

    for issue in all_issues:
        severity = issue.get(
            "severity"
        )

        if severity in severity_counts:
            severity_counts[severity] += 1

    if total_pages:
        score_total = sum(
            int(
                page.get(
                    "seo_score",
                    0
                )
            )
            for page in audit_results
        )

        average_score = round(
            score_total / total_pages,
            2
        )
    else:
        average_score = 0

    print("--------------------------------")
    print(f"Crawl timestamp: {crawl_timestamp}")
    print(f"Total pages analysed: {total_pages}")
    print(f"Average SEO score: {average_score}")
    print(
        f"Critical issues: "
        f"{severity_counts['Critical']}"
    )
    print(
        f"High issues: "
        f"{severity_counts['High']}"
    )
    print(
        f"Medium issues: "
        f"{severity_counts['Medium']}"
    )
    print(
        f"Low issues: "
        f"{severity_counts['Low']}"
    )
    print("--------------------------------")


def main():
    """
    Complete SEO audit aur report-generation process run karta hai.
    """
    print(
        "EngineerWala SEO rules analysis "
        "started..."
    )

    crawl_timestamp = (
        get_current_timestamp()
    )

    pages = read_basic_crawl()

    (
        audit_results,
        all_issues
    ) = analyse_all_pages(
        pages,
        crawl_timestamp
    )

    save_latest_audit_csv(
        audit_results
    )

    save_latest_audit_json(
        audit_results,
        crawl_timestamp
    )

    save_issues(
        all_issues
    )

    save_severity_files(
        all_issues
    )

    print_summary(
        audit_results,
        all_issues,
        crawl_timestamp
    )


if __name__ == "__main__":
    main()
