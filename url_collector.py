import csv
import os
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests


BASE_URL = "https://engineerwala.com"
SITEMAP_URL = f"{BASE_URL}/sitemap_index.xml"

HEADERS = {
    "User-Agent": "EngineerWala-SEO-Tracker/1.0"
}


def get_wordpress_urls(content_type):
    """
    WordPress REST API se posts ya pages ki URLs collect karta hai.
    """

    urls = []
    page_number = 1

    while True:
        api_url = f"{BASE_URL}/wp-json/wp/v2/{content_type}"

        params = {
            "per_page": 100,
            "page": page_number,
            "status": "publish",
            "_fields": "link"
        }

        try:
            response = requests.get(
                api_url,
                params=params,
                headers=HEADERS,
                timeout=30
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
                    urls.append(url.strip())

            total_pages = int(
                response.headers.get("X-WP-TotalPages", 1)
            )

            if page_number >= total_pages:
                break

            page_number += 1

        except requests.RequestException as error:
            print(
                f"WordPress {content_type} fetch error: {error}"
            )
            break

    return urls


def read_sitemap(sitemap_url, visited_sitemaps=None):
    """
    Sitemap index aur child sitemaps se URLs collect karta hai.
    """

    if visited_sitemaps is None:
        visited_sitemaps = set()

    if sitemap_url in visited_sitemaps:
        return []

    visited_sitemaps.add(sitemap_url)

    collected_urls = []

    try:
        response = requests.get(
            sitemap_url,
            headers=HEADERS,
            timeout=30
        )
        response.raise_for_status()

        root = ET.fromstring(response.content)

        sitemap_locations = []
        page_locations = []

        for element in root.iter():
            tag_name = element.tag.split("}")[-1]

            if tag_name == "sitemap":
                for child in element:
                    child_tag = child.tag.split("}")[-1]

                    if child_tag == "loc" and child.text:
                        sitemap_locations.append(child.text.strip())

            elif tag_name == "url":
                for child in element:
                    child_tag = child.tag.split("}")[-1]

                    if child_tag == "loc" and child.text:
                        page_locations.append(child.text.strip())

        collected_urls.extend(page_locations)

        for child_sitemap in sitemap_locations:
            child_urls = read_sitemap(
                child_sitemap,
                visited_sitemaps
            )
            collected_urls.extend(child_urls)

    except requests.RequestException as error:
        print(f"Sitemap request error: {error}")

    except ET.ParseError as error:
        print(f"Sitemap XML error: {error}")

    return collected_urls


def is_valid_website_url(url):
    """
    Sirf EngineerWala domain ki valid URLs rakhta hai.
    """

    parsed_url = urlparse(url)
    base_domain = urlparse(BASE_URL).netloc

    if parsed_url.netloc != base_domain:
        return False

    if "/wp-content/uploads/" in parsed_url.path:
        return False

    return True


def save_urls(urls):
    """
    Collected URLs ko data/urls.csv file mein save karta hai.
    """

    os.makedirs("data", exist_ok=True)

    output_file = "data/urls.csv"

    with open(
        output_file,
        "w",
        newline="",
        encoding="utf-8"
    ) as csv_file:

        writer = csv.writer(csv_file)

        writer.writerow([
            "url",
            "source"
        ])

        for url, source in urls:
            writer.writerow([
                url,
                source
            ])

    print(f"Total URLs saved: {len(urls)}")
    print(f"File created: {output_file}")


def main():
    print("EngineerWala URLs collect ho rahi hain...")

    collected = {}

    post_urls = get_wordpress_urls("posts")

    for url in post_urls:
        collected[url] = "WordPress Post"

    page_urls = get_wordpress_urls("pages")

    for url in page_urls:
        collected[url] = "WordPress Page"

    sitemap_urls = read_sitemap(SITEMAP_URL)

    for url in sitemap_urls:
        if url not in collected:
            collected[url] = "Sitemap"

    final_urls = []

    for url, source in collected.items():
        if is_valid_website_url(url):
            final_urls.append((url, source))

    final_urls.sort(key=lambda item: item[0])

    save_urls(final_urls)


if __name__ == "__main__":
    main()
