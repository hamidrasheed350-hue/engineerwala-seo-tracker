import csv
import json
import os
import xml.etree.ElementTree as ET
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


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


def normalize_domain(domain):
    """Domain se www remove karke lowercase return karta hai."""
    return domain.lower().replace("www.", "")


def normalize_url(url):
    """URL se fragment remove karke clean URL return karta hai."""
    clean_url, _ = urldefrag(url.strip())

    if clean_url.endswith("/") and clean_url != BASE_URL + "/":
        return clean_url.rstrip("/") + "/"

    return clean_url


def is_internal_url(url):
    """Sirf EngineerWala domain ki valid URLs allow karta hai."""
    parsed_url = urlparse(url)

    base_domain = normalize_domain(
        urlparse(BASE_URL).netloc
    )

    current_domain = normalize_domain(
        parsed_url.netloc
    )

    if current_domain != base_domain:
        return False

    if "/wp-content/uploads/" in parsed_url.path:
        return False

    return parsed_url.scheme in {
        "http",
        "https"
    }


def get_wordpress_urls(api_url, source_name):
    """
    WordPress API se tamam published URLs collect karta hai.
    Pagination handle hoti hai.
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
                        (
                            normalize_url(url),
                            source_name
                        )
                    )

            total_pages = int(
                response.headers.get(
                    "X-WP-TotalPages",
                    1
                )
            )

            print(
                f"{source_name}: "
                f"page {page_number} of "
                f"{total_pages} fetched"
            )

            if page_number >= total_pages:
                break

            page_number += 1

        except requests.RequestException as error:
            print(
                f"{source_name} API error: "
                f"{error}"
            )
            break

        except ValueError as error:
            print(
                f"{source_name} JSON error: "
                f"{error}"
            )
            break

    return collected_urls


def read_sitemap(sitemap_url, visited=None):
    """
    Sitemap index aur child sitemaps se URLs collect karta hai.
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

        root = ET.fromstring(
            response.content
        )

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
                                normalize_url(
                                    child.text
                                ),
                                "Sitemap"
                            )
                        )

        print(
            f"Sitemap checked: "
            f"{sitemap_url}"
        )

    except requests.RequestException as error:
        print(
            f"Sitemap request error: "
            f"{error}"
        )

    except ET.ParseError as error:
        print(
            f"Sitemap XML error: "
            f"{error}"
        )

    return collected_urls


def remove_duplicates(url_records):
    """
    Duplicate URLs remove karta hai.
    WordPress source ko Sitemap source par priority deta hai.
    """
    unique_urls = {}

    for url, source in url_records:
        if not is_internal_url(url):
            continue

        if url not in unique_urls:
            unique_urls[url] = source

        elif unique_urls[url] == "Sitemap":
            unique_urls[url] = source

    return sorted(
        unique_urls.items()
    )


def save_urls(url_records):
    """Final URLs ko data/urls.csv mein save karta hai."""
    os.makedirs(
        OUTPUT_DIRECTORY,
        exist_ok=True
    )

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


def extract_page_title(soup):
    """HTML se page title extract karta hai."""
    if not soup.title:
        return ""

    return soup.title.get_text(
        " ",
        strip=True
    )


def extract_meta_description(soup):
    """HTML se meta description extract karta hai."""
    meta_tag = soup.find(
        "meta",
        attrs={
            "name": lambda value: (
                value
                and str(value).lower() == "description"
            )
        }
    )

    if not meta_tag:
        return ""

    content = meta_tag.get(
        "content",
        ""
    )

    return content.strip()


def canonical_rel_match(value):
    """Canonical rel attribute identify karta hai."""
    if not value:
        return False

    if isinstance(value, list):
        return any(
            str(item).lower() == "canonical"
            for item in value
        )

    return "canonical" in str(
        value
    ).lower().split()


def extract_canonical_url(soup, page_url):
    """HTML se canonical URL extract karta hai."""
    canonical_tag = soup.find(
        "link",
        rel=canonical_rel_match
    )

    if not canonical_tag:
        return ""

    canonical_href = canonical_tag.get(
        "href",
        ""
    ).strip()

    if not canonical_href:
        return ""

    return urljoin(
        page_url,
        canonical_href
    )


