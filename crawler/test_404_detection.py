from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import requests


TEST_URL = (
    "https://engineerwala.com/"
    "seo-tracker-404-test-page-does-not-exist/"
)

OUTPUT_FILE = Path(
    "data/404_detection_test.json"
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def main() -> int:
    response = requests.get(
        TEST_URL,
        timeout=30,
        allow_redirects=True,
        headers={
            "User-Agent": (
                "EngineerWala SEO Tracker "
                "404 Detection Test"
            )
        },
    )

    detected = response.status_code == 404

    result = {
        "tested_at": utc_now(),
        "test_url": TEST_URL,
        "final_url": response.url,
        "status_code": response.status_code,
        "404_detected": detected,
        "result": (
            "passed"
            if detected
            else "failed"
        ),
    }

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            result,
            handle,
            ensure_ascii=False,
            indent=2,
        )

    print(
        json.dumps(
            result,
            indent=2,
        )
    )

    if not detected:
        raise RuntimeError(
            (
                "404 detection test failed. "
                f"Expected HTTP 404 but received "
                f"HTTP {response.status_code}."
            )
        )

    print(
        "404 detection test passed."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
