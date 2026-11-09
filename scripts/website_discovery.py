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
from pathlib import Path

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
    # Funders, grant databases, donation/volunteer platforms and business-data
    # sites seen in the 2026-11-05 Rhode Island run.
    "philanthropy.org", "grassrootsfund.org", "instrumentl.com", "grantedai.com",
    "foundationcenter.org", "roundup.org", "youcangiveback.com", "opengovus.com",
    "b2bhint.com", "uwri.org", "unitedway.org", "actionnetwork.org", "anakalypsis.com",
    "givebutter.com", "classy.org", "networkforgood.com", "justgiving.com",
    "grantstation.com", "buzzfile.com",
    # Environmental news outlets.
    "ecori.org", "patch.com", "providencejournal.com", "bostonglobe.com",
})
# Listing pages keyed by EIN or organization slug, whatever the host.
_DIRECTORY_PATH_RE = re.compile(r"/(ein|nonprofits?|charit(y|ies)|organizations?|org|profile)/", re.I)
# Database-style query strings (?agency_id=, ?FlexDataID=) mark listing pages.
_ID_QUERY_RE = re.compile(r"(^|&)[a-z_]*id=", re.I)
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
    """Return whether a URL is a directory, aggregator, government page or document.

    IRS-registered nonprofits are not government bodies, so a ``.gov`` page is
    always a page *about* the organization (a registry, grant or court record).
    """
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower().split(":")[0]
        if site_domain(url) in _DIRECTORY_HOSTS or host.endswith((".gov", ".mil")):
            return True
        return bool(
            _DIRECTORY_PATH_RE.search(parsed.path)
            or _DOCUMENT_PATH_RE.search(parsed.path)
            or _ID_QUERY_RE.search(parsed.query)
        )
    except Exception:
        return True


_PHONE_LABEL_RE = re.compile(r"\b(phone|call|tel|telephone|ph|office|reach us|contact)\b")


def normalize_phone(raw: str) -> str:
    """Return a valid US number as ``(AAA) EEE-NNNN``, or "" when it isn't one."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    # NANP: area code and exchange both start with 2-9.
    if len(digits) != 10 or digits[0] in "01" or digits[3] in "01":
        return ""
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def email_matches_site(email: str, website_url: str) -> bool:
    """Accept only the organization's own domain or a free personal mailbox."""
    if not _EMAIL_RE.fullmatch(email or ""):
        return False
    domain = site_domain(email.rsplit("@", 1)[1])
    return domain == site_domain(website_url) or domain in _FREEMAIL_DOMAINS


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(text).casefold()).strip()


_STATE_NAMES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas", "CA": "california",
    "CO": "colorado", "CT": "connecticut", "DE": "delaware", "DC": "district of columbia",
    "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho", "IL": "illinois",
    "IN": "indiana", "IA": "iowa", "KS": "kansas", "KY": "kentucky", "LA": "louisiana",
    "ME": "maine", "MD": "maryland", "MA": "massachusetts", "MI": "michigan", "MN": "minnesota",
    "MS": "mississippi", "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "new hampshire", "NJ": "new jersey", "NM": "new mexico", "NY": "new york",
    "NC": "north carolina", "ND": "north dakota", "OH": "ohio", "OK": "oklahoma", "OR": "oregon",
    "PA": "pennsylvania", "RI": "rhode island", "SC": "south carolina", "SD": "south dakota",
    "TN": "tennessee", "TX": "texas", "UT": "utah", "VT": "vermont", "VA": "virginia",
    "WA": "washington", "WV": "west virginia", "WI": "wisconsin", "WY": "wyoming",
}
# Words that add no identity on their own: legal suffixes and the stock nouns
# shared by thousands of conservation groups.
_STOP_WORDS = {"the", "of", "and", "for", "a", "an", "at", "in", "on", "inc", "incorporated", "co", "corp"}
_GENERIC_WORDS = _STOP_WORDS | {
    "association", "assn", "assoc", "foundation", "fund", "society", "council", "trust",
    "friends", "corporation", "company", "committee", "club", "organization", "group",
    "center", "centre", "coalition", "project", "alliance", "network", "institute",
    "partnership", "conservancy", "conservation", "preservation", "watershed", "land",
    "river", "lake", "pond", "park", "north", "south", "east", "west", "united",
    "states", "america", "american", "national", "international", "community",
    "citizens", "environmental", "education", "educational", "improvement", "chapter",
}


