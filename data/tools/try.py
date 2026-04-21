#!/usr/bin/env python3
"""Scrape knowledge points from kamacoder notes categories.

This script crawls the first five content sections of https://notes.kamacoder.com/base/:
- 计算机基础
- C++ 面试题
- Java 面试题
- Go 面试题
- 真实面经

It follows internal category links, fetches each page, and stores the discovered
knowledge points, titles, and URLs in a JSON file.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from tqdm import tqdm

BASE_URL = "https://notes.kamacoder.com"
CATEGORIES = [
    ("base", "计算机基础", "/base/"),
    ("cpp", "C++面试题", "/cpp/"),
    ("java", "Java面试题", "/java/"),
    ("go", "Go面试题", "/go/"),
    ("llm", "大模型", "/llm/"),
    ("interview", "真实面经", "/interview/"),
]
DEFAULT_OUTPUT = Path("data/bagu.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def build_session() -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=3)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)
    return session


def fetch_html(session: requests.Session, url: str, timeout: int = 20) -> str:
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        return response.text
    except RequestException as exc:
        raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc


def normalize_url(url: str, base: str) -> str:
    normalized = urldefrag(urljoin(base, url))[0]
    if normalized.endswith("index.html"):
        normalized = normalized[: -len("index.html")]
    return normalized


def is_internal_category_url(url: str, category_path: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc and parsed.netloc != urlparse(BASE_URL).netloc:
        return False
    return parsed.path.startswith(category_path)


def extract_links(html: str, base_url: str, category_path: str) -> Set[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: Set[str] = set()
    for a in soup.select("a[href]"):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
            continue
        full_url = normalize_url(href, base_url)
        if is_internal_category_url(full_url, category_path):
            links.add(full_url)
    return links


def extract_title_headings_and_content(html: str) -> Tuple[str, List[str], str]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        title = h1.get_text(strip=True)
    headings: List[str] = []
    for tag in soup.select("h1, h2, h3, h4"):
        text = tag.get_text(separator=" ", strip=True)
        if text and text not in headings:
            headings.append(text)

    content_container = (
        soup.select_one(".theme-default-content.content__default")
        or soup.select_one(".theme-default-content")
        or soup.find("main")
        or soup
    )
    content = content_container.get_text(separator="\n", strip=True)
    return title, headings, content


def discover_category_pages(
    session: requests.Session,
    category_url: str,
    category_path: str,
) -> Tuple[Set[str], Dict[str, str]]:
    discovered: Set[str] = set()
    queue: List[str] = [category_url]
    html_by_url: Dict[str, str] = {}

    while queue:
        page_url = queue.pop(0)
        if page_url in discovered:
            continue
        try:
            html = fetch_html(session, page_url)
            html_by_url[page_url] = html
            links = extract_links(html, page_url, category_path)
            for link in sorted(links):
                if link not in discovered and link not in queue:
                    queue.append(link)
        except Exception:
            # Keep the URL for later retry/failure reporting.
            html_by_url[page_url] = ""
        discovered.add(page_url)

    return discovered, html_by_url


def scrape_category(
    session: requests.Session,
    slug: str,
    name: str,
    category_path: str,
    max_workers: int,
) -> Dict:
    category_url = f"{BASE_URL}{category_path}"
    page_urls, html_by_url = discover_category_pages(session, category_url, category_path)

    pages: List[Dict] = []
    missing_urls = [url for url in sorted(page_urls) if not html_by_url.get(url)]
    if missing_urls:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(fetch_html, session, page_url): page_url
                for page_url in missing_urls
            }
            for future in tqdm(
                concurrent.futures.as_completed(future_to_url),
                total=len(future_to_url),
                desc=f"[{slug}] retry pages",
                unit="page",
            ):
                page_url = future_to_url[future]
                try:
                    page_html = future.result()
                    html_by_url[page_url] = page_html
                except Exception:
                    html_by_url[page_url] = ""

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(extract_title_headings_and_content, html_by_url[page_url]): page_url
            for page_url in sorted(page_urls)
            if html_by_url.get(page_url)
        }
        for future in tqdm(
            concurrent.futures.as_completed(future_to_url),
            total=len(future_to_url),
            desc=f"[{slug}] pages",
            unit="page",
        ):
            page_url = future_to_url[future]
            try:
                title, headings, content = future.result()
                pages.append(
                    {
                        "url": page_url,
                        "title": title,
                        "headings": headings,
                        "content": content,
                    }
                )
            except Exception as exc:
                pages.append(
                    {
                        "url": page_url,
                        "title": "",
                        "headings": [],
                        "content": "",
                        "error": str(exc),
                    }
                )

    for failed_url in sorted(page_urls):
        if not html_by_url.get(failed_url):
            pages.append(
                {
                    "url": failed_url,
                    "title": "",
                    "headings": [],
                    "content": "",
                    "error": "fetch failed",
                }
            )

    return {
        "slug": slug,
        "name": name,
        "url": category_url,
        "page_count": len(page_urls),
        "pages": sorted(pages, key=lambda item: item["url"]),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape knowledge points from kamacoder notes.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSON output path.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="Number of worker threads to fetch pages concurrently.",
    )
    parser.add_argument(
        "--categories",
        type=str,
        default=",".join(cat[0] for cat in CATEGORIES),
        help="Comma-separated category slugs to scrape (base,cpp,java,go,interview).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected = {slug for slug in args.categories.split(",") if slug.strip()}
    categories = [cat for cat in CATEGORIES if cat[0] in selected]
    if not categories:
        print("No valid categories selected.")
        return 1

    session = build_session()
    output = {
        "source": BASE_URL,
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "selected_categories": [cat[0] for cat in categories],
        "categories": [],
    }

    for slug, name, path in categories:
        print(f"Scraping category: {name} ({path})")
        category_data = scrape_category(session, slug, name, path, args.max_workers)
        output["categories"].append(category_data)
        print(f"  → {category_data['page_count']} pages discovered")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved scraped knowledge points to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
