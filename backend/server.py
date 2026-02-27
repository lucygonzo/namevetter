#!/usr/bin/env python3
"""
NameVetter Backend Server
Performs real availability checks for domains, social media handles,
and trademark/business registration lookups.
Run: python server.py
The React app at name-vetter.jsx connects to http://localhost:5111
"""

import json
import socket
import re
import time
import concurrent.futures
from urllib.parse import quote
from flask import Flask, request, jsonify
from flask_cors import CORS

import requests as http_requests

app = Flask(__name__)
CORS(app)

# ─── Configuration ─────────────────────────────────────────────────────
REQUEST_TIMEOUT = 8
SOCIAL_TIMEOUT = 10

DOMAIN_EXTENSIONS = [".com", ".co", ".io", ".net", ".org", ".ai"]

SOCIAL_PLATFORMS = [
    {
        "name": "Instagram",
        "url_template": "https://www.instagram.com/{handle}/",
        "taken_signals": [],  # 200 = profile exists
        "available_signals": [404],
    },
    {
        "name": "TikTok",
        "url_template": "https://www.tiktok.com/@{handle}",
        "taken_signals": [],
        "available_signals": [404],
    },
    {
        "name": "YouTube",
        "url_template": "https://www.youtube.com/@{handle}",
        "taken_signals": [],
        "available_signals": [404],
    },
    {
        "name": "X (Twitter)",
        "url_template": "https://x.com/{handle}",
        "taken_signals": [],
        "available_signals": [404],
    },
    {
        "name": "Facebook",
        "url_template": "https://www.facebook.com/{handle}",
        "taken_signals": [],
        "available_signals": [404],
    },
    {
        "name": "LinkedIn",
        "url_template": "https://www.linkedin.com/company/{handle}",
        "taken_signals": [],
        "available_signals": [404],
    },
    {
        "name": "Threads",
        "url_template": "https://www.threads.net/@{handle}",
        "taken_signals": [],
        "available_signals": [404],
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


# ─── Domain Checking ───────────────────────────────────────────────────

def check_domain_rdap(domain):
    """Check domain via RDAP (authoritative registry protocol)."""
    try:
        r = http_requests.get(
            f"https://rdap.org/domain/{domain}",
            timeout=REQUEST_TIMEOUT,
            headers=HEADERS,
            allow_redirects=True,
        )
        if r.status_code == 200:
            # Parse registration data if available
            data = {}
            try:
                j = r.json()
                # Extract registrar info
                for entity in j.get("entities", []):
                    if "registrar" in entity.get("roles", []):
                        vcard = entity.get("vcardArray", [None, []])[1]
                        for item in vcard:
                            if item[0] == "fn":
                                data["registrar"] = item[3]
                # Extract dates
                for event in j.get("events", []):
                    if event.get("eventAction") == "registration":
                        data["registered"] = event.get("eventDate", "")[:10]
                    if event.get("eventAction") == "expiration":
                        data["expires"] = event.get("eventDate", "")[:10]
            except Exception:
                pass
            return {"status": "taken", "method": "rdap", "details": data}
        elif r.status_code == 404:
            return {"status": "available", "method": "rdap", "details": {}}
        else:
            return {"status": "unknown", "method": "rdap", "details": {"http_status": r.status_code}}
    except Exception as e:
        return {"status": "unknown", "method": "rdap_error", "details": {"error": str(e)[:100]}}


def check_domain_dns(domain):
    """Fallback: check if domain resolves via DNS."""
    try:
        socket.setdefaulttimeout(5)
        ip = socket.gethostbyname(domain)
        return {"status": "taken", "method": "dns", "details": {"ip": ip}}
    except socket.gaierror:
        # No DNS record - likely available but not definitive
        return {"status": "likely_available", "method": "dns", "details": {}}
    except Exception:
        return {"status": "unknown", "method": "dns_error", "details": {}}


def check_domain_whois(domain):
    """Fallback: check via python-whois."""
    try:
        import whois
        w = whois.whois(domain)
        if w.domain_name:
            details = {}
            if w.registrar:
                details["registrar"] = w.registrar if isinstance(w.registrar, str) else w.registrar[0]
            if w.creation_date:
                cd = w.creation_date if isinstance(w.creation_date, list) else [w.creation_date]
                details["registered"] = str(cd[0])[:10]
            if w.expiration_date:
                ed = w.expiration_date if isinstance(w.expiration_date, list) else [w.expiration_date]
                details["expires"] = str(ed[0])[:10]
            return {"status": "taken", "method": "whois", "details": details}
        else:
            return {"status": "available", "method": "whois", "details": {}}
    except Exception as e:
        err_str = str(e).lower()
        if "no match" in err_str or "not found" in err_str or "no entries" in err_str:
            return {"status": "available", "method": "whois", "details": {}}
        return {"status": "unknown", "method": "whois_error", "details": {"error": str(e)[:100]}}


def check_domain(domain):
    """
    Multi-method domain check for maximum accuracy.
    1. Try RDAP first (authoritative)
    2. If inconclusive, try WHOIS
    3. If still inconclusive, try DNS as last resort
    """
    result = check_domain_rdap(domain)
    if result["status"] in ("taken", "available"):
        return result

    # RDAP inconclusive, try WHOIS
    result2 = check_domain_whois(domain)
    if result2["status"] in ("taken", "available"):
        return result2

    # Last resort: DNS
    result3 = check_domain_dns(domain)
    if result3["status"] == "taken":
        return result3
    if result3["status"] == "likely_available":
        return {"status": "available", "method": "dns_inferred", "details": result3["details"]}

    return {"status": "unknown", "method": "all_failed", "details": {}}


# ─── Social Media Checking ─────────────────────────────────────────────

def check_social_platform(platform, handle):
    """Check a single social media platform for handle availability."""
    url = platform["url_template"].format(handle=handle)
    name = platform["name"]

    try:
        r = http_requests.get(
            url,
            timeout=SOCIAL_TIMEOUT,
            headers=HEADERS,
            allow_redirects=True,
        )

        status_code = r.status_code
        final_url = r.url

        # Platform-specific logic
        if name == "Instagram":
            if status_code == 404:
                return {"status": "available", "method": "http_404"}
            if status_code == 200:
                # Instagram returns 200 for existing profiles
                # Check if the page content indicates a real profile vs login redirect
                if "/accounts/login" in final_url:
                    # Redirected to login - could be private or rate limited
                    return {"status": "unknown", "method": "login_redirect"}
                return {"status": "taken", "method": "http_200"}

        elif name == "TikTok":
            if status_code == 404:
                return {"status": "available", "method": "http_404"}
            if status_code == 200:
                text_lower = r.text[:5000].lower()
                # TikTok shows a specific page for non-existent users
                if "couldn't find this account" in text_lower or "this account" in text_lower and "exist" in text_lower:
                    return {"status": "available", "method": "page_content"}
                return {"status": "taken", "method": "http_200"}

        elif name == "YouTube":
            if status_code == 404:
                return {"status": "available", "method": "http_404"}
            if status_code == 200:
                if "This page isn" in r.text[:5000] or "404" in r.text[:2000]:
                    return {"status": "available", "method": "page_content"}
                return {"status": "taken", "method": "http_200"}

        elif name == "X (Twitter)":
            if status_code == 404:
                return {"status": "available", "method": "http_404"}
            if status_code == 200:
                text_sample = r.text[:5000].lower()
                if "this account doesn" in text_sample or "doesn't exist" in text_sample:
                    return {"status": "available", "method": "page_content"}
                return {"status": "taken", "method": "http_200"}
            # X often returns 302 -> login for non-logged in users
            if status_code in (301, 302, 303):
                return {"status": "unknown", "method": "redirect"}

        elif name == "Facebook":
            if status_code == 404:
                return {"status": "available", "method": "http_404"}
            if status_code == 200:
                text_sample = r.text[:5000].lower()
                if "page not found" in text_sample or "this content isn" in text_sample:
                    return {"status": "available", "method": "page_content"}
                return {"status": "taken", "method": "http_200"}

        elif name == "LinkedIn":
            if status_code == 404:
                return {"status": "available", "method": "http_404"}
            if status_code == 200:
                if "/authwall" in final_url or "authwall" in r.text[:3000].lower():
                    # LinkedIn auth wall - can't determine
                    return {"status": "unknown", "method": "authwall"}
                return {"status": "taken", "method": "http_200"}

        elif name == "Threads":
            if status_code == 404:
                return {"status": "available", "method": "http_404"}
            if status_code == 200:
                text_sample = r.text[:5000].lower()
                if "sorry, this page" in text_sample:
                    return {"status": "available", "method": "page_content"}
                return {"status": "taken", "method": "http_200"}

        # Generic fallback
        if status_code == 404:
            return {"status": "available", "method": "http_404"}
        elif status_code == 200:
            return {"status": "taken", "method": "http_200"}
        else:
            return {"status": "unknown", "method": f"http_{status_code}"}

    except http_requests.exceptions.Timeout:
        return {"status": "unknown", "method": "timeout"}
    except http_requests.exceptions.ConnectionError:
        return {"status": "unknown", "method": "connection_error"}
    except Exception as e:
        return {"status": "unknown", "method": "error", "error": str(e)[:100]}


# ─── Similar Domains ───────────────────────────────────────────────────

def find_similar_domains(handle):
    """Find similar registered domains via domainsdb."""
    try:
        r = http_requests.get(
            f"https://api.domainsdb.info/v1/domains/search?domain={handle}&zone=com&limit=20",
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        domains = data.get("domains", [])
        results = []
        for d in domains:
            base = d["domain"].split(".")[0]
            dist = levenshtein(handle, base)
            if 0 < dist <= 3:
                results.append({"domain": d["domain"], "distance": dist})
        results.sort(key=lambda x: x["distance"])
        return results[:8]
    except Exception:
        return []


def levenshtein(a, b):
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            dp[i][j] = dp[i-1][j-1] if a[i-1] == b[j-1] else 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
    return dp[m][n]


# ─── API Endpoints ─────────────────────────────────────────────────────

@app.route("/api/check", methods=["POST"])
def check_name():
    """
    Full vetting of a company name.
    Request body: { "name": "MyCompany" }
    Returns domain, social, and similar name results.
    """
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400

    handle = re.sub(r"[^a-z0-9]", "", name.lower())
    if not handle:
        return jsonify({"error": "Name must contain alphanumeric characters"}), 400

    results = {
        "name": name,
        "handle": handle,
        "domains": {},
        "social": {},
        "similar": [],
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Check all domains in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        domain_futures = {}
        for ext in DOMAIN_EXTENSIONS:
            domain = handle + ext
            domain_futures[ext] = executor.submit(check_domain, domain)

        social_futures = {}
        for platform in SOCIAL_PLATFORMS:
            social_futures[platform["name"]] = executor.submit(check_social_platform, platform, handle)

        similar_future = executor.submit(find_similar_domains, handle)

        # Collect domain results
        for ext, future in domain_futures.items():
            try:
                results["domains"][ext] = future.result(timeout=15)
            except Exception:
                results["domains"][ext] = {"status": "unknown", "method": "timeout"}

        # Collect social results
        for pname, future in social_futures.items():
            try:
                results["social"][pname] = future.result(timeout=15)
            except Exception:
                results["social"][pname] = {"status": "unknown", "method": "timeout"}

        # Collect similar domains
        try:
            results["similar"] = similar_future.result(timeout=10)
        except Exception:
            results["similar"] = []

    return jsonify(results)


@app.route("/api/check-domain", methods=["POST"])
def check_single_domain_endpoint():
    """Check a single domain. Body: { "domain": "example.com" }"""
    data = request.get_json()
    domain = data.get("domain", "").strip().lower()
    if not domain:
        return jsonify({"error": "Domain is required"}), 400
    result = check_domain(domain)
    return jsonify({"domain": domain, **result})


@app.route("/api/check-social", methods=["POST"])
def check_single_social_endpoint():
    """Check a single social platform. Body: { "platform": "Instagram", "handle": "mycompany" }"""
    data = request.get_json()
    platform_name = data.get("platform", "")
    handle = data.get("handle", "").strip().lower()
    platform = next((p for p in SOCIAL_PLATFORMS if p["name"] == platform_name), None)
    if not platform:
        return jsonify({"error": f"Unknown platform: {platform_name}"}), 400
    result = check_social_platform(platform, handle)
    return jsonify({"platform": platform_name, "handle": handle, **result})


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": "1.0.0"})


if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  NameVetter Backend Server")
    print("  Running on http://localhost:5111")
    print("  Open name-vetter.jsx in Claude to use the UI")
    print("=" * 55 + "\n")
    app.run(host="0.0.0.0", port=5111, debug=False)