def domain_matches_name(url: str, name: str) -> bool:
    """Return whether a URL's domain is plausibly the organization's own.

    True when the domain label contains a distinctive name word
    (``burrillvillelandtrust``), two adjacent name words run together
    (``westbaylandtrust``) or the name's initials (``sklt`` for South
    Kingstown Land Trust, ``foghp`` for Friends Of Green Hill Pond).
    """
    return label_matches_name(site_domain(url).split(".")[0], name)


def label_matches_name(label: str, name: str) -> bool:
    """Name test shared by domains and page slugs (``facebook.com/MiddleDamPond``)."""
    label = re.sub(r"[^a-z0-9]", "", label.lower())
    words = _norm(name).split()
    if not label or not words:
        return False
    if any(len(w) >= 4 and w not in _GENERIC_WORDS and w in label for w in words):
        return True
    core = [w for w in words if w not in _STOP_WORDS]
    if any(len(a + b) >= 7 and a + b in label for a, b in zip(core, core[1:])):
        return True
    # Initials must be the whole label, or a 4+ letter prefix: "rie" (RI Envirothon)
    # wrongly matched "rieea" (RI Environmental Education Association).
    for initials in ("".join(w[0] for w in words), "".join(w[0] for w in core)):
        if len(initials) >= 3 and (label == initials or (len(initials) >= 4 and label.startswith(initials))):
            return True
    return False


def is_homepage_like(url: str) -> bool:
    """A site's front page: no path beyond an index file and no query.

    Any deeper page on a domain that doesn't match the name is a page *about*
    the organization (alaskaadvisor.com/bootlegger.html named Glacier Grotto).
    """
    parsed = urllib.parse.urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]
    return not parsed.query and (
        not segments or (len(segments) == 1 and segments[0].lower() in ("index.html", "index.php", "home"))
    )


def _identity_score(result: dict, name_norm: str, city_norm: str, state: str) -> float:
    """Score how strongly a Brave result's title and snippet name the organization (0–1)."""
    url = result.get("url", "")
    if is_directory(url):
        return 0.0
    combined = " " + _norm(result.get("title", "")) + " " + _norm(result.get("description", "")) + " "
    score = 0.0
    name_words = [w for w in name_norm.split() if len(w) > 3]
    if name_words:
        score += 0.6 * sum(1 for w in name_words if w in combined) / len(name_words)
    if city_norm and f" {city_norm} " in combined:
        score += 0.2
    state_name = _STATE_NAMES.get(state.upper(), "")
    if state and (f" {state.casefold()} " in combined or (state_name and f" {state_name} " in combined)):
        score += 0.2
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

    # tel: links are the site's own declared number. Plain-text numbers count only
    # when labelled as a phone, which skips fax lines and partners' numbers.
    phone = next((p for p in map(normalize_phone, parser.tel) if p), "")
    if not phone:
        labelled, unlabelled = [], set()
        for match in _PHONE_RE.finditer(parser.text):
            number = normalize_phone(match.group())
            label = parser.text[max(0, match.start() - 30):match.start()].lower()
            if not number or "fax" in label:
                continue
            if _PHONE_LABEL_RE.search(label):
                labelled.append(number)
            else:
                unlabelled.add(number)
        # Many small sites print one unlabelled number in the footer; a page
        # with several unlabelled numbers (partners, officers) is ambiguous.
        phone = labelled[0] if labelled else (next(iter(unlabelled)) if len(unlabelled) == 1 else "")

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
    if urllib.parse.urlparse(website_url).path.strip("/"):
        # Own-domain matches are stored as the homepage, so a deeper URL is the
        # organization's page on someone else's site (e.g. caves.org/grotto/x):
        # its phone and email belong to the host. Leave contacts blank, unpaid.
        return {"email": "", "phone": "", "contact_page_url": "", "accessible": True}
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


# Text that is about getting somewhere, paying, or the website itself rather
# than about the organization ("Mail a check to: P.O. Box 196", driving directions).
_JUNK_SUMMARY_RE = re.compile(
    r"p\.?\s?o\.?\s+box|mail (a|your) check|make checks? payable|\b(turn|bear) (left|right)\b|"
    r"\bmiles? (on|north|south|east|west)\b|cookies?\b|javascript|all rights reserved|copyright|©|"
    r"click here|log ?in\b|sign ?up\b|subscribe|newsletter|404|page not found",
    re.I,
)
# Wording that typically describes what an organization does.
_DESCRIPTIVE_RE = re.compile(
    r"\b(mission|dedicated|committed|non-?profit|501\s?\(?c\)?|organization|works? to|working to|"
    r"founded|protect|preserv|restor|conserv|educat|support|promot|advoca|volunteer|steward|"
    r"community|habitat|watershed|environment)",
    re.I,
)


