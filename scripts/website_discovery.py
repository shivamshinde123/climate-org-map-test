"""Brave Search website discovery and deterministic contact extraction.

Brave is the primary discovery path; this module is called by
enrich_organizations_with_jev.py before the OpenAI fallback.
"""

from __future__ import annotations

import html.parser
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

USER_AGENT = "GCC-Climate-Organization-Map/0.1"
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

_DIRECTORY_HOSTS = frozenset({
    "guidestar.org", "candid.org", "charitynavigator.org", "irs.gov",
    "propublica.org", "facebook.com", "linkedin.com", "twitter.com",
    "instagram.com", "wikipedia.org", "youtube.com", "bbb.org",
    "give.org", "charitywatch.org",
})
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}(?!\d)")


def _is_directory(url: str) -> bool:
    try:
        host = urllib.parse.urlparse(url).netloc.lower().lstrip("www.")
        return any(d in host for d in _DIRECTORY_HOSTS)
    except Exception:
        return True


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(text).casefold()).strip()


def _identity_score(result: dict, name_norm: str, city_norm: str, state: str) -> float:
    """Score a Brave result 0–1 for identity match against the org."""
    url = result.get("url", "")
    if _is_directory(url):
        return 0.0
    combined = _norm(result.get("title", "")) + " " + _norm(result.get("description", ""))
    score = 0.0
    name_words = [w for w in name_norm.split() if len(w) > 3]
    if name_words:
        score += 0.6 * sum(1 for w in name_words if w in combined) / len(name_words)
    if city_norm and city_norm in combined:
        score += 0.2
    if state and state.casefold() in combined:
        score += 0.1
    try:
        if urllib.parse.urlparse(url).netloc.lower().endswith(".org"):
            score += 0.1
    except Exception:
        pass
    return min(score, 1.0)


class _HTMLParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.mailto: list[str] = []
        self.tel: list[str] = []
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        for attr, val in attrs:
            if attr != "href" or not val:
                continue
            if val.startswith("mailto:"):
                self.mailto.append(val[7:].split("?")[0].strip())
            elif val.startswith("tel:"):
                self.tel.append(re.sub(r"[^\d+]", "", val[4:]))
            else:
                self.links.append(val)

    def handle_data(self, data):
        self._text.append(data)

    @property
    def text(self) -> str:
        return " ".join(self._text)


def _robots_allowed(url: str) -> bool:
    try:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(urllib.parse.urljoin(url, "/robots.txt"))
        rp.read()
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def _fetch(url: str, timeout: int = 12) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ct = resp.headers.get("Content-Type", "")
            if not ct.startswith("text/"):
                return None
            charset = "utf-8"
            if "charset=" in ct:
                charset = ct.split("charset=")[-1].split(";")[0].strip()
            return resp.read(1_000_000).decode(charset, errors="replace")
    except Exception:
        return None


def _extract_contacts(html_text: str, base_url: str) -> dict[str, str]:
    parser = _HTMLParser()
    try:
        parser.feed(html_text)
    except Exception:
        pass

    # mailto: links are more reliable than text regex
    email = parser.mailto[0] if parser.mailto else ""
    if not email:
        matches = _EMAIL_RE.findall(parser.text)
        preferred_prefixes = ("info", "contact", "office", "hello", "programs", "admin")
        email = next(
            (e for e in matches if e.split("@")[0].lower() in preferred_prefixes),
            matches[0] if matches else "",
        )

    phone = ""
    if parser.tel:
        phone = parser.tel[0]
    else:
        matches = _PHONE_RE.findall(parser.text)
        phone = matches[0].strip() if matches else ""

    contact_page_url = ""
    base_netloc = urllib.parse.urlparse(base_url).netloc
    for href in parser.links:
        if any(w in href.lower() for w in ("/contact", "/about", "/reach", "/staff", "/team")):
            try:
                abs_url = urllib.parse.urljoin(base_url, href)
                if urllib.parse.urlparse(abs_url).netloc == base_netloc:
                    contact_page_url = abs_url
                    break
            except Exception:
                pass

    return {"email": email, "phone": phone, "contact_page_url": contact_page_url}


def crawl_for_contacts(website_url: str) -> dict:
    """Fetch homepage then contact page; return {email, phone, contact_page_url, accessible}.

    ``accessible`` is True when the site was reached (even if no contacts found),
    False when robots.txt denied access or the site was unreachable. Callers use
    ``accessible=False`` to decide whether an OpenAI fallback is warranted.
    """
    blocked: dict = {"email": "", "phone": "", "contact_page_url": "", "accessible": False}
    if not _robots_allowed(website_url):
        return blocked
    html_text = _fetch(website_url)
    if not html_text:
        return blocked
    contacts = _extract_contacts(html_text, website_url)
    if contacts["contact_page_url"] and contacts["contact_page_url"] != website_url:
        if _robots_allowed(contacts["contact_page_url"]):
            deeper = _fetch(contacts["contact_page_url"])
            if deeper:
                deeper_contacts = _extract_contacts(deeper, contacts["contact_page_url"])
                if not contacts["email"]:
                    contacts["email"] = deeper_contacts["email"]
                if not contacts["phone"]:
                    contacts["phone"] = deeper_contacts["phone"]
    contacts["accessible"] = True
    return contacts


def brave_discover(properties: dict, brave_key: str) -> dict | None:
    """Query Brave Search; return a discovery dict when confident, else None.

    None signals the caller to fall through to the OpenAI path.
    """
    name = properties.get("name", "")
    city = properties.get("city", "")
    state = properties.get("state", "")
    name_norm = _norm(name)
    city_norm = _norm(city)

    query = f'"{name}" {city} {state} nonprofit'
    params = urllib.parse.urlencode({"q": query, "count": 5, "search_lang": "en"})
    req = urllib.request.Request(
        f"{BRAVE_ENDPOINT}?{params}",
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "X-Subscription-Token": brave_key,
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            results = json.loads(resp.read()).get("web", {}).get("results", [])
    except Exception:
        return None  # network/auth failure → OpenAI fallback

    scored = [
        (r, _identity_score(r, name_norm, city_norm, state))
        for r in results
        if not _is_directory(r.get("url", ""))
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    if not scored or scored[0][1] < 0.5:
        return None  # not confident enough → OpenAI fallback

    top, score = scored[0]
    return {
        "status": "found",
        "website_url": top["url"],
        "summary": top.get("description", ""),
        "evidence": top.get("description", ""),
        "source_urls": [top["url"]],
        "confidence": "high" if score >= 0.8 else "medium",
        "rationale": f"Brave Search match score {score:.2f}",
    }
