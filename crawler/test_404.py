import csv
import os

from main import crawl_page


TEST_URL = (
    "https://engineerwala.com/"
    "seo-tracker-404-test-page-987654321/"
)

OUTPUT_FILE = "data/404_test.csv"


def save_test_result(result):
    """
    404 test result ko CSV file mein save karta hai.
    """
    os.makedirs(
        "data",
        exist_ok=True
    )

    status_code = result.get(
        "status_code",
        ""
    )

    test_passed = (
        str(status_code) == "404"
    )

    fieldnames = [
        "test_url",
        "status_code",
        "final_url",
        "crawl_error",
        "test_passed"
    ]

    row = {
        "test_url": TEST_URL,
        "status_code": status_code,
        "final_url": result.get(
            "final_url",
            ""
        ),
        "crawl_error": result.get(
            "crawl_error",
            ""
        ),
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
        f"404 test result saved: {OUTPUT_FILE}"
    )

    print(
        f"Detected status code: {status_code}"
    )

    print(
        f"404 detection passed: {test_passed}"
    )


def main():
    """
    Non-existing page ko crawl karke
    HTTP status detection test karta hai.
    """
    print(
        f"Testing non-existing URL: {TEST_URL}"
    )

    result = crawl_page(
        TEST_URL
    )

    save_test_result(
        result
    )


if __name__ == "__main__":
    main()