def tidy_summary(text: str, limit: int = 320) -> str:
    """Trim to whole sentences within ``limit`` characters and drop a dangling fragment.

    Many meta descriptions are cut mid-word by the site itself ("…The Campbell").
    """
    text = clean_text(text).rstrip("…").rstrip()
    sentences = re.findall(r".+?[.!?](?=\s|$)", text)
    kept = ""
    for sentence in sentences:
        if len(kept) + len(sentence) > limit and kept:
            break
        kept += sentence
    if kept.strip() and len(kept.strip()) >= 60:
        return kept.strip()
    return text[:limit].rsplit(" ", 1)[0] + "…" if len(text) > limit else text


def _has_contact_details(text: str) -> bool:
    # Officer rosters ("President Jane Doe (401) 486-5174") must never become a public summary.
    return bool(_PHONE_RE.search(text) or _EMAIL_RE.search(text))


def choose_summary(candidates: list[tuple[str, str]], name: str) -> tuple[str, str]:
    """Pick the first candidate that reads like a description of the organization.

    ``candidates`` are ``(text, source)`` pairs in preference order. Short, junk
    and website-chrome text is skipped; text naming the organization or using
    descriptive wording wins; otherwise the first usable candidate is kept.
    """
    distinctive = [w for w in _norm(name).split() if len(w) >= 4 and w not in _GENERIC_WORDS]
    usable = [
        (tidy_summary(text), source)
        for text, source in candidates
        if text and len(clean_text(text)) >= 60 and not _JUNK_SUMMARY_RE.search(text)
        and not _has_contact_details(text)
    ]
    describes = (
        (text, source) for text, source in usable
        if _DESCRIPTIVE_RE.search(text) or any(w in _norm(text) for w in distinctive)
    )
    return next(describes, usable[0] if usable else ("", ""))


def page_profile(url: str) -> dict:
    """Return the page's meta description, substantial paragraphs and a text excerpt."""
    empty = {"description": "", "paragraphs": [], "excerpt": ""}
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
        "paragraphs": [p for p in parser.paragraphs if len(p) >= 80][:8],
        "excerpt": " ".join(parser.text.split())[:2000],
    }


# Raw Brave results keyed by query: changing the matching rules re-scores
# cached results instead of paying for the same searches again.
BRAVE_CACHE_PATH = Path(__file__).resolve().parents[1] / "Data" / "Website Enrichment" / "brave-cache.jsonl"
_brave_cache: dict[str, list] | None = None


def _cached_brave_results(query: str) -> list[dict] | None:
    global _brave_cache
    if _brave_cache is None:
        _brave_cache = {}
        if BRAVE_CACHE_PATH.exists():
            for line in BRAVE_CACHE_PATH.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    item = json.loads(line)
                    _brave_cache[item["query"]] = item["results"]
    return _brave_cache.get(query)


def _store_brave_results(query: str, results: list[dict]) -> None:
    _cached_brave_results(query)  # ensures the cache is loaded
    _brave_cache[query] = results
    BRAVE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with BRAVE_CACHE_PATH.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps({"query": query, "results": results}, ensure_ascii=False) + "\n")


def _brave_search(query: str, brave_key: str, retries: int = 3) -> list[dict] | None:
    """Run one logged Brave web search; None means fall back to OpenRouter."""
    cached = _cached_brave_results(query)
    if cached is not None:
        api_log.decision("brave_cache_hit", reason="reused cached Brave results; no API call", query=query)
        return cached
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
            results = json.loads(raw).get("web", {}).get("results", [])
            _store_brave_results(query, results)
            return results
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


def brave_query(properties: dict) -> str:
    return f'"{properties.get("name", "")}" {properties.get("city", "")} {properties.get("state", "")}'


# Facebook paths that are never an organization's own page.
_FACEBOOK_NON_PAGES = {"events", "groups", "watch", "marketplace", "photo", "photos", "posts", "share", "story.php", "people", "login", "public"}


