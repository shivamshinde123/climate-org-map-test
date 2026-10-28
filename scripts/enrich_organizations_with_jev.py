#!/usr/bin/env python3
"""Enrich organizations through website research and Jev classification.

The workflow deliberately separates two different responsibilities. OpenAI web
search finds the official organization website and returns source-grounded facts;
it is instructed not to choose project categories. The System One Jev model,
called through OpenRouter's Decisions API, then assigns all schema categories in
one request. Versioned caches and per-record completion checks make repeated runs
incremental and preserve an audit trail of both stages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

try:
    from .normalize_external_data_without_llm import CATEGORY_OPTIONS
    from .load_environment import load_environment
    from .website_discovery import brave_discover, crawl_for_contacts
except ImportError:  # Allows direct execution from the repository root.
    from normalize_external_data_without_llm import CATEGORY_OPTIONS  # type: ignore
    from load_environment import load_environment  # type: ignore
    from website_discovery import brave_discover, crawl_for_contacts  # type: ignore


OPENAI_ENDPOINT = "https://api.openai.com/v1/responses"
OPENROUTER_DECISIONS_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_SEARCH_MODEL = "gpt-5.4-mini"
DEFAULT_JEV_MODEL = "typesafe/jev-1.13"
DISCOVERY_VERSION = "gcc-website-discovery-v1"
JEV_QUESTIONS_VERSION = "gcc-jev-classification-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Jev's question identifiers intentionally match the source-neutral schema.
CLASSIFICATION_FIELDS = (
    "organization_type",
    "audience_focus",
    "adaptation_vs_mitigation",
    "advocacy_vs_action",
    "action_category",
    "climate_categories",
    "reach",
    "status",
)

# The frontend consumes the ``gcc_*`` aliases while retained generic fields make
# the enriched file reusable by downstream systems.
GCC_FIELD_BY_SCHEMA_FIELD = {
    "organization_type": "gcc_organization_type",
    "audience_focus": "gcc_audience_focus",
    "adaptation_vs_mitigation": "gcc_resilience",
    "advocacy_vs_action": "gcc_activity",
    "action_category": "gcc_action_category",
    "climate_categories": "gcc_climate_category",
    "reach": "gcc_reach",
    "status": "gcc_verification",
}

# These instructions give each Jev choice question a single semantic objective.
FIELD_INSTRUCTIONS = {
    "organization_type": "Choose the organization's entity type from the supplied criteria.",
    "audience_focus": "Choose the primary audience explicitly supported by the evidence.",
    "adaptation_vs_mitigation": "Choose the climate resilience orientation supported by the evidence.",
    "advocacy_vs_action": "Choose whether the organization primarily advocates, acts directly, or does both.",
    "action_category": "Choose the organization's primary kind of climate or environmental action.",
    "climate_categories": "Choose the primary climate or environmental subject area.",
    "reach": "Choose the geographic reach explicitly supported by the evidence.",
    "status": "Choose Verified only when the state contains explicit GCC verification evidence. An official website alone is not verification.",
}

# Choice descriptions provide evidence standards, not additional output values;
# the only valid answers remain the options declared in CATEGORY_OPTIONS.
OPTION_DESCRIPTIONS = {
    "Academic": "A university, college, school, or academic research institution.",
    "Business": "A for-profit business or business-led association.",
    "Coalition": "A network, alliance, or coalition of multiple organizations or groups.",
    "Municipal / Government-affiliated": "A public agency or organization formally affiliated with government.",
    "Municipality": "A municipal government, or work directed specifically at municipal institutions when used as an audience or reach.",
    "Municipality": "A city, town, village, or other municipal government itself.",
    "Nonprofit / Grassroots": "A nonprofit, charity, community group, or grassroots organization.",
    "Businesses": "Programs or services primarily target businesses or employers.",
    "Residents": "Programs or services primarily target residents or the general public.",
    "Adaptation": "Primarily prepares for or reduces harm from climate impacts.",
    "Mitigation": "Primarily reduces greenhouse-gas emissions or their causes.",
    "Both": "Substantial evidence supports both choices represented by this question.",
    "Action": "Primarily implements programs, projects, services, or direct interventions.",
    "Advocacy": "Primarily influences policy, public opinion, or institutional decisions.",
    "Community Engagement": "Education, outreach, organizing, or community participation.",
    "Conservation": "Protection or restoration of land, water, habitat, forests, or natural resources.",
    "Advocacy/Policy": "Policy advocacy, campaigning, lobbying, or civic influence.",
    "Other": "Supported action that does not fit another action category.",
    "Energy Efficiency": "Energy conservation, clean energy, efficiency, or electrification.",
    "Environmental": "Broad environmental or climate work without a more specific listed focus.",
    "Food & Food Waste": "Food systems, agriculture, composting, or food-waste reduction.",
    "Green Economics": "Green jobs, sustainable business, finance, or economic transition.",
    "Transportation": "Transit, mobility, walking, cycling, or vehicle decarbonization.",
    "Waste Reduction": "Recycling, reuse, repair, zero waste, or material-waste reduction.",
    "Global": "Operates internationally or worldwide.",
    "Regional": "Operates across a multi-city, county, or sub-state region.",
    "State / National": "Operates statewide or nationally.",
    "Town / City": "Operates primarily within one town or city.",
    "Verified": "Explicit evidence says GCC or its authorized review process verified this record.",
    "Not Verified": "No explicit GCC verification evidence is present.",
    "Unknown": "The supplied evidence is insufficient to choose another option.",
}


def discovery_schema() -> dict:
    """Return the strict structured-output contract for website discovery."""
    return {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["found", "not_found", "ambiguous"]},
            "website_url": {"type": "string"},
            "summary": {"type": "string"},
            "evidence": {"type": "string"},
            "source_urls": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "rationale": {"type": "string"},
        },
        "required": [
            "status", "website_url", "summary", "evidence", "source_urls",
            "confidence", "rationale",
        ],
        "additionalProperties": False,
    }


def website_discovery_payload(properties: dict, model: str) -> dict:
    """Build a web-search request using the record's available identity signals.

    Address and EIN information help disambiguate similar organization names.
    The prompt excludes directories, social profiles, and category inference so
    this stage produces evidence rather than silently classifying the record.
    """
    identity = {
        "name": properties.get("name", ""),
        "address": properties.get("address", ""),
        "city": properties.get("city", ""),
        "state": properties.get("state", ""),
        "postal_code": properties.get("postal_code", ""),
        "ein": properties.get("source_id", ""),
        "ntee_label": properties.get("ntee_label", ""),
    }
    return {
        "model": model,
        "store": False,
        "tools": [{"type": "web_search", "search_context_size": "medium"}],
        "instructions": (
            "Find the official website for the identified organization and collect factual "
            "information about its mission, programs, audience, activities, subject areas, "
            "and geographic reach. Match identity using name and location; do not choose a "
            "directory, social profile, news article, or a similarly named organization. "
            "Return found only when the identity match is supportable. Write a concise, neutral "
            "summary grounded in the sources. Put the relevant extracted facts in evidence and "
            "include every supporting URL. Do not infer GCC categories in this stage."
        ),
        "input": json.dumps(identity, ensure_ascii=False, separators=(",", ":")),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "organization_website_discovery",
                "strict": True,
                "schema": discovery_schema(),
            }
        },
    }


def contact_schema() -> dict:
    """Return the structured-output contract for OpenAI contact extraction."""
    return {
        "type": "object",
        "properties": {
            "email": {"type": "string"},
            "phone": {"type": "string"},
            "contact_page_url": {"type": "string"},
        },
        "required": ["email", "phone", "contact_page_url"],
        "additionalProperties": False,
    }


def contact_search_payload(properties: dict, website_url: str, model: str) -> dict:
    """Build an OpenAI web-search request to find public contact details.

    Used only when the deterministic crawler was blocked or unreachable.
    """
    identity = {
        "name": properties.get("name", ""),
        "city": properties.get("city", ""),
        "state": properties.get("state", ""),
        "website": website_url,
    }
    return {
        "model": model,
        "store": False,
        "tools": [{"type": "web_search", "search_context_size": "low"}],
        "instructions": (
            "Find the public organizational email address, phone number, and contact page URL "
            "for the identified nonprofit organization from its official website. "
            "Return only general organizational contacts such as info@, contact@, or office@. "
            "Do not return named staff personal addresses or direct personal phone numbers. "
            "Return empty strings for any field not confirmed on the official site."
        ),
        "input": json.dumps(identity, ensure_ascii=False, separators=(",", ":")),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "organization_contact_details",
                "strict": True,
                "schema": contact_schema(),
            }
        },
    }


def valid_http_url(value: object) -> bool:
    """Return whether a value is an absolute HTTP(S) URL with a host."""
    try:
        parsed = urllib.parse.urlparse(str(value))
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def validate_discovery(result: dict) -> None:
    """Reject incomplete or unsafe website-discovery output before persistence."""
    if result.get("status") not in {"found", "not_found", "ambiguous"}:
        raise ValueError("Invalid website discovery status")
    if result.get("confidence") not in {"high", "medium", "low"}:
        raise ValueError("Invalid website discovery confidence")
    if result["status"] == "found":
        if not valid_http_url(result.get("website_url")):
            raise ValueError("A found website must have a valid HTTP(S) URL")
        if not str(result.get("summary", "")).strip():
            raise ValueError("A found website must include a summary")
        if not str(result.get("evidence", "")).strip():
            raise ValueError("A found website must include classification evidence")
        if not result.get("source_urls") or not all(valid_http_url(url) for url in result["source_urls"]):
            raise ValueError("A found website must include valid evidence URLs")


def jev_state(properties: dict, discovery: dict) -> dict:
    """Create the evidence state shared by all Jev classification questions.

    ``verification_evidence`` remains empty by design: finding an official site
    does not mean that GCC has reviewed or verified the organization.
    """
    return {
        "organization": {
            "name": properties.get("name", ""),
            "city": properties.get("city", ""),
            "state": properties.get("state", ""),
            "irs_category": properties.get("irs_category", ""),
            "official_website": discovery.get("website_url", ""),
        },
        "website_summary": discovery.get("summary", ""),
        "website_evidence": discovery.get("evidence", ""),
        "evidence_urls": discovery.get("source_urls", []),
        "verification_evidence": "",
    }


def jev_questions() -> dict:
    """Build all schema questions so Jev classifies a record in one API call."""
    questions = {}
    for field in CLASSIFICATION_FIELDS:
        questions[field] = {
            "type": "choice",
            "instructions": FIELD_INSTRUCTIONS[field],
            "criteria": {
                option: OPTION_DESCRIPTIONS[option]
                for option in CATEGORY_OPTIONS[field]
            },
        }
    return questions


def jev_request_payload(properties: dict, discovery: dict, model: str) -> dict:
    """Assemble an OpenRouter Decisions request for the configured Jev model."""
    return {
        "model": model,
        "state": jev_state(properties, discovery),
        "questions": jev_questions(),
    }


def extract_openai_output(response: dict) -> dict:
    """Extract and decode the structured JSON result from an OpenAI response."""
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return json.loads(content["text"])
            if content.get("type") == "refusal":
                raise RuntimeError(f"Website-search model refused: {content.get('refusal', '')}")
    raise RuntimeError("OpenAI website-search response did not contain output text")


def call_openai(payload: dict, api_key: str, endpoint: str, retries: int = 3) -> dict:
    """Call website discovery with exponential backoff for transient failures."""
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "GCC-Climate-Organization-Map/0.1",
        },
    )
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return extract_openai_output(json.loads(response.read().decode("utf-8")))
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            if attempt == retries or error.code < 500 and error.code != 429:
                raise RuntimeError(f"OpenAI website-search API error {error.code}: {details}") from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            if attempt == retries:
                raise RuntimeError("OpenAI website-search request failed") from error
        time.sleep(2**attempt)
    raise RuntimeError("Unreachable OpenAI retry state")


def post_json(
    payload: dict,
    api_key: str,
    endpoint: str,
    retries: int = 3,
) -> dict:
    """Post a Jev decision request to OpenRouter with bounded retries."""
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/gcc-climate-org-mapping",
            "X-Title": "GCC Climate Org Mapping",
            "User-Agent": "GCC-Climate-Organization-Map/0.1",
        },
    )
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            if attempt == retries or error.code < 500 and error.code != 429:
                raise RuntimeError(f"OpenRouter Jev API error {error.code}: {details}") from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            if attempt == retries:
                raise RuntimeError("OpenRouter Jev request failed") from error
        time.sleep(2**attempt)
    raise RuntimeError("Unreachable OpenRouter retry state")


def validate_jev_response(response: dict) -> None:
    """Ensure Jev answered every question with an allowed, scored choice."""
    answers = response.get("answers")
    if not isinstance(answers, dict):
        raise ValueError("Jev response does not contain answers")
    for field in CLASSIFICATION_FIELDS:
        answer = answers.get(field, {})
        choice = answer.get("choice")
        if answer.get("type") != "choice" or choice not in CATEGORY_OPTIONS[field]:
            raise ValueError(f"Invalid Jev answer for {field}: {choice!r}")
        probabilities = answer.get("probabilities")
        if not isinstance(probabilities, dict) or choice not in probabilities:
            raise ValueError(f"Jev answer for {field} lacks probabilities")


def apply_enrichment(properties: dict, discovery: dict, jev_response: dict, requested_model: str) -> None:
    """Merge validated research and classifications into one feature's fields."""
    validate_discovery(discovery)
    validate_jev_response(jev_response)
    properties["website_url"] = discovery["website_url"]
    properties["summary"] = discovery["summary"]
    properties["website_discovery_status"] = discovery["status"]
    properties["website_discovery_confidence"] = discovery["confidence"]
    properties["website_evidence_urls"] = discovery["source_urls"]

    # Store both the selected values and model diagnostics. The UI uses only the
    # values, while confidence/probability fields support later review and audit.
    confidences = {}
    probabilities = {}
    for field in CLASSIFICATION_FIELDS:
        answer = jev_response["answers"][field]
        value = answer["choice"]
        properties[field] = value
        properties[GCC_FIELD_BY_SCHEMA_FIELD[field]] = value
        confidences[field] = answer.get("confidence")
        probabilities[field] = answer.get("probabilities", {})

    properties["validated"] = properties["status"] == "Verified"
    properties["jev_classification_status"] = "classified"
    properties["jev_requested_model"] = requested_model
    properties["jev_model"] = jev_response.get("model", requested_model)
    properties["jev_provider"] = jev_response.get("provider", "OpenRouter")
    properties["jev_request_id"] = jev_response.get("id", "")
    properties["jev_questions_version"] = JEV_QUESTIONS_VERSION
    properties["jev_confidences"] = confidences
    properties["jev_probabilities"] = probabilities
    properties["jev_classified_at"] = datetime.now(timezone.utc).isoformat()


