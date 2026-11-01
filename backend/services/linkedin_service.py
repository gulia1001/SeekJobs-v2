"""Parse a LinkedIn profile via the Apify SDK (needs APIFY_TOKEN).

TODO (roadmap Phase 2): replace scraping with "upload your LinkedIn PDF export".
Scraping LinkedIn breaks its terms of service and is a legal risk for the business.
"""
import asyncio
import os


async def parse_linkedin(linkedin_url: str) -> dict:
    """Return cleaned profile data, {} if not configured, or {"error": ...}."""
    # the Apify call blocks for up to a minute — keep it off the event loop
    return await asyncio.to_thread(_try_apify_sdk, linkedin_url) or {}


def _try_apify_sdk(url: str) -> dict:
    """Direct Apify call — requires APIFY_TOKEN env var."""
    token = os.getenv("APIFY_TOKEN")
    if not token:
        return {}
    try:
        from apify_client import ApifyClient  # type: ignore

        client = ApifyClient(token)
        run = client.actor("harvestapi/linkedin-profile-scraper").call(
            run_input={"urls": [url], "proxyConfiguration": {"useApifyProxy": True}}
        )
        items = client.dataset(run["defaultDatasetId"]).list_items().items
        if not items:
            return {}
        raw = items[0]
        return _clean(raw)
    except Exception as e:
        return {"error": str(e)}


def _clean(raw: dict) -> dict:
    raw_certs = raw.get("certifications") or raw.get("licensesAndCertifications") or []
    return {
        "fullName": f"{raw.get('firstName', '')} {raw.get('lastName', '')}".strip() or raw.get("name", ""),
        "headline": raw.get("headline", ""),
        "location": (raw.get("location") or {}).get("parsed", {}).get("text", ""),
        "experience": [
            {
                "title": e.get("position") or e.get("title", ""),
                "company": e.get("companyName", ""),
                "start": (e.get("startDate") or {}).get("text", "N/A"),
                "end": (e.get("endDate") or {}).get("text", "Present"),
            }
            for e in (raw.get("experience") or [])
        ],
        "education": [
            {
                "school": edu.get("schoolName") or edu.get("school", ""),
                "degree": edu.get("degree", ""),
                "period": edu.get("period", ""),
            }
            for edu in (raw.get("education") or [])
        ],
        "certifications": [
            {
                "name": c.get("name") or c.get("title", ""),
                "authority": c.get("authority") or c.get("issuingOrganizationName", ""),
            }
            for c in raw_certs
        ],
        "skills": [
            (s if isinstance(s, str) else s.get("name", ""))
            for s in (raw.get("skills") or [])
        ],
    }
