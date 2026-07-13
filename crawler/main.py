import csv
import json
import os
import xml.etree.ElementTree as ET
from urllib.parse import urldefrag, urlparse

import requests


CONFIG_FILE = "config.json"


def load_config():
    """config.json se website settings read karta hai."""
    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


CONFIG = load_config()

BASE_URL = CONFIG["base_url"].rstrip("/")
POSTS_API = CONFIG["posts_api"]
PAGES_API = CONFIG["pages_api"]
SITEMAP_URL = CONFIG["sitemap_url"]
TIMEOUT = CONFIG.get("request_timeout", 30)
OUTPUT_DIRECTORY = CONFIG.get("output_directory", "data")

HEADERS = {
    "User-Agent": CONFIG.get(
        "user_agent",
        "EngineerWala-SEO-Tracker/1.0"
    )
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def normalize_url(url):
    """URL se fragment remove karke clean URL return karta hai."""
    clean_url, _ = urldefrag(url.strip())

    if clean_url.endswith("/") and clean_url != BASE_URL + "/":
        return clean_url.rstrip("/") + "/"

    return clean_url


def is_internal_url(url):
    """Sirf EngineerWala domain ki URLs allow karta hai."""
    parsed_url = urlparse(url)
    base_domain = urlparse(BASE_URL).netloc.replace("www.", "")
    current_domain = parsed_url.netloc.replace("www.", "")

    if current_domain != base_domain:
        return False

    if "/wp-content/uploads/" in parsed_url.path:
        return False

    return parsed_url.scheme in {"http", "https"}


def get_wordpress_urls(api_url, source_name):
    """
    WordPress REST API se tamam URLs collect karta hai.
    Pagination ki wajah se sirf pehli 10 posts tak limited nahi rahega.
    """
    collected_urls = []
    page_number = 1

    while True:
        params = {
            "per_page": 100,
            "page": page_number,
            "status": "publish",
            "_fields": "link"
        }

        try:
            response = SESSION.get(
                api_url,
                params=params,
                timeout=TIMEOUT
            )

            if response.status_code == 400:
                break

            response.raise_for_status()
            items = response.json()

            if not items:
                break

            for item in items:
                url = item.get("link")

                if url:
                    collected_urls.append(
                        (normalize_url(url), source_name)
                    )

            total_pages = int(
                response.headers.get("X-WP-TotalPages", 1)
            )

            print(
                f"{source_name}: page {page_number} "
                f"of {total_pages} fetched"
            )

            if page_number >= total_pages:
                break

            page_number += 1

        except requests.RequestException as error:
            print(f"{source_name} API error: {error}")
            break

        except ValueError as error:
            print(f"{source_name} JSON error: {error}")
            break

    return collected_urls


def read_sitemap(sitemap_url, visited=None):
    """
    Sitemap index aur uske child sitemaps se URLs collect karta hai.
    """
    if visited is None:
        visited = set()

    sitemap_url = normalize_url(sitemap_url)

    if sitemap_url in visited:
        return []

    visited.add(sitemap_url)
    collected_urls = []

    try:
        response = SESSION.get(
            sitemap_url,
            timeout=TIMEOUT
        )
        response.raise_for_status()

        root = ET.fromstring(response.content)

        root_name = root.tag.split("}")[-1]

        if root_name == "sitemapindex":
            for element in root:
                for child in element:
                    tag_name = child.tag.split("}")[-1]

                    if tag_name == "loc" and child.text:
                        child_sitemap = child.text.strip()

                        collected_urls.extend(
                            read_sitemap(
                                child_sitemap,
                                visited
                            )
                        )

        elif root_name == "urlset":
            for element in root:
                for child in element:
                    tag_name = child.tag.split("}")[-1]

                    if tag_name == "loc" and child.text:
                        collected_urls.append(
                            (
                                normalize_url(child.text),
                                "Sitemap"
                            )
                        )

        print(f"Sitemap checked: {sitemap_url}")

    except requests.RequestException as error:
        print(f"Sitemap request error: {error}")

    except ET.ParseError as error:
        print(f"Sitemap XML error: {error}")

    return collected_urls


def remove_duplicates(url_records):
    """
    Duplicate URLs remove karta hai.
    WordPress API source ko sitemap source par priority deta hai.
    """
    unique_urls = {}

    for url, source in url_records:
        if not is_internal_url(url):
            continue

        if url not in unique_urls:
            unique_urls[url] = source

        elif unique_urls[url] == "Sitemap":
            unique_urls[url] = source

    return sorted(unique_urls.items())


def save_urls(url_records):
    """Final URL list ko data/urls.csv mein save karta hai."""
    os.makedirs(OUTPUT_DIRECTORY, exist_ok=True)

    output_file = os.path.join(
        OUTPUT_DIRECTORY,
        "urls.csv"
    )

    with open(
        output_file,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.writer(file)

        writer.writerow([
            "url",
            "source"
        ])

        for url, source in url_records:
            writer.writerow([
                url,
                source
            ])

    print("--------------------------------")
    print(f"Total unique URLs: {len(url_records)}")
    print(f"Saved file: {output_file}")


def main():
    print("EngineerWala URL collection started...")

    all_urls = []

    post_urls = get_wordpress_urls(
        POSTS_API,
        "WordPress Post"
    )
    all_urls.extend(post_urls)

    page_urls = get_wordpress_urls(
        PAGES_API,
        "WordPress Page"
    )
    all_urls.extend(page_urls)

    sitemap_urls = read_sitemap(SITEMAP_URL)
    all_urls.extend(sitemap_urls)

    unique_urls = remove_duplicates(all_urls)

    save_urls(unique_urls)


if __name__ == "__main__":
    main()