def extract_robots_directives(soup):
    """
    Robots aur Googlebot meta directives extract karta hai.
    """
    directives = []

    for meta_tag in soup.find_all("meta"):
        meta_name = meta_tag.get(
            "name",
            ""
        ).strip().lower()

        if meta_name not in {
            "robots",
            "googlebot"
        }:
            continue

        content = meta_tag.get(
            "content",
            ""
        ).strip()

        if content:
            directives.append(
                f"{meta_name}: {content}"
            )

    return " | ".join(
        directives
    )


def detect_noindex(
    robots_directives,
    x_robots_tag
):
    """
    Meta robots aur X-Robots-Tag se noindex detect karta hai.
    """
    combined_directives = (
        f"{robots_directives} "
        f"{x_robots_tag}"
    ).lower()

    return "noindex" in combined_directives


def count_headings(soup):
    """Page ke H1 aur H2 headings count karta hai."""
    h1_count = len(
        soup.find_all("h1")
    )

    h2_count = len(
        soup.find_all("h2")
    )

    return h1_count, h2_count


def calculate_word_count(soup):
    """
    Scripts aur styling remove karke visible page text
    ka basic word count calculate karta hai.
    """
    clean_soup = BeautifulSoup(
        str(soup),
        "html.parser"
    )

    unwanted_tags = clean_soup.find_all([
        "script",
        "style",
        "noscript",
        "template",
        "svg"
    ])

    for tag in unwanted_tags:
        tag.decompose()

    visible_text = clean_soup.get_text(
        " ",
        strip=True
    )

    if not visible_text:
        return 0

    words = visible_text.split()

    return len(words)


def count_page_links(soup, page_url):
    """
    Page ke unique internal aur external links count karta hai.
    """
    internal_links = set()
    external_links = set()

    website_domain = normalize_domain(
        urlparse(BASE_URL).netloc
    )

    ignored_prefixes = (
        "#",
        "mailto:",
        "tel:",
        "javascript:",
        "data:"
    )

    for link_tag in soup.find_all(
        "a",
        href=True
    ):
        href = link_tag.get(
            "href",
            ""
        ).strip()

        if not href:
            continue

        if href.lower().startswith(
            ignored_prefixes
        ):
            continue

        complete_url = urljoin(
            page_url,
            href
        )

        clean_url, _ = urldefrag(
            complete_url
        )

        parsed_link = urlparse(
            clean_url
        )

        if parsed_link.scheme not in {
            "http",
            "https"
        }:
            continue

        link_domain = normalize_domain(
            parsed_link.netloc
        )

        if link_domain == website_domain:
            internal_links.add(
                clean_url
            )
        else:
            external_links.add(
                clean_url
            )

    return (
        len(internal_links),
        len(external_links)
    )


def count_images_and_missing_alt(soup):
    """
    Page ki total images aur missing/blank alt text count karta hai.
    """
    image_tags = soup.find_all("img")
    missing_alt_count = 0

    for image_tag in image_tags:
        if not image_tag.has_attr("alt"):
            missing_alt_count += 1
            continue

        alt_text = str(
            image_tag.get(
                "alt",
                ""
            )
        ).strip()

        if not alt_text:
            missing_alt_count += 1

    return (
        len(image_tags),
        missing_alt_count
    )


