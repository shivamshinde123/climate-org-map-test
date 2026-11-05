"""Brave Search website discovery and deterministic contact extraction.

Brave is the primary discovery path; this module is called by
enrich_organizations_with_jev.py before the OpenRouter web-search fallback.
"""

from __future__ import annotations

import html
import html.parser
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

try:
    from . import api_log
except ImportError:  # Allows direct execution from the scripts directory.
    import api_log  # type: ignore

USER_AGENT = "GCC-Climate-Organization-Map/0.1"
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

# Nonprofit directories, social networks and data aggregators: a page about the
# organization on one of these is never its official website.
_DIRECTORY_HOSTS = frozenset({
    "guidestar.org", "candid.org", "charitynavigator.org", "irs.gov",
    "propublica.org", "facebook.com", "linkedin.com", "twitter.com", "x.com",
    "instagram.com", "wikipedia.org", "youtube.com", "bbb.org",
    "give.org", "charitywatch.org", "getholdings.com", "greatnonprofits.org",
    "causeiq.com", "idealist.org", "open990.org", "taxexemptworld.com",
    "nonprofitlight.com", "charityfootprints.com", "opencorporates.com",
    "bizapedia.com", "dnb.com", "zoominfo.com", "yelp.com", "mapquest.com",
    "manta.com", "volunteermatch.org", "benevity.org", "givefreely.com",
    "everydayhero.com", "networkforgood.org", "donorbox.org", "gofundme.com",
    "nonprofitfacts.com", "eintaxid.com", "faqs.org", "corporationwiki.com",
    "allbiz.com", "chamberofcommerce.com", "nextdoor.com", "tiktok.com",
    "pinterest.com", "threads.net", "meetup.com", "eventbrite.com",
})
# Listing pages keyed by EIN or organization slug, whatever the host.
_DIRECTORY_PATH_RE = re.compile(r"/(ein|nonprofits?|charit(y|ies)|organizations?|org|profile)/", re.I)
# A document that merely mentions the organization (e.g. a state agency PDF).
_DOCUMENT_PATH_RE = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|txt|csv)$", re.I)
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}(?!\d)")
# Small nonprofits often use a personal mailbox instead of their own domain.
_FREEMAIL_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "aol.com",
    "icloud.com", "comcast.net", "verizon.net", "att.net", "msn.com", "live.com",
})


def site_domain(url_or_host: str) -> str:
    """Return the last two labels of a host (``www.akfarmland.com`` → ``akfarmland.com``)."""
    # ponytail: two-label registrable domain; wrong for .co.uk-style suffixes, rare in IRS data.
    host = urllib.parse.urlparse(url_or_host).netloc or url_or_host
    labels = host.lower().split(":")[0].strip(".").split(".")
    return ".".join(labels[-2:])


def is_directory(url: str) -> bool:
    """Return whether a URL is a directory, aggregator or document rather than an official site."""
    try:
        if site_domain(url) in _DIRECTORY_HOSTS:
            return True
        path = urllib.parse.urlparse(url).path
        return bool(_DIRECTORY_PATH_RE.search(path) or _DOCUMENT_PATH_RE.search(path))
    except Exception:
        return True


def email_matches_site(email: str, website_url: str) -> bool:
    """Accept only the organization's own domain or a free personal mailbox."""
    if not _EMAIL_RE.fullmatch(email or ""):
        return False
    domain = site_domain(email.rsplit("@", 1)[1])
    return domain == site_domain(website_url) or domain in _FREEMAIL_DOMAINS


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(text).casefold()).strip()


def _identity_score(result: dict, name_norm: str, city_norm: str, state: str) -> float:
    """Score a Brave result 0–1 for identity match against the org."""
    url = result.get("url", "")
    if is_directory(url):
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


class BraveKeyError(RuntimeError):
    """Brave rejected the API key or plan; continuing would silently pay for fallbacks."""


def clean_text(value: str) -> str:
    """Strip HTML tags, entities and U+FFFD garbage (Brave snippets carry both)."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", value or "")).replace("�", "")
    return " ".join(text.split())


def decode_cfemail(encoded: str) -> str:
    """Decode Cloudflare's email obfuscation (hex string XOR-ed with its first byte)."""
    try:
        data = bytes.fromhex(encoded)
        return bytes(b ^ data[0] for b in data[1:]).decode("utf-8")
    except (ValueError, IndexError, UnicodeDecodeError):
        return ""