def facebook_page(properties: dict) -> str:
    """Return the organization's Facebook page from cached Brave results, or "".

    For groups with no website of their own, a Facebook page is often their only
    web presence. Only cached results are read, so this never costs an API call;
    the page's slug must match the name (``facebook.com/MiddleDamPondAssociation``).
    """
    for result in _cached_brave_results(brave_query(properties)) or []:
        parsed = urllib.parse.urlparse(result.get("url", ""))
        if site_domain(parsed.netloc) != "facebook.com":
            continue
        segments = [s for s in parsed.path.split("/") if s]
        if not segments or segments[0].lower() in _FACEBOOK_NON_PAGES:
            continue
        # Pages live at /Name, /p/Name-123 (newer profiles) or /pages/Name/123.
        prefixed = segments[0] in ("p", "pages") and len(segments) > 1
        slug = segments[1] if prefixed else segments[0]
        if label_matches_name(slug, properties.get("name", "")):
            kept = segments[: 3 if segments[0] == "pages" else 2] if prefixed else segments[:1]
            return f"https://www.facebook.com/{'/'.join(kept)}/"
    return ""


def brave_discover(properties: dict, brave_key: str) -> dict | None:
    """Query Brave Search; return a discovery dict when confident, else None.

    None signals the caller to fall through to the OpenRouter path.

    A result is accepted when its domain looks like the organization's own and
    its text names the organization (score >= 0.4), or, without a domain match,
    only when it is a homepage-like page whose text names it strongly (>= 0.8).
    Pages that merely mention the organization (news, listings) fail both.
    The summary comes from the site itself where possible.
    """
    name = properties.get("name", "")
    city = properties.get("city", "")
    state = properties.get("state", "")
    name_norm = _norm(name)
    city_norm = _norm(city)

    results = _brave_search(brave_query(properties), brave_key)
    if results is None:
        return None

    skipped = [r.get("url") for r in results if is_directory(r.get("url", ""))]
    scored = sorted(
        (
            (r, _identity_score(r, name_norm, city_norm, state),
             domain_matches_name(r.get("url", ""), name), is_homepage_like(r.get("url", "")))
            for r in results
            if not is_directory(r.get("url", ""))
        ),
        key=lambda x: (x[2], x[1]),
        reverse=True,
    )
    candidates = [
        {"url": r.get("url"), "score": round(s, 2), "own_domain": own, "homepage": home}
        for r, s, own, home in scored
    ]
    chosen = next(
        (c for c in scored if (c[2] and c[1] >= 0.4) or (not c[2] and c[3] and c[1] >= 0.8)),
        None,
    )
    if chosen is None:
        api_log.decision(
            "brave_rejected", reason="no own-domain match and no strong homepage match",
            candidates=candidates, skipped_directories=skipped,
        )
        return None

    top, score, own_domain, _ = chosen
    return discovery_from_result(
        properties, top,
        confidence="high" if own_domain and score >= 0.6 else "medium",
        rationale=f"Brave Search match score {score:.2f}; own domain: {own_domain}",
        log_kind="brave_accepted", candidates=candidates, skipped_directories=skipped,
    )


def discovery_from_result(properties: dict, result: dict, confidence: str, rationale: str, log_kind: str, **log) -> dict | None:
    """Build a discovery record (website, summary, evidence) from one chosen Brave result."""
    name = properties.get("name", "")
    website_url = result["url"]
    if domain_matches_name(website_url, name):
        # Link the organization's front page, not whichever subpage ranked.
        parsed = urllib.parse.urlparse(website_url)
        website_url = f"{parsed.scheme}://{parsed.netloc}/"
    snippet = clean_text(result.get("description", ""))
    page = page_profile(website_url)
    summary, summary_source = choose_summary(
        [(page["description"], "site meta description")]
        + [(paragraph, "site paragraph") for paragraph in page["paragraphs"]]
        + [(snippet, "brave snippet")],
        name,
    )
    if not summary:
        api_log.decision("brave_rejected", reason="matched site has no description", url=website_url)
        return None
    api_log.decision(log_kind, reason=rationale, url=website_url, summary_source=summary_source, **log)
    return {
        "status": "found",
        "website_url": website_url,
        "summary": summary,
        "evidence": "\n\n".join(part for part in (snippet, page["excerpt"]) if part),
        "source_urls": [result["url"]],
        "confidence": confidence,
        "rationale": rationale,
    }


def brave_candidates(properties: dict) -> list[dict]:
    """Cached Brave results for this organization that could be an official site (no API call)."""
    return [
        r for r in _cached_brave_results(brave_query(properties)) or []
        if r.get("url") and not is_directory(r["url"])
    ]