def cache_key(material: dict) -> str:
    """Hash canonical request material into a stable content-addressed key."""
    encoded = json.dumps(material, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_cache(path: Path) -> dict[str, dict]:
    """Load an append-only JSON Lines cache, with later duplicates winning."""
    if not path.exists():
        return {}
    cache = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            cache[item["cache_key"]] = item["result"]
    return cache


def append_cache(path: Path, key: str, result: dict) -> None:
    """Append one API result immediately so completed work survives interruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps({"cache_key": key, "result": result}, ensure_ascii=False, separators=(",", ":")) + "\n")


def identity_material(properties: dict) -> dict:
    """Select identity fields that invalidate discovery when their values change."""
    return {
        field: properties.get(field, "")
        for field in ("id", "name", "address", "city", "state", "postal_code", "source_id")
    }


def enrichment_is_complete(properties: dict, search_model: str, jev_model: str) -> bool:
    """Return whether current version/model settings already processed a record.

    Definitive not-found and ambiguous discovery results count as complete to
    avoid paying for the same unsuccessful search on every run. Found sites also
    require a current Jev result before the feature is considered complete.
    """
    if properties.get("website_discovery_version") != DISCOVERY_VERSION:
        return False
    if properties.get("website_discovery_model") != search_model:
        return False
    status = properties.get("website_discovery_status")
    if status in {"not_found", "ambiguous"}:
        return True
    return (
        status == "found"
        and properties.get("jev_classification_status") == "classified"
        and properties.get("jev_requested_model") == jev_model
        and properties.get("jev_questions_version") == JEV_QUESTIONS_VERSION
    )


def write_geojson(path: Path, payload: dict) -> None:
    """Atomically write GeoJSON so a terminated process cannot truncate output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")
    temporary.replace(path)


def enrich_geojson(
    input_path: Path,
    output_path: Path,
    openai_key: str,
    openrouter_key: str,
    discovery_cache_path: Path,
    jev_cache_path: Path,
    search_model: str = DEFAULT_SEARCH_MODEL,
    jev_model: str = DEFAULT_JEV_MODEL,
    openai_endpoint: str = OPENAI_ENDPOINT,
    jev_endpoint: str = OPENROUTER_DECISIONS_ENDPOINT,
    limit: int | None = None,
    discovery_caller: Callable[[dict, str, str], dict] | None = None,
    jev_caller: Callable[[dict, str, str], dict] | None = None,
    contact_caller: Callable[[dict, str, str], dict] | None = None,
    fail_on_error: bool = False,
    brave_key: str | None = None,
) -> dict[str, int]:
    """Research and classify only records not already complete.

    Caller injection keeps network behavior testable. ``limit`` is applied after
    existing records are removed, so it always represents new work. Errors are
    recorded on individual features unless ``fail_on_error`` requests immediate
    termination. Summary counts are returned and embedded in dataset metadata.
    """
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    features = payload.get("features", [])
    discovery_cache = load_cache(discovery_cache_path)
    jev_cache = load_cache(jev_cache_path)
    search = discovery_caller or (lambda body, key, endpoint: call_openai(body, key, endpoint))
    decide = jev_caller or (lambda body, key, endpoint: post_json(body, key, endpoint))
    contact_search = contact_caller or search
    # Completion checks happen before limiting, which makes small resumable runs
    # advance through the dataset instead of revisiting its first records.
    pending = [
        feature
        for feature in features
        if not enrichment_is_complete(feature.get("properties", {}), search_model, jev_model)
    ]
    selected = pending if limit is None else pending[:limit]
    stats = {
        "processed": 0,
        "websites_found": 0,
        "classified": 0,
        "failed": 0,
        "skipped_existing": len(features) - len(pending),
        "remaining": 0,
    }

    for feature in selected:
        properties = feature["properties"]
        stats["processed"] += 1
        discovery_key = cache_key({
            "version": DISCOVERY_VERSION,
            "model": search_model,
            "identity": identity_material(properties),
        })
        try:
            # Cache keys include prompt version, model, and record identity; a
            # change to any of them forces fresh evidence collection.
            discovery = discovery_cache.get(discovery_key)
            if discovery is None:
                # Brave Search is the cost-effective primary path; OpenAI is the
                # fallback when Brave returns None (no confident match found).
                if brave_key:
                    discovery = brave_discover(properties, brave_key)
                if discovery is None:
                    discovery = search(website_discovery_payload(properties, search_model), openai_key, openai_endpoint)
                validate_discovery(discovery)
                discovery_cache[discovery_key] = discovery
                append_cache(discovery_cache_path, discovery_key, discovery)
            else:
                validate_discovery(discovery)

            properties["website_discovery_status"] = discovery["status"]
            properties["website_discovery_confidence"] = discovery["confidence"]
            properties["website_discovery_version"] = DISCOVERY_VERSION
            properties["website_discovery_model"] = search_model
            if discovery["status"] != "found":
                continue
            stats["websites_found"] += 1
            # Save useful research immediately, even if Jev subsequently fails.
            properties["website_url"] = discovery["website_url"]
            properties["summary"] = discovery["summary"]
            properties["website_evidence_urls"] = discovery["source_urls"]
            # Crawl the accepted site for contact details.
            # When the crawler was blocked or the site unreachable, fall back to
            # OpenAI web search, which may surface contacts from its cached index.
            contacts = crawl_for_contacts(discovery["website_url"])
            if not contacts["accessible"]:
                try:
                    raw = contact_search(
                        contact_search_payload(properties, discovery["website_url"], search_model),
                        openai_key, openai_endpoint,
                    )
                    contacts = {k: str(raw.get(k, "")) for k in ("email", "phone", "contact_page_url")}
                except Exception:
                    contacts = {"email": "", "phone": "", "contact_page_url": ""}
            properties["email"] = contacts["email"]
            properties["phone"] = contacts["phone"]
            if contacts.get("contact_page_url"):
                properties["contact_page_url"] = contacts["contact_page_url"]

            jev_key = cache_key({
                "version": JEV_QUESTIONS_VERSION,
                "model": jev_model,
                "state": jev_state(properties, discovery),
            })
            # Jev's cache depends on the complete evidence state and question
            # version, preventing stale choices after research or schema changes.
            jev_response = jev_cache.get(jev_key)
            if jev_response is None:
                jev_response = decide(jev_request_payload(properties, discovery, jev_model), openrouter_key, jev_endpoint)
                validate_jev_response(jev_response)
                jev_cache[jev_key] = jev_response
                append_cache(jev_cache_path, jev_key, jev_response)
            apply_enrichment(properties, discovery, jev_response, jev_model)
            stats["classified"] += 1
        except Exception as error:
            stats["failed"] += 1
            properties["jev_classification_status"] = "error"
            properties["enrichment_error"] = str(error)
            if fail_on_error:
                raise

    # Failed selected records remain pending, while successful selections do not.
    stats["remaining"] = len(pending) - len(selected) + stats["failed"]

    payload.setdefault("metadata", {})["enrichment"] = {
        **stats,
        "website_search_model": search_model,
        "classification_model": jev_model,
        "classification_provider": "OpenRouter Decisions API",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    write_geojson(output_path, payload)
    return stats


def parse_args() -> argparse.Namespace:
    """Parse enrichment settings, model overrides, caches, and batch limits."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("app/data/organizations.geojson"))
    parser.add_argument("--output", type=Path, default=Path("app/data/organizations.geojson"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--search-model", default=os.environ.get("OPENAI_MODEL", DEFAULT_SEARCH_MODEL))
    parser.add_argument("--jev-model", default=os.environ.get("JEV_MODEL", DEFAULT_JEV_MODEL))
    parser.add_argument("--openai-endpoint", default=os.environ.get("OPENAI_BASE_URL", OPENAI_ENDPOINT))
    parser.add_argument("--jev-endpoint", default=os.environ.get("JEV_BASE_URL", OPENROUTER_DECISIONS_ENDPOINT))
    parser.add_argument("--openai-api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--openrouter-api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--brave-api-key-env", default="BRAVE_API_KEY")
    parser.add_argument("--discovery-cache", type=Path, default=Path("Data/Website Enrichment/discovery-cache.jsonl"))
    parser.add_argument("--jev-cache", type=Path, default=Path("Data/Jev Classification/classification-cache.jsonl"))
    parser.add_argument("--fail-on-error", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    return args


def main() -> None:
    """Load local configuration, validate secrets, and run enrichment."""
    load_environment(PROJECT_ROOT / ".env")
    args = parse_args()
    openai_key = os.environ.get(args.openai_api_key_env)
    openrouter_key = os.environ.get(args.openrouter_api_key_env)
    brave_key = os.environ.get(args.brave_api_key_env)
    if not openai_key:
        raise SystemExit(f"Missing API key environment variable: {args.openai_api_key_env}")
    if not openrouter_key:
        raise SystemExit(f"Missing API key environment variable: {args.openrouter_api_key_env}")
    stats = enrich_geojson(
        args.input, args.output, openai_key, openrouter_key,
        args.discovery_cache, args.jev_cache, args.search_model, args.jev_model,
        args.openai_endpoint, args.jev_endpoint, args.limit,
        fail_on_error=args.fail_on_error, brave_key=brave_key or None,
    )
    print(f"Organizations processed: {stats['processed']:,}")
    print(f"Official websites found: {stats['websites_found']:,}")
    print(f"Organizations classified by Jev: {stats['classified']:,}")
    print(f"Errors: {stats['failed']:,}")


if __name__ == "__main__":
    main()