class _HTMLParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.mailto: list[str] = []
        self.tel: list[str] = []
        self.description = ""
        self.paragraphs: list[str] = []
        self._text: list[str] = []
        self._paragraph: list[str] | None = None
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self._skip_depth += 1
        if tag == "p":
            self._paragraph = []
        if values.get("data-cfemail"):
            self.mailto.append(decode_cfemail(values["data-cfemail"]))
        if tag == "meta":
            key = (values.get("name") or values.get("property") or "").lower()
            if key in ("description", "og:description") and not self.description:
                self.description = clean_text(values.get("content", ""))
        if tag != "a":
            return
        val = values.get("href") or ""
        if val.startswith("mailto:"):
            self.mailto.append(val[7:].split("?")[0].strip())
        elif "/cdn-cgi/l/email-protection#" in val:
            self.mailto.append(decode_cfemail(val.rsplit("#", 1)[1]))
        elif val.startswith("tel:"):
            self.tel.append(re.sub(r"[^\d+]", "", val[4:]))
        elif val:
            self.links.append(val)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip_depth:
            self._skip_depth -= 1
        if tag == "p" and self._paragraph is not None:
            self.paragraphs.append(clean_text(" ".join(self._paragraph)))
            self._paragraph = None

    def handle_data(self, data):
        if self._skip_depth:
            return
        self._text.append(data)
        if self._paragraph is not None:
            self._paragraph.append(data)

    @property
    def text(self) -> str:
        return " ".join(self._text)

    @property
    def first_paragraph(self) -> str:
        """First substantial paragraph, a fallback summary for sites without a meta description."""
        return next((p for p in self.paragraphs if len(p) >= 80), "")


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

    # mailto: links are more reliable than text regex. Either way the address must
    # belong to the site (or a free mailbox), not a web designer or directory.
    mailto = [e for e in parser.mailto if email_matches_site(e, base_url)]
    email = mailto[0] if mailto else ""
    if not email:
        matches = [e for e in _EMAIL_RE.findall(parser.text) if email_matches_site(e, base_url)]
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
    ``accessible=False`` to decide whether an OpenRouter fallback is warranted.
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


def page_profile(url: str) -> dict[str, str]:
    """Return the page's meta description, first substantial paragraph and a text excerpt."""
    empty = {"description": "", "paragraph": "", "excerpt": ""}
    if not _robots_allowed(url):
        return empty
    html_text = _fetch(url)
    if not html_text:
        return empty
    parser = _HTMLParser()
    try:
        parser.feed(html_text)
    except Exception:
        pass
    return {
        "description": parser.description,
        "paragraph": parser.first_paragraph,
        "excerpt": " ".join(parser.text.split())[:2000],
    }


def _brave_search(query: str, brave_key: str, retries: int = 3) -> list[dict] | None:
    """Run one logged Brave web search; None means fall back to OpenRouter."""
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
    for attempt in range(1, retries + 1):
        try:
            raw = api_log.send(req, "brave", "website_discovery", timeout=15)
            return json.loads(raw).get("web", {}).get("results", [])
        except urllib.error.HTTPError as error:
            if error.code in (401, 403, 422):
                raise BraveKeyError(
                    f"Brave rejected the request (HTTP {error.code}): check BRAVE_API_KEY "
                    f"and that a Search plan is active. Details: {error.read().decode('utf-8', 'replace')[:300]}"
                ) from None
            if error.code == 429 and attempt < retries:
                time.sleep(2 * attempt)
                continue
            api_log.decision("brave_error", reason=f"HTTP {error.code}")
            return None
        except Exception as error:
            api_log.decision("brave_error", reason=f"{type(error).__name__}: {error}")
            return None
    return None


def brave_discover(properties: dict, brave_key: str) -> dict | None:
    """Query Brave Search; return a discovery dict when confident, else None.

    None signals the caller to fall through to the OpenRouter path. The summary
    comes from the matched site itself (meta description, else first substantial
    paragraph), since Brave snippets are short and may describe a single page.
    """
    name = properties.get("name", "")
    city = properties.get("city", "")
    state = properties.get("state", "")
    name_norm = _norm(name)
    city_norm = _norm(city)

    results = _brave_search(f'"{name}" {city} {state} nonprofit', brave_key)
    if results is None:
        return None

    skipped = [r.get("url") for r in results if is_directory(r.get("url", ""))]
    scored = [
        (r, _identity_score(r, name_norm, city_norm, state))
        for r in results
        if not is_directory(r.get("url", ""))
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    candidates = [{"url": r.get("url"), "score": round(s, 2)} for r, s in scored]
    if not scored or scored[0][1] < 0.5:
        api_log.decision(
            "brave_rejected", reason="no non-directory result scored >= 0.5",
            candidates=candidates, skipped_directories=skipped,
        )
        return None

    top, score = scored[0]
    snippet = clean_text(top.get("description", ""))
    page = page_profile(top["url"])
    summary, summary_source = next(
        ((text, source) for text, source in (
            (page["description"], "site meta description"),
            (page["paragraph"], "site first paragraph"),
            (snippet, "brave snippet"),
        ) if text),
        ("", ""),
    )
    if not summary:
        api_log.decision("brave_rejected", reason="matched site has no description", url=top["url"])
        return None
    api_log.decision(
        "brave_accepted", reason=f"score {score:.2f}", url=top["url"],
        summary_source=summary_source, candidates=candidates, skipped_directories=skipped,
    )
    return {
        "status": "found",
        "website_url": top["url"],
        "summary": summary,
        "evidence": "\n\n".join(part for part in (snippet, page["excerpt"]) if part),
        "source_urls": [top["url"]],
        "confidence": "high" if score >= 0.8 else "medium",
        "rationale": f"Brave Search match score {score:.2f}",
    }
