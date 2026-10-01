import os
import json
import re
from datetime import datetime
import google.generativeai as genai

# Configuration
SITE_URL = os.getenv("SITE_URL", "https://ac9575541-png.github.io/Auto-Publishing-Bot")
GEMINI_API_KEY = os.getenv("AQ.Ab8RN6J3xSOUr9fXxLtmtSyA_w27FB4mO02JUx8IjbQORBMU9g")
DOCS_DIR = "docs"
KEYWORDS_FILE = "keywords.txt"
TRACKER_FILE = "published.json"

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is missing.")

genai.configure(api_key=GEMINI_API_KEY)


def get_next_keyword():
    """Picks the first unpublished keyword from keywords.txt."""
    if not os.path.exists(KEYWORDS_FILE):
        return None

    published = set()
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE, "r", encoding="utf-8") as f:
            published = set(json.load(f))

    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip()]

    for kw in keywords:
        if kw.lower() not in published:
            return kw
    return None


def mark_keyword_published(keyword):
    """Saves the published keyword to the tracker file."""
    published = []
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE, "r", encoding="utf-8") as f:
            published = json.load(f)
    published.append(keyword.lower())
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(published, f, indent=2)


def generate_seo_article(keyword):
    """Generates structured content and metadata with Gemini Flash."""
    model = genai.GenerativeModel("gemini-1.5-flash")

    prompt = f"""
    You are an expert SEO copywriter. Write a comprehensive, factual, long-form article for the keyword: "{keyword}".
    
    Output strictly valid JSON with the following keys (no markdown code blocks, just raw JSON):
    {{
      "title": "A compelling, click-worthy SEO title under 60 characters",
      "meta_description": "An engaging meta description between 140 and 160 characters",
      "faq": [
        {{"question": "FAQ Question 1", "answer": "Detailed answer 1"}},
        {{"question": "FAQ Question 2", "answer": "Detailed answer 2"}}
      ],
      "body_html": "<p>Introduction...</p><h2>Subheading</h2><p>Content...</p>"
    }}

    Guidelines:
    - Ensure clean semantic HTML in 'body_html' with <h2>, <h3>, <p>, <ul>, <li>.
    - Avoid buzzwords, fluff, or generic AI intros. Provide practical, high-value information.
    """

    response = model.generate_content(prompt)
    clean_text = response.text.strip()
    if clean_text.startswith("```json"):
        clean_text = clean_text[7:]
    if clean_text.endswith("```"):
        clean_text = clean_text[:-3]

    return json.loads(clean_text.strip())


def render_html(data, keyword, slug):
    canonical_url = f"{SITE_URL}/{slug}.html"
    published_date = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    human_date = datetime.utcnow().strftime("%B %d, %Y")

    # Schema.org Article + FAQPage JSON-LD
    faq_schema = [
        {
            "@type": "Question",
            "name": item["question"],
            "acceptedAnswer": {"@type": "Answer", "text": item["answer"]}
        }
        for item in data.get("faq", [])
    ]

    schema_graph = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "headline": data["title"],
                "description": data["meta_description"],
                "datePublished": published_date,
                "mainEntityOfPage": canonical_url,
                "author": {"@type": "Organization", "name": "AutoBot Team"}
            },
            {
                "@type": "FAQPage",
                "mainEntity": faq_schema
            }
        ]
    }

    # FAQ HTML section
    faq_html = "".join([
        f"<div class='faq-item'><h3>{item['question']}</h3><p>{item['answer']}</p></div>"
        for item in data.get("faq", [])
    ])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{data['title']}</title>
  <meta name="description" content="{data['meta_description']}">
  <link rel="canonical" href="{canonical_url}">
  <meta name="robots" content="index, follow">
  
  <meta property="og:title" content="{data['title']}">
  <meta property="og:description" content="{data['meta_description']}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{canonical_url}">

  <script type="application/ld+json">
  {json.dumps(schema_graph, indent=2)}
  </script>

  <style>
    :root {{ --primary: #0066cc; --text: #1a1a1a; --bg: #ffffff; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.7; color: var(--text); background: var(--bg); max-width: 760px; margin: 0 auto; padding: 40px 20px; }}
    h1 {{ font-size: 2.2rem; line-height: 1.25; margin-bottom: 8px; }}
    h2 {{ font-size: 1.5rem; margin-top: 2rem; border-bottom: 1px solid #eee; padding-bottom: 8px; }}
    h3 {{ font-size: 1.2rem; margin-top: 1.5rem; }}
    p, li {{ font-size: 1.05rem; }}
    .meta {{ font-size: 0.9rem; color: #666; margin-bottom: 2rem; }}
    .back-home {{ display: inline-block; margin-bottom: 20px; color: var(--primary); text-decoration: none; }}
    .faq-item {{ background: #f9f9f9; border-radius: 8px; padding: 12px 18px; margin-bottom: 12px; }}
  </style>
</head>
<body>
  <a href="index.html" class="back-home">&larr; Home</a>
  <article>
    <h1>{data['title']}</h1>
    <div class="meta">Published on {human_date}</div>
    {data['body_html']}
    
    <h2>Frequently Asked Questions</h2>
    {faq_html}
  </article>
</body>
</html>"""


def update_sitemap_and_index(slug, title):
    """Updates sitemap.xml and docs/index.html with the new article link."""
    os.makedirs(DOCS_DIR, exist_ok=True)
    canonical_url = f"{SITE_URL}/{slug}.html"
    date_now = datetime.utcnow().strftime("%Y-%m-%d")

    # 1. Update sitemap.xml
    sitemap_path = os.path.join(DOCS_DIR, "sitemap.xml")
    entry = f"""  <url>
    <loc>{canonical_url}</loc>
    <lastmod>{date_now}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>\n</urlset>"""

    if not os.path.exists(sitemap_path):
        with open(sitemap_path, "w", encoding="utf-8") as f:
            f.write(f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{entry}')
    else:
        with open(sitemap_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "</urlset>" in content:
            with open(sitemap_path, "w", encoding="utf-8") as f:
                f.write(content.replace("</urlset>", entry))

    # 2. Update index.html
    index_path = os.path.join(DOCS_DIR, "index.html")
    new_link = f'<li><a href="{slug}.html">{title}</a> - <small>{date_now}</small></li>\n    <!-- new_links -->'

    if not os.path.exists(index_path):
        base_index = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Knowledge Base</title>
  <style>body {{ font-family: sans-serif; max-width: 760px; margin: 40px auto; padding: 0 20px; line-height: 1.6; }}</style>
</head>
<body>
  <h1>Recent Articles</h1>
  <ul>
    {new_link}
  </ul>
</body>
</html>"""
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(base_index)
    else:
        with open(index_path, "r", encoding="utf-8") as f:
            idx_content = f.read()
        if "<!-- new_links -->" in idx_content:
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(idx_content.replace("<!-- new_links -->", new_link))


def main():
    keyword = get_next_keyword()
    if not keyword:
        print("No pending keywords found in keywords.txt.")
        return

    print(f"Generating content for: {keyword}")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", keyword.lower()).strip("-")

    data = generate_seo_article(keyword)
    html = render_html(data, keyword, slug)

    file_path = os.path.join(DOCS_DIR, f"{slug}.html")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html)

    update_sitemap_and_index(slug, data["title"])
    mark_keyword_published(keyword)
    print(f"Successfully published: {file_path}")


if __name__ == "__main__":
    main()
