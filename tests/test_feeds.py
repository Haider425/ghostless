from tracker.models import Company
from tracker.sources import fetch_jobs, http, listing_is_complete, parse_rss, parse_sitemap

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://www.shopify.com/careers/applied-machine-learning-engineers_9f16f862-28ec-42d7-a9fa-948bf2eeeb4a</loc>
    <lastmod>2026-10-10T12:00:00Z</lastmod>
  </url>
  <url>
    <loc>https://www.shopify.com/careers/senior-data-engineer-ii_62d779d3-51c8-4b0a-ab2e-1a440276bb37</loc>
  </url>
  <url><loc>https://www.shopify.com/careers/extraordinary</loc></url>
</urlset>"""

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">
<channel>
  <item>
    <title>Software Engineer, Data Platform (Toronto)</title>
    <description><![CDATA[<p>Requisition ID: 1</p><p>We use <b>Spark</b> &amp; Kafka.</p><img src="data:image/png;base64,AAAA"/>]]></description>
    <link>https://jobs.scotiabank.com/job/Toronto-Software-Engineer/600000017/</link>
    <guid>600000017</guid>
    <g:id>600000017</g:id>
    <g:location>Toronto, ON, CA</g:location>
    <g:job_function>Technology</g:job_function>
  </item>
  <item>
    <title>Financial Planner</title>
    <link>https://jobs.scotiabank.com/job/x/600873017/</link>
    <guid>600873017</guid>
    <g:location>Maple Ridge, BC, CA</g:location>
  </item>
</channel>
</rss>"""


def test_parse_sitemap_keeps_only_job_pages():
    jobs = parse_sitemap(SITEMAP)
    assert [j.title for j in jobs] == ["Applied Machine Learning Engineers", "Senior Data Engineer II"]
    assert jobs[0].external_id == "9f16f862-28ec-42d7-a9fa-948bf2eeeb4a"
    assert jobs[0].posted_at.year == 2026
    assert jobs[1].posted_at is None


def test_parse_rss():
    first, second = parse_rss(RSS)
    assert first.external_id == "600000017"
    assert first.location == "Toronto, ON, CA"
    assert first.department == "Technology"
    assert "Spark & Kafka" in first.description and "base64" not in first.description
    assert second.external_id == "600873017"  # falls back to guid


def test_sitemap_region_fallback_and_completeness(monkeypatch):
    monkeypatch.setattr(http, "get_text", lambda url: SITEMAP)
    company = Company(
        "Shopify", "sitemap", "https://www.shopify.com/careers/sitemap.xml", region="Remote - Americas"
    )
    jobs = fetch_jobs(company)
    assert all(j.location == "Remote - Americas" for j in jobs)
    assert listing_is_complete(company)
