from urllib.parse import urlparse


SEVERITY_POINTS = {
    "Critical": 25,
    "High": 15,
    "Medium": 8,
    "Low": 3
}

SEVERITY_RANK = {
    "Critical": 4,
    "High": 3,
    "Medium": 2,
    "Low": 1,
    "None": 0
}


def safe_int(value, default=0):
    """
    CSV ya JSON value ko safely integer mein convert karta hai.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_bool(value):
    """
    Different true/false formats ko Python boolean mein convert karta hai.
    """
    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {
        "true",
        "1",
        "yes"
    }


def normalize_comparison_url(url):
    """
    URL comparison ke liye scheme, domain aur path normalize karta hai.
    """
    if not url:
        return ""

    parsed_url = urlparse(
        str(url).strip()
    )

    domain = parsed_url.netloc.lower().replace(
        "www.",
        ""
    )

    path = parsed_url.path.rstrip("/")

    if not path:
        path = "/"

    return f"{domain}{path}"


def add_issue(
    issues,
    severity,
    issue_name,
    explanation,
    action
):
    """
    Issues list mein structured SEO issue add karta hai.
    """
    issues.append({
        "severity": severity,
        "issue": issue_name,
        "explanation": explanation,
        "action": action
    })


def analyse_status_code(page, issues):
    """
    HTTP status aur redirect related issues check karta hai.
    """
    status_code = safe_int(
        page.get("status_code")
    )

    original_url = str(
        page.get("url", "")
    ).strip()

    final_url = str(
        page.get("final_url", "")
    ).strip()

    crawl_error = str(
        page.get("crawl_error", "")
    ).strip()

    if crawl_error:
        add_issue(
            issues,
            "Critical",
            "Crawl failed",
            f"Crawler page ko successfully open nahi kar saka: "
            f"{crawl_error}",
            "Hosting, firewall, timeout ya blocked crawler issue "
            "check karo. Page ko browser mein manually open karke "
            "confirm karo."
        )
        return

    if status_code >= 500:
        add_issue(
            issues,
            "Critical",
            f"Server error {status_code}",
            "Page server-side error return kar raha hai.",
            "Hosting error logs check karo aur page ko HTTP 200 "
            "status par restore karo."
        )

    elif status_code >= 400:
        add_issue(
            issues,
            "Critical",
            f"Broken page {status_code}",
            "Page visitors aur search engines ke liye accessible "
            "nahi hai.",
            "Page restore karo ya is URL ko sab se relevant live "
            "page par 301 redirect karo. Sitemap aur internal links "
            "bhi update karo."
        )

    elif 300 <= status_code < 400:
        add_issue(
            issues,
            "High",
            f"Redirect status {status_code}",
            "URL direct HTTP 200 page ki jagah redirect return "
            "kar raha hai.",
            "Sitemap aur internal links mein redirected URL ki jagah "
            "final destination URL use karo."
        )

    elif status_code and status_code != 200:
        add_issue(
            issues,
            "Medium",
            f"Unexpected status {status_code}",
            "Page standard HTTP 200 status return nahi kar raha.",
            "Page response manually verify karo aur live SEO pages ko "
            "HTTP 200 status par rakho."
        )

    if (
        original_url
        and final_url
        and normalize_comparison_url(original_url)
        != normalize_comparison_url(final_url)
    ):
        add_issue(
            issues,
            "Medium",
            "URL redirects to another page",
            f"Requested URL ka final destination {final_url} hai.",
            f"Website ke internal links aur sitemap mein direct "
            f"{final_url} use karo."
        )


def analyse_title(page, issues):
    """
    SEO title presence aur length evaluate karta hai.
    """
    title = str(
        page.get("title", "")
    ).strip()

    title_length = len(title)

    if not title:
        add_issue(
            issues,
            "Critical",
            "Missing page title",
            "Page ke HTML mein title tag missing hai.",
            "Page ke liye unique SEO title add karo. Main keyword ko "
            "naturally include karo aur title ko roughly 30–60 "
            "characters mein rakho."
        )
        return

    if title_length < 30:
        add_issue(
            issues,
            "Medium",
            "SEO title too short",
            f"Current title sirf {title_length} characters ka hai.",
            "Title ko zyada descriptive banao, main search intent aur "
            "primary keyword add karo. Target roughly 30–60 characters."
        )

    elif title_length > 60:
        add_issue(
            issues,
            "Medium",
            "SEO title too long",
            f"Current title {title_length} characters ka hai aur SERP "
            "mein cut ho sakta hai.",
            "Important keyword aur benefit start mein rakh kar title ko "
            "roughly 60 characters ke andar rewrite karo."
        )


def analyse_meta_description(page, issues):
    """
    Meta description presence aur length evaluate karta hai.
    """
    description = str(
        page.get("meta_description", "")
    ).strip()

    description_length = len(description)

    if not description:
        add_issue(
            issues,
            "High",
            "Missing meta description",
            "Page par meta description available nahi hai.",
            "Page ke search intent ko summarize karne wali unique meta "
            "description add karo. Primary keyword aur clear benefit "
            "include karo."
        )
        return

    if description_length < 70:
        add_issue(
            issues,
            "Medium",
            "Meta description too short",
            f"Meta description sirf {description_length} characters ki hai.",
            "Description ko zyada informative banao aur approximately "
            "120–155 characters tak expand karo."
        )

    elif description_length > 160:
        add_issue(
            issues,
            "Medium",
            "Meta description too long",
            f"Meta description {description_length} characters ki hai.",
            "Description ko concise rewrite karo. Important information "
            "aur CTA ko approximately 120–155 characters mein rakho."
        )


def analyse_headings(page, issues):
    """
    H1 aur H2 heading structure evaluate karta hai.
    """
    h1_count = safe_int(
        page.get("h1_count")
    )

    h2_count = safe_int(
        page.get("h2_count")
    )

    if h1_count == 0:
        add_issue(
            issues,
            "High",
            "Missing H1 heading",
            "Page par koi H1 heading detect nahi hui.",
            "Page ke main topic ko describe karne wali aik clear H1 "
            "heading add karo."
        )

    elif h1_count > 1:
        add_issue(
            issues,
            "Medium",
            "Multiple H1 headings",
            f"Page par {h1_count} H1 headings detect hui hain.",
            "Primary page heading ko aik H1 rakho. Baqi section headings "
            "ko H2 ya H3 mein convert karo."
        )

    if h2_count == 0:
        add_issue(
            issues,
            "Low",
            "No H2 headings",
            "Page par content sections ke liye H2 headings nahi milin.",
            "Long content ko logical H2 sections mein divide karo taa-ke "
            "readability aur topic coverage improve ho."
        )


def analyse_canonical(page, issues):
    """
    Canonical URL presence aur correctness evaluate karta hai.
    """
    page_url = str(
        page.get("url", "")
    ).strip()

    canonical_url = str(
        page.get("canonical_url", "")
    ).strip()

    if not canonical_url:
        add_issue(
            issues,
            "High",
            "Missing canonical URL",
            "Page par canonical tag detect nahi hua.",
            f"Self-referencing canonical add karo jo {page_url} ko point "
            "kare."
        )
        return

    if (
        normalize_comparison_url(page_url)
        != normalize_comparison_url(canonical_url)
    ):
        add_issue(
            issues,
            "High",
            "Canonical points to another URL",
            f"Page ka canonical {canonical_url} ko point kar raha hai.",
            "Confirm karo ke canonical intentionally doosre page ko point "
            "karna chahiye. Agar ye unique page hai to self-referencing "
            "canonical use karo."
        )


def analyse_indexing(page, issues):
    """
    Noindex status evaluate karta hai.
    """
    is_noindex = safe_bool(
        page.get("is_noindex")
    )

    if is_noindex:
        add_issue(
            issues,
            "Critical",
            "Page is set to noindex",
            "Robots directive search engines ko page index karne se "
            "rok rahi hai.",
            "Agar page Google mein rank karna chahiye to Rank Math ya "
            "page settings mein noindex remove karke index enable karo."
        )


def analyse_content(page, issues):
    """
    Basic content depth aur word count evaluate karta hai.
    """
    word_count = safe_int(
        page.get("word_count")
    )

    if word_count < 300:
        add_issue(
            issues,
            "High",
            "Very thin content",
            f"Page par approximately {word_count} visible words detect "
            "huay hain.",
            "Search intent ke mutabiq useful explanation, steps, examples "
            "aur FAQs add karo. Important article pages ko substantially "
            "expand karo."
        )

    elif word_count < 600:
        add_issue(
            issues,
            "Medium",
            "Limited content depth",
            f"Page par approximately {word_count} visible words hain.",
            "Competitor coverage aur user questions review karke missing "
            "sections, examples aur practical guidance add karo."
        )


def analyse_links(page, issues):
    """
    Internal aur external link counts evaluate karta hai.
    """
    internal_links = safe_int(
        page.get("internal_links_count")
    )

    external_links = safe_int(
        page.get("external_links_count")
    )

    if internal_links == 0:
        add_issue(
            issues,
            "High",
            "No internal links",
            "Page par koi crawlable internal link detect nahi hua.",
            "Article ke relevant paragraphs mein kam az kam 2–4 related "
            "EngineerWala pages ke contextual internal links add karo."
        )

    elif internal_links < 3:
        add_issue(
            issues,
            "Medium",
            "Very few internal links",
            f"Page par sirf {internal_links} unique internal links mile.",
            "Relevant supporting articles aur category pages ke natural "
            "contextual links add karo."
        )

    if external_links == 0:
        add_issue(
            issues,
            "Low",
            "No external references",
            "Page par koi external reference detect nahi hua.",
            "Technical ya factual claims ke liye zarurat par authoritative "
            "source ka relevant link add karo."
        )


def analyse_images(page, issues):
    """
    Image alt text issues evaluate karta hai.
    """
    image_count = safe_int(
        page.get("image_count")
    )

    missing_alt_count = safe_int(
        page.get("missing_alt_count")
    )

    if missing_alt_count > 0:
        add_issue(
            issues,
            "Medium",
            "Images missing alt text",
            f"{image_count} images mein se {missing_alt_count} images ka "
            "alt text missing ya blank hai.",
            f"In {missing_alt_count} images ke liye short, descriptive aur "
            "context-relevant alt text add karo. Keyword stuffing mat karo."
        )


def calculate_seo_score(issues):
    """
    Issue severity ke mutabiq 0–100 SEO score calculate karta hai.
    """
    total_deduction = 0

    for issue in issues:
        severity = issue.get(
            "severity",
            "Low"
        )

        total_deduction += SEVERITY_POINTS.get(
            severity,
            0
        )

    return max(
        0,
        100 - total_deduction
    )


def get_highest_priority(issues):
    """
    Page ki sab se high issue priority return karta hai.
    """
    if not issues:
        return "None"

    return max(
        (
            issue.get("severity", "Low")
            for issue in issues
        ),
        key=lambda severity: SEVERITY_RANK.get(
            severity,
            0
        )
    )


def analyse_page(page):
    """
    Aik crawled page par tamam basic SEO rules run karta hai.
    """
    issues = []

    analyse_status_code(
        page,
        issues
    )

    analyse_title(
        page,
        issues
    )

    analyse_meta_description(
        page,
        issues
    )

    analyse_headings(
        page,
        issues
    )

    analyse_canonical(
        page,
        issues
    )

    analyse_indexing(
        page,
        issues
    )

    analyse_content(
        page,
        issues
    )

    analyse_links(
        page,
        issues
    )

    analyse_images(
        page,
        issues
    )

    seo_score = calculate_seo_score(
        issues
    )

    highest_priority = get_highest_priority(
        issues
    )

    exact_actions = " | ".join(
        issue["action"]
        for issue in issues
    )

    return {
        "seo_score": seo_score,
        "priority": highest_priority,
        "issue_count": len(issues),
        "exact_actions": exact_actions,
        "issues": issues
    }