def crawl_page(url):
    """
    Ek URL crawl karke page information return karta hai.
    Ek page fail hone par poora crawler stop nahi hota.
    """
    result = {
        "url": url,
        "status_code": "",
        "final_url": url,
        "title": "",
        "meta_description": "",
        "canonical_url": "",
        "robots_directives": "",
        "x_robots_tag": "",
        "is_noindex": False,
        "h1_count": 0,
        "h2_count": 0,
        "word_count": 0,
        "internal_links_count": 0,
        "external_links_count": 0,
        "image_count": 0,
        "missing_alt_count": 0,
        "crawl_error": ""
    }

    try:
        response = SESSION.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=True
        )

        result["status_code"] = (
            response.status_code
        )

        result["final_url"] = (
            response.url
        )

        result["x_robots_tag"] = (
            response.headers.get(
                "X-Robots-Tag",
                ""
            ).strip()
        )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        result["title"] = (
            extract_page_title(soup)
        )

        result["meta_description"] = (
            extract_meta_description(soup)
        )

        result["canonical_url"] = (
            extract_canonical_url(
                soup,
                response.url
            )
        )

        result["robots_directives"] = (
            extract_robots_directives(
                soup
            )
        )

        result["is_noindex"] = detect_noindex(
            result["robots_directives"],
            result["x_robots_tag"]
        )

        h1_count, h2_count = count_headings(
            soup
        )

        result["h1_count"] = h1_count
        result["h2_count"] = h2_count

        result["word_count"] = (
            calculate_word_count(soup)
        )

        (
            internal_links_count,
            external_links_count
        ) = count_page_links(
            soup,
            response.url
        )

        result["internal_links_count"] = (
            internal_links_count
        )

        result["external_links_count"] = (
            external_links_count
        )

        (
            image_count,
            missing_alt_count
        ) = count_images_and_missing_alt(
            soup
        )

        result["image_count"] = (
            image_count
        )

        result["missing_alt_count"] = (
            missing_alt_count
        )

        print(
            f"Crawled: {url} | "
            f"Status: {response.status_code} | "
            f"Noindex: {result['is_noindex']} | "
            f"H1: {h1_count} | "
            f"H2: {h2_count} | "
            f"Words: {result['word_count']} | "
            f"Internal links: {internal_links_count} | "
            f"External links: {external_links_count} | "
            f"Images: {image_count} | "
            f"Missing alt: {missing_alt_count} | "
            f"Title: {result['title']}"
        )

    except requests.RequestException as error:
        result["crawl_error"] = str(
            error
        )

        print(
            f"Crawl failed: {url} | "
            f"Error: {error}"
        )

    except Exception as error:
        result["crawl_error"] = (
            f"HTML processing error: {error}"
        )

        print(
            f"HTML processing failed: "
            f"{url} | Error: {error}"
        )

    return result


def crawl_all_urls(url_records):
    """Saari URLs ko aik aik karke crawl karta hai."""
    crawl_results = []

    for url, source in url_records:
        page_result = crawl_page(
            url
        )

        page_result["source"] = source

        crawl_results.append(
            page_result
        )

    return crawl_results


def save_basic_crawl(crawl_results):
    """
    Crawl report ko data/basic_crawl.csv mein save karta hai.
    """
    os.makedirs(
        OUTPUT_DIRECTORY,
        exist_ok=True
    )

    output_file = os.path.join(
        OUTPUT_DIRECTORY,
        "basic_crawl.csv"
    )

    fieldnames = [
        "url",
        "source",
        "status_code",
        "final_url",
        "title",
        "meta_description",
        "canonical_url",
        "robots_directives",
        "x_robots_tag",
        "is_noindex",
        "h1_count",
        "h2_count",
        "word_count",
        "internal_links_count",
        "external_links_count",
        "image_count",
        "missing_alt_count",
        "crawl_error"
    ]

    with open(
        output_file,
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
            crawl_results
        )

    print(
        f"Basic crawl report saved: "
        f"{output_file}"
    )


def main():
    """URL collection aur crawling process run karta hai."""
    print(
        "EngineerWala URL collection "
        "started..."
    )

    all_urls = []

    post_urls = get_wordpress_urls(
        POSTS_API,
        "WordPress Post"
    )

    all_urls.extend(
        post_urls
    )

    page_urls = get_wordpress_urls(
        PAGES_API,
        "WordPress Page"
    )

    all_urls.extend(
        page_urls
    )

    sitemap_urls = read_sitemap(
        SITEMAP_URL
    )

    all_urls.extend(
        sitemap_urls
    )

    unique_urls = remove_duplicates(
        all_urls
    )

    save_urls(
        unique_urls
    )

    crawl_results = crawl_all_urls(
        unique_urls
    )

    save_basic_crawl(
        crawl_results
    )


if __name__ == "__main__":
    main()
