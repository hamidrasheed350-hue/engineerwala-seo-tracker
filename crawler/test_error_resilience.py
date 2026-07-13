import csv
import os

from main import crawl_page


FAILED_URL = "http://127.0.0.1:1/seo-tracker-test"
VALID_URL = "https://engineerwala.com/"

OUTPUT_FILE = "data/error_resilience_test.csv"


def main():
    """
    Pehle jaan-boojh kar failing URL crawl karta hai.
    Phir homepage crawl karke confirm karta hai ke
    crawler failure ke baad bhi continue hua.
    """
    print("Intentional failing URL test started...")

    failed_result = crawl_page(
        FAILED_URL
    )

    print("Ab valid homepage crawl ho rahi hai...")

    valid_result = crawl_page(
        VALID_URL
    )

    failure_recorded = bool(
        str(
            failed_result.get(
                "crawl_error",
                ""
            )
        ).strip()
    )

    next_page_status = str(
        valid_result.get(
            "status_code",
            ""
        )
    )

    crawler_continued = (
        next_page_status == "200"
    )

    test_passed = (
        failure_recorded
        and crawler_continued
    )

    os.makedirs(
        "data",
        exist_ok=True
    )

    fieldnames = [
        "failed_url",
        "failed_url_error",
        "next_url",
        "next_url_status",
        "crawler_continued",
        "test_passed"
    ]

    row = {
        "failed_url": FAILED_URL,
        "failed_url_error": failed_result.get(
            "crawl_error",
            ""
        ),
        "next_url": VALID_URL,
        "next_url_status": next_page_status,
        "crawler_continued": crawler_continued,
        "test_passed": test_passed
    }

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerow(row)

    print(
        f"Error resilience report saved: "
        f"{OUTPUT_FILE}"
    )

    print(
        f"Failure recorded: {failure_recorded}"
    )

    print(
        f"Next page status: {next_page_status}"
    )

    print(
        f"Crawler continued: {crawler_continued}"
    )

    print(
        f"Test passed: {test_passed}"
    )


if __name__ == "__main__":
    main()
