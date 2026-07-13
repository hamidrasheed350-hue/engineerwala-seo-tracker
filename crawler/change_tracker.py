import csv
import os
import shutil
from datetime import datetime, timezone


DATA_DIRECTORY = "data"

CURRENT_AUDIT_FILE = os.path.join(
    DATA_DIRECTORY,
    "latest_audit.csv"
)

PREVIOUS_AUDIT_FILE = os.path.join(
    DATA_DIRECTORY,
    "previous_audit.csv"
)

CHANGE_LOG_FILE = os.path.join(
    DATA_DIRECTORY,
    "change_log.csv"
)


TRACKED_FIELDS = {
    "status_code": "HTTP status changed",
    "final_url": "Final URL changed",
    "title": "Page title changed",
    "meta_description": "Meta description changed",
    "canonical_url": "Canonical URL changed",
    "is_noindex": "Noindex status changed",
    "h1_count": "H1 count changed",
    "h2_count": "H2 count changed",
    "word_count": "Word count changed",
    "internal_links_count": "Internal links changed",
    "external_links_count": "External links changed",
    "image_count": "Image count changed",
    "missing_alt_count": "Missing alt count changed",
    "seo_score": "SEO score changed",
    "priority": "Page priority changed",
    "issue_count": "Issue count changed"
}


CHANGE_LOG_FIELDS = [
    "detected_at",
    "url",
    "change_type",
    "field",
    "old_value",
    "new_value",
    "change_summary"
]


def get_current_timestamp():
    """
    Current UTC timestamp return karta hai.
    """
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    ).replace(
        "+00:00",
        "Z"
    )


def read_audit_file(file_path):
    """
    Audit CSV ko URL-based dictionary mein read karta hai.
    """
    if not os.path.exists(file_path):
        return {}

    pages = {}

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            url = row.get(
                "url",
                ""
            ).strip()

            if url:
                pages[url] = row

    return pages


def clean_value(value):
    """
    Comparison ke liye values ko normalize karta hai.
    """
    if value is None:
        return ""

    return str(value).strip()


def create_change(
    timestamp,
    url,
    change_type,
    field,
    old_value,
    new_value,
    summary
):
    """
    Structured change-log row return karta hai.
    """
    return {
        "detected_at": timestamp,
        "url": url,
        "change_type": change_type,
        "field": field,
        "old_value": clean_value(old_value),
        "new_value": clean_value(new_value),
        "change_summary": summary
    }


def compare_existing_page(
    url,
    previous_page,
    current_page,
    timestamp
):
    """
    Same URL ke previous aur current values compare karta hai.
    """
    changes = []

    for field, summary in TRACKED_FIELDS.items():
        old_value = clean_value(
            previous_page.get(
                field,
                ""
            )
        )

        new_value = clean_value(
            current_page.get(
                field,
                ""
            )
        )

        if old_value == new_value:
            continue

        changes.append(
            create_change(
                timestamp=timestamp,
                url=url,
                change_type="Updated",
                field=field,
                old_value=old_value,
                new_value=new_value,
                summary=summary
            )
        )

    return changes


def compare_audits(
    previous_pages,
    current_pages
):
    """
    Previous aur current audits ka complete comparison karta hai.
    """
    timestamp = get_current_timestamp()
    changes = []

    previous_urls = set(
        previous_pages.keys()
    )

    current_urls = set(
        current_pages.keys()
    )

    new_urls = sorted(
        current_urls - previous_urls
    )

    removed_urls = sorted(
        previous_urls - current_urls
    )

    existing_urls = sorted(
        previous_urls & current_urls
    )

    for url in new_urls:
        changes.append(
            create_change(
                timestamp=timestamp,
                url=url,
                change_type="New Page",
                field="url",
                old_value="",
                new_value=url,
                summary="New URL website audit mein detect hui."
            )
        )

    for url in removed_urls:
        changes.append(
            create_change(
                timestamp=timestamp,
                url=url,
                change_type="Removed Page",
                field="url",
                old_value=url,
                new_value="",
                summary=(
                    "URL current website audit mein nahi mili. "
                    "Page removal, sitemap ya API status verify karo."
                )
            )
        )

    for url in existing_urls:
        page_changes = compare_existing_page(
            url=url,
            previous_page=previous_pages[url],
            current_page=current_pages[url],
            timestamp=timestamp
        )

        changes.extend(
            page_changes
        )

    return changes


def save_change_log(changes):
    """
    Current comparison ko data/change_log.csv mein save karta hai.
    """
    os.makedirs(
        DATA_DIRECTORY,
        exist_ok=True
    )

    with open(
        CHANGE_LOG_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=CHANGE_LOG_FIELDS
        )

        writer.writeheader()

        writer.writerows(
            changes
        )

    print(
        f"Change log saved: {CHANGE_LOG_FILE}"
    )

    print(
        f"Total changes detected: {len(changes)}"
    )


def save_current_as_previous():
    """
    Current audit ko next run ke baseline ke taur par save karta hai.
    """
    shutil.copyfile(
        CURRENT_AUDIT_FILE,
        PREVIOUS_AUDIT_FILE
    )

    print(
        f"Previous audit baseline updated: "
        f"{PREVIOUS_AUDIT_FILE}"
    )


def create_first_baseline():
    """
    Pehli run par current audit ko baseline banata hai.
    """
    save_change_log([])

    save_current_as_previous()

    print(
        "First baseline created. "
        "Agli crawl se real page changes detect honge."
    )


def main():
    """
    Complete change-tracking process run karta hai.
    """
    print(
        "EngineerWala change tracker started..."
    )

    if not os.path.exists(
        CURRENT_AUDIT_FILE
    ):
        raise FileNotFoundError(
            f"Current audit file nahi mili: "
            f"{CURRENT_AUDIT_FILE}"
        )

    if not os.path.exists(
        PREVIOUS_AUDIT_FILE
    ):
        create_first_baseline()
        return

    previous_pages = read_audit_file(
        PREVIOUS_AUDIT_FILE
    )

    current_pages = read_audit_file(
        CURRENT_AUDIT_FILE
    )

    changes = compare_audits(
        previous_pages,
        current_pages
    )

    save_change_log(
        changes
    )

    save_current_as_previous()


if __name__ == "__main__":
    main()
