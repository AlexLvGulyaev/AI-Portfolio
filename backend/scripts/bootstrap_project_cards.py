"""
Bootstrap ProjectCard records from src/portfolio.html.

Usage:
    cd backend
    python scripts/bootstrap_project_cards.py

This is a one-time helper used to generate the data migration for the initial
switch from static HTML to PostgreSQL as the single Source of Truth for project
cards. After the generated migration is applied, project_cards is maintained
exclusively through the admin console.
"""

import json
import os
import re
import sys


def project_root():
    """Return project root assuming script is at backend/scripts/."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_portfolio_html(path: str) -> list[dict]:
    """Parse case cards from the public portfolio HTML."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Portfolio HTML not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    articles = re.findall(r'<article class="case-card">(.*?)</article>', html, re.DOTALL)
    cards = []
    for order, article in enumerate(articles, start=1):
        title_match = re.search(
            r'<h3 class="case-card__title">\s*<a href="([^"]+)">([^<]+)</a>',
            article,
        )
        excerpt_match = re.search(
            r'<p class="case-card__excerpt">\s*(.*?)\s*</p>',
            article,
            re.DOTALL,
        )
        tags = re.findall(r'<span class="tag">([^<]+)</span>', article)

        if not title_match:
            continue

        external_url = title_match.group(1)
        title = title_match.group(2).strip()
        slug = (
            external_url.split("/")[-1].replace(".html", "")
            if ".html" in external_url
            else re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-")
        )
        short_description = (
            excerpt_match.group(1).replace("\n", " ").strip()
            if excerpt_match
            else ""
        )

        cards.append({
            "slug": slug,
            "title": title,
            "short_description": short_description,
            "category": "cases",
            "tags": tags,
            "display_order": order,
            "external_url": "/" + external_url,
        })

    return cards


def print_cards(cards: list[dict]) -> None:
    """Print cards as a Python list literal suitable for migration."""
    print("PROJECT_CARDS = [")
    for card in cards:
        print("    {")
        print(f"        'slug': {card['slug']!r},")
        print(f"        'title': {card['title']!r},")
        print(f"        'short_description': {card['short_description']!r},")
        print(f"        'category': {card['category']!r},")
        print(f"        'tags': {card['tags']!r},")
        print(f"        'display_order': {card['display_order']},")
        print(f"        'external_url': {card['external_url']!r},")
        print("    },")
    print("]")


def main():
    root = project_root()
    portfolio_path = os.path.join(root, "src", "portfolio.html")
    cards = parse_portfolio_html(portfolio_path)

    if not cards:
        print("No cards found in portfolio.html", file=sys.stderr)
        sys.exit(1)

    print(f"# Parsed {len(cards)} project cards from {portfolio_path}", file=sys.stderr)
    print_cards(cards)


if __name__ == "__main__":
    main()
