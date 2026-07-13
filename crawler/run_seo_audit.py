import csv
import os

from seo_rules import analyse_page


INPUT_FILE = "data/basic_crawl.csv"
OUTPUT_DIRECTORY = "data"

LATEST_AUDIT_FILE = os.path.join(
    OUTPUT_DIRECTORY,
    "latest_audit.csv"
)

ISSUES_FILE = os.path.join(
    OUTPUT_DIRECTORY,
    "issues.csv"
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


def analyse_all_pages(pages):
    """
    Har crawled page par SEO rules run karta hai.
    """
    audit_results = []
    all_issues = []

    for page in pages:
        analysis = analyse_page(page)

        audit_row = dict(page)

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
            all_issues.append({
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
            })

        print(
            f"Analysed: {page.get('url', '')} | "
            f"Score: {analysis['seo_score']} | "
            f"Priority: {analysis['priority']} | "
            f"Issues: {analysis['issue_count']}"
        )

    return audit_results, all_issues


def save_latest_audit(audit_results):
    """
    Page-wise complete audit data latest_audit.csv mein save karta hai.
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
        LATEST_AUDIT_FILE,
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
        f"Latest audit saved: "
        f"{LATEST_AUDIT_FILE}"
    )


def save_issues(all_issues):
    """
    Tamam individual SEO issues ko issues.csv mein save karta hai.
    """
    os.makedirs(
        OUTPUT_DIRECTORY,
        exist_ok=True
    )

    fieldnames = [
        "url",
        "title",
        "seo_score",
        "page_priority",
        "severity",
        "issue",
        "explanation",
        "action"
    ]

    with open(
        ISSUES_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(
            all_issues
        )

    print(
        f"SEO issues saved: "
        f"{ISSUES_FILE}"
    )


def print_summary(
    audit_results,
    all_issues
):
    """
    Terminal mein audit ka short summary show karta hai.
    """
    total_pages = len(
        audit_results
    )

    critical_issues = sum(
        1
        for issue in all_issues
        if issue.get("severity") == "Critical"
    )

    high_issues = sum(
        1
        for issue in all_issues
        if issue.get("severity") == "High"
    )

    medium_issues = sum(
        1
        for issue in all_issues
        if issue.get("severity") == "Medium"
    )

    low_issues = sum(
        1
        for issue in all_issues
        if issue.get("severity") == "Low"
    )

    if total_pages:
        average_score = round(
            sum(
                int(
                    page.get(
                        "seo_score",
                        0
                    )
                )
                for page in audit_results
            ) / total_pages,
            2
        )
    else:
        average_score = 0

    print("--------------------------------")
    print(f"Total pages analysed: {total_pages}")
    print(f"Average SEO score: {average_score}")
    print(f"Critical issues: {critical_issues}")
    print(f"High issues: {high_issues}")
    print(f"Medium issues: {medium_issues}")
    print(f"Low issues: {low_issues}")
    print("--------------------------------")


def main():
    """
    Complete SEO audit process run karta hai.
    """
    print(
        "EngineerWala SEO rules analysis "
        "started..."
    )

    pages = read_basic_crawl()

    audit_results, all_issues = (
        analyse_all_pages(
            pages
        )
    )

    save_latest_audit(
        audit_results
    )

    save_issues(
        all_issues
    )

    print_summary(
        audit_results,
        all_issues
    )


if __name__ == "__main__":
    main()
