#!/usr/bin/env python3
"""Enrich organizations through website research and Jev classification.

The workflow deliberately separates two different responsibilities. A web-search
model (via OpenRouter's web plugin) finds the official organization website and
returns source-grounded facts;
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
    from .website_discovery import (
        BraveKeyError, brave_candidates, brave_discover, brave_query, clean_text, crawl_for_contacts, discovery_from_result,
        email_matches_site, facebook_page, is_directory, normalize_phone, site_domain, tidy_summary,
    )
    from . import api_log
    from . import supabase_store as store
    from .survey_verifications import is_survey_verified
except ImportError:  # Allows direct execution from the repository root.
    from survey_verifications import is_survey_verified  # type: ignore
    from normalize_external_data_without_llm import CATEGORY_OPTIONS  # type: ignore
    from load_environment import load_environment  # type: ignore
    from website_discovery import (  # type: ignore
        BraveKeyError, brave_candidates, brave_discover, brave_query, clean_text, crawl_for_contacts, discovery_from_result,
        email_matches_site, facebook_page, is_directory, normalize_phone, site_domain, tidy_summary,
    )
    import api_log  # type: ignore
    import supabase_store as store  # type: ignore


OPENROUTER_CHAT_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_DECISIONS_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_SEARCH_MODEL = "openai/gpt-5.4-nano"
DEFAULT_JEV_MODEL = "typesafe/jev-1.13"
DISCOVERY_VERSION = "gcc-website-discovery-v8"
JEV_QUESTIONS_VERSION = "gcc-jev-classification-v2"
# Bumping this re-checks contacts only: discovery and Jev results stay cached.
CONTACT_VERSION = "gcc-contacts-v3"
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
    "audience_focus": "Choose the audience, or the combination of audiences, that the evidence explicitly shows the organization serves.",
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
    "Municipality": "A city, town, or village government, or a public agency formally part of government; as an audience, work directed at municipal institutions.",
    "Tribal/Indigenous": "A tribal government, tribal nation, or Indigenous-led organization.",
    "Committee": "A town or city committee, commission, or volunteer board.",
    "Nonprofit / Grassroots": "A nonprofit, charity, community group, or grassroots organization.",
    "Businesses": "Programs or services primarily target businesses or employers.",
    "Residents": "Programs or services primarily target residents or the general public.",
    "Residents / Municipality": "Programs substantially serve both residents and municipal institutions.",
    "Residents / Businesses": "Programs substantially serve both residents and businesses.",
    "Residents / Municipality / Businesses": "Programs substantially serve residents, municipal institutions, and businesses.",
    "Municipality / Businesses": "Programs substantially serve both municipal institutions and businesses.",
    "Adaptation": "Primarily prepares for or reduces harm from climate impacts.",
    "Mitigation": "Primarily reduces greenhouse-gas emissions or their causes.",
    "Both": "Substantial evidence supports both choices represented by this question.",
    "Action": "Primarily implements programs, projects, services, or direct interventions.",
    "Advocacy": "Primarily influences policy, public opinion, or institutional decisions.",
    "Community Engagement": "Education, outreach, organizing, or community participation.",
    "Conservation": "Protection or restoration of land, water, habitat, forests, or natural resources.",
    "Advocacy/Policy": "Policy advocacy, campaigning, lobbying, or civic influence.",
    "Other": "Supported action that does not fit another action category.",
    # Climate descriptions follow the GCC schema's own wording.
    "Energy Efficiency": "Heating/cooling, weatherization, solar.",
    "Environmental": "Pollinators, native plants, clean air/water; also land, water, habitat, and forest conservation.",
    "Food & Food Waste": "Composting, food choices, local farming.",
    "Green Economics": "Buying local, supporting sustainable businesses, green investing.",
    "Transportation": "Public options, electric vehicles.",
    "Waste Reduction": "Reuse, repair, repurpose, recycle, refuse.",
    "Regional": "Operates across a multi-city, county, or sub-state region.",
    "State / National": "Operates statewide, nationally, or internationally.",
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


def web_search_payload(model: str, instructions: str, identity: dict, schema_name: str, schema: dict, context_size: str) -> dict:
    """Build an OpenRouter chat request with live web search and strict JSON output."""
    return {
        "model": model,
        "plugins": [{"id": "web"}],
        "web_search_options": {"search_context_size": context_size},
        # Asks OpenRouter to return token counts and dollar cost in the response.
        "usage": {"include": True},
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps(identity, ensure_ascii=False, separators=(",", ":"))},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        },
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
    return web_search_payload(
        model,
        (
            "Find the official website for the identified organization and collect factual "
            "information about its mission, programs, audience, activities, subject areas, "
            "and geographic reach. Match identity using name and location; do not choose a "
            "directory, social profile, news article, or a similarly named organization. "
            "Return found only when the identity match is supportable. "
            "The summary is shown to the public in a map popup: write one to three plain sentences "
            "describing the organization itself (what it does, where, and for whom), grounded in "
            "the sources. Do not mention websites, searching, matching, EINs, IRS records, "
            "addresses, or how the organization was identified; put identity reasoning in "
            "rationale instead. Put the relevant extracted facts in evidence and include every "
            "supporting URL. Do not infer GCC categories in this stage."
        ),
        identity,
        "organization_website_discovery",
        discovery_schema(),
        "medium",
    )


PICKER_PROMPT_VERSION = "gcc-brave-pick-v1"
_PICKER_INSTRUCTIONS = (
    "You are given a nonprofit organization's identity and numbered web search results. "
    "Return the index of the result that is the organization's own official website: a site "
    "the organization runs itself, normally at its own domain. Choose its page on a parent "
    "organization's site only if it clearly has no domain of its own. Never choose a "
    "directory or nonprofit database, a news article, a government page, a funder or grant "
    "listing, a social media page, or a different organization with a similar name. If no "
    "result is clearly its official website, return index -1. Give a one-sentence reason."
)


def brave_pick_payload(properties: dict, candidates: list[dict], model: str) -> dict:
    """Ask a cheap model to choose the official site among Brave's results (no web search)."""
    question = {
        "organization": {k: properties.get(k, "") for k in ("name", "city", "state", "ntee_label")},
        "results": [
            {"index": i, "url": r["url"], "title": clean_text(r.get("title", "")),
             "snippet": clean_text(r.get("description", ""))}
            for i, r in enumerate(candidates)
        ],
    }
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": _PICKER_INSTRUCTIONS},
            {"role": "user", "content": json.dumps(question, ensure_ascii=False)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "official_site_pick",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"index": {"type": "integer"}, "reason": {"type": "string"}},
                    "required": ["index", "reason"],
                    "additionalProperties": False,
                },
            },
        },
        "usage": {"include": True},
    }


def call_brave_pick(payload: dict, api_key: str, endpoint: str) -> dict:
    return extract_chat_output(post_json(payload, api_key, endpoint, purpose="brave_pick"))


def pick_from_brave(
    properties: dict, model: str, api_key: str, endpoint: str,
    cache: dict, caller: Callable[[dict, str, str], dict] | None = None,
) -> dict | None:
    """Return a discovery built from the Brave result the model calls official, or None.

    Costs one small chat call (~$0.0005 with gpt-5.4-nano) instead of a ~$0.012
    web search, and only runs when Brave's own rules matched nothing.
    """
    candidates = brave_candidates(properties)
    if not candidates:
        return None
    key = cache_key({
        "prompt": PICKER_PROMPT_VERSION, "model": model,
        "query": brave_query(properties), "urls": [r["url"] for r in candidates],
    })
    answer = cache.get(key)
    if answer is None:
        answer = (caller or call_brave_pick)(brave_pick_payload(properties, candidates, model), api_key, endpoint)
        cache[key] = answer
        store.append_cache("picker", key, answer)
    index = answer.get("index", -1)
    if not isinstance(index, int) or not 0 <= index < len(candidates):
        api_log.decision("brave_pick_none", reason=str(answer.get("reason", ""))[:300], candidates=len(candidates))
        return None
    return discovery_from_result(
        properties, candidates[index], confidence="medium",
        rationale=f"Brave Search result picked by {model}: {str(answer.get('reason', ''))[:200]}",
        log_kind="brave_picked",
    )


def contact_schema() -> dict:
    """Return the structured-output contract for web-search contact extraction."""
    return {
        "type": "object",
        "properties": {
            "email": {"type": "string"},
            "phone": {"type": "string"},
            "phone_source_url": {"type": "string"},
            "contact_page_url": {"type": "string"},
        },
        "required": ["email", "phone", "phone_source_url", "contact_page_url"],
        "additionalProperties": False,
    }


def contact_search_payload(properties: dict, website_url: str, model: str) -> dict:
    """Build a web-search request to find public contact details.

    Used only when the deterministic crawler was blocked or unreachable.
    """
    identity = {
        "name": properties.get("name", ""),
        "city": properties.get("city", ""),
        "state": properties.get("state", ""),
        "website": website_url,
    }
    return web_search_payload(
        model,
        (
            "Find the public organizational email address, phone number, and contact page URL "
            "for the identified nonprofit organization from its official website. "
            "Return only general organizational contacts such as info@, contact@, or office@. "
            "Do not return named staff personal addresses or direct personal phone numbers. "
            "Set phone_source_url to the exact page on the official site where the phone number "
            "appears. Return empty strings for any field not confirmed on the official site; "
            "never return a number from a directory, a parent or partner organization, or a guess."
        ),
        identity,
        "organization_contact_details",
        contact_schema(),
        "low",
    )


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


def extract_chat_output(response: dict) -> dict:
    """Extract and decode the structured JSON result from a chat completion."""
    choices = response.get("choices") or []
    message = choices[0].get("message", {}) if choices else {}
    if message.get("refusal"):
        raise RuntimeError(f"Website-search model refused: {message['refusal']}")
    if not message.get("content"):
        raise RuntimeError("Website-search response did not contain output text")
    return json.loads(message["content"])


def call_web_search(payload: dict, api_key: str, endpoint: str) -> dict:
    """Run a web-search chat request through OpenRouter and decode its JSON."""
    purpose = payload["response_format"]["json_schema"]["name"].removeprefix("organization_")
    return extract_chat_output(post_json(payload, api_key, endpoint, purpose=f"web_search_{purpose}"))


def post_json(
    payload: dict,
    api_key: str,
    endpoint: str,
    retries: int = 3,
    purpose: str = "jev_classification",
) -> dict:
    """Post a JSON request to OpenRouter with bounded retries."""
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
            return json.loads(api_log.send(request, "openrouter", purpose, timeout=180).decode("utf-8"))
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            if attempt == retries or error.code < 500 and error.code != 429:
                raise RuntimeError(f"OpenRouter API error {error.code}: {details}") from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            if attempt == retries:
                raise RuntimeError("OpenRouter request failed") from error
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

    # Keep the IRS-derived values Jev replaces, once, so a later run that
    # rejects this record's website can put them back.
    properties.setdefault("pre_enrichment_categories", {
        key: properties.get(key)
        for field in CLASSIFICATION_FIELDS
        for key in (field, GCC_FIELD_BY_SCHEMA_FIELD[field])
    } | {"validated": properties.get("validated", False)})

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


_JEV_FIELDS = (
    "jev_requested_model", "jev_model", "jev_provider", "jev_request_id", "jev_questions_version",
    "jev_confidences", "jev_probabilities", "jev_classified_at",
)


def clear_research(properties: dict) -> None:
    """Remove website, summary, contacts and Jev categories left by an earlier run.

    Categories go back to their IRS-derived values: Jev chose the old ones from
    the evidence of a website this run rejected.
    """
    # The base schema always carries these as empty strings; the others are enrichment-only.
    for field in ("website_url", "summary", "email", "phone"):
        properties[field] = ""
    for field in ("contact_page_url", "website_evidence_urls", "facebook_url", *_JEV_FIELDS):
        properties.pop(field, None)
    properties.update(properties.pop("pre_enrichment_categories", {}))
    if properties.get("jev_classification_status") == "classified":
        properties["jev_classification_status"] = "not_classified"


def cache_key(material: dict) -> str:
    """Hash canonical request material into a stable content-addressed key."""
    encoded = json.dumps(material, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


WEBSEARCH_PROMPT_VERSION = "gcc-websearch-v2"  # bump when website_discovery_payload's wording changes


def websearch_cache_key(properties: dict, search_model: str) -> str:
    return cache_key({"prompt": WEBSEARCH_PROMPT_VERSION, "model": search_model, "identity": identity_material(properties)})


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
    if status == "found" and is_survey_verified(properties):
        # The organization's own survey answers stand in for Jev's categories.
        return properties.get("contact_version") == CONTACT_VERSION
    return (
        status == "found"
        and properties.get("jev_classification_status") == "classified"
        and properties.get("jev_requested_model") == jev_model
        and properties.get("jev_questions_version") == JEV_QUESTIONS_VERSION
        and properties.get("contact_version") == CONTACT_VERSION
    )


def enrich_payload(
    payload: dict,
    openrouter_key: str,
    search_model: str = DEFAULT_SEARCH_MODEL,
    jev_model: str = DEFAULT_JEV_MODEL,
    search_endpoint: str = OPENROUTER_CHAT_ENDPOINT,
    jev_endpoint: str = OPENROUTER_DECISIONS_ENDPOINT,
    limit: int | None = None,
    discovery_caller: Callable[[dict, str, str], dict] | None = None,
    jev_caller: Callable[[dict, str, str], dict] | None = None,
    contact_caller: Callable[[dict, str, str], dict] | None = None,
    picker_caller: Callable[[dict, str, str], dict] | None = None,
    fail_on_error: bool = False,
    brave_key: str | None = None,
    state: str | None = None,
    contact_fallback: bool = False,
) -> dict[str, int]:
    """Research and classify only records not already complete.

    Caller injection keeps network behavior testable. ``limit`` is applied after
    existing records are removed, so it always represents new work. Errors are
    recorded on individual features unless ``fail_on_error`` requests immediate
    termination. Summary counts are returned; the caller saves ``payload``.
    """
    features = payload.get("features", [])
    discovery_cache = store.load_cache("discovery")
    contact_cache = store.load_cache("contact")
    # Paid web-search answers, kept apart from the discovery cache so that a
    # discovery-rule change re-scores Brave results without re-paying these.
    websearch_cache = store.load_cache("websearch")
    picker_cache = store.load_cache("picker")
    jev_cache = store.load_cache("jev")
    search = discovery_caller or call_web_search
    decide = jev_caller or (lambda body, key, endpoint: post_json(body, key, endpoint))
    contact_search = contact_caller or search
    # Completion checks happen before limiting, which makes small resumable runs
    # advance through the dataset instead of revisiting its first records.
    # GCC-survey records carry the organization's own answers; a paid search must
    # not replace or clear them.
    incomplete = [
        feature
        for feature in features
        if feature.get("properties", {}).get("source") != "GCC survey"
        and not enrichment_is_complete(feature.get("properties", {}), search_model, jev_model)
    ]
    pending = [
        feature for feature in incomplete
        if state is None or str(feature.get("properties", {}).get("state", "")).upper() == state.upper()
    ]
    selected = pending if limit is None else pending[:limit]
    stats = {
        "processed": 0,
        "websites_found": 0,
        "classified": 0,
        "failed": 0,
        "skipped_existing": len(features) - len(incomplete),
        "remaining": 0,
        "brave_matches": 0,
        "brave_picks": 0,
        "web_search_fallbacks": 0,
        "contact_fallbacks": 0,
        "facebook_pages": 0,
        "survey_answers_kept": 0,
    }
    brave_failure: BraveKeyError | None = None

    for feature in selected:
        properties = feature["properties"]
        stats["processed"] += 1
        api_log.record_context.set({"org_id": properties.get("id", ""), "org_name": properties.get("name", "")})
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
                # Brave Search is the cost-effective primary path; LLM web search
                # is the fallback when Brave returns None (no confident match found).
                route = ""
                if brave_key:
                    discovery = brave_discover(properties, brave_key)
                    route = "brave" if discovery else ""
                    if discovery is None:
                        # Brave already paid for the search: let the cheap model pick
                        # from its results before paying for a fresh web search.
                        discovery = pick_from_brave(
                            properties, search_model, openrouter_key, search_endpoint,
                            picker_cache, picker_caller,
                        )
                        route = "brave_pick" if discovery else ""
                if discovery is None:
                    api_log.decision(
                        "web_search_fallback", model=search_model,
                        reason="BRAVE_API_KEY not set" if not brave_key else "no Brave result is the official site",
                    )
                    search_key = websearch_cache_key(properties, search_model)
                    discovery = websearch_cache.get(search_key)
                    if discovery is None:
                        stats["web_search_fallbacks"] += 1
                        discovery = search(website_discovery_payload(properties, search_model), openrouter_key, search_endpoint)
                        websearch_cache[search_key] = discovery
                        store.append_cache("websearch", search_key, discovery)
                    else:
                        api_log.decision("web_search_cache_hit", reason="reused cached web-search answer; no API call")
                    discovery = {**discovery, "summary": tidy_summary(discovery.get("summary", ""))}
                    if discovery.get("status") == "found" and is_directory(discovery.get("website_url", "")):
                        api_log.decision("web_search_directory_rejected", url=discovery.get("website_url"),
                                         reason="fallback returned a directory page, not an official site")
                        discovery = {**discovery, "status": "ambiguous"}
                elif route == "brave":
                    stats["brave_matches"] += 1
                else:
                    stats["brave_picks"] += 1
                validate_discovery(discovery)
                discovery_cache[discovery_key] = discovery
                store.append_cache("discovery", discovery_key, discovery)
            else:
                api_log.decision("discovery_cache_hit", reason="reused cached discovery; no API call")
                validate_discovery(discovery)

            properties["website_discovery_source"] = (
                "brave_llm_pick" if str(discovery.get("rationale", "")).startswith("Brave Search result picked")
                else "brave" if str(discovery.get("rationale", "")).startswith("Brave Search") else "openrouter_web_search"
            )
            properties["website_discovery_status"] = discovery["status"]
            properties["website_discovery_confidence"] = discovery["confidence"]
            properties["website_discovery_version"] = DISCOVERY_VERSION
            properties["website_discovery_model"] = search_model
            if discovery["status"] != "found":
                # Drop research from earlier runs so a rejected site never lingers on the map.
                clear_research(properties)
                facebook = facebook_page(properties)
                if facebook:
                    properties["facebook_url"] = facebook
                    stats["facebook_pages"] += 1
                    api_log.decision("facebook_fallback", reason="no website; Facebook page from cached Brave results", url=facebook)
                continue
            properties.pop("facebook_url", None)
            stats["websites_found"] += 1
            # Contacts don't depend on the category questions, so a re-classification
            # run keeps current contacts for an unchanged site instead of re-crawling.
            contacts_current = (
                properties.get("contact_version") == CONTACT_VERSION
                and properties.get("website_url") == discovery["website_url"]
            )
            # Save useful research immediately, even if Jev subsequently fails.
            properties["website_url"] = discovery["website_url"]
            properties["summary"] = discovery["summary"]
            properties["website_evidence_urls"] = discovery["source_urls"]
            if contacts_current:
                api_log.decision("contacts_reused", reason="contacts already current for this website; no crawl")
            else:
                # Crawl the accepted site for contact details.
                # When the crawler was blocked or the site unreachable, fall back to
                # LLM web search, which may surface contacts from its search index.
                contacts = crawl_for_contacts(discovery["website_url"])
                if contacts["accessible"]:
                    api_log.decision(
                        "contacts_from_site", reason="crawled the official site",
                        found={k: bool(contacts.get(k)) for k in ("email", "phone", "contact_page_url")},
                    )
                elif not contact_fallback:
                    api_log.decision("contact_fallback_skipped", reason="site blocked; paid contact lookup is off (use --contact-fallback)")
                else:
                    contact_key = cache_key({"model": search_model, "website": discovery["website_url"], "schema": "v2"})
                    try:
                        raw = contact_cache.get(contact_key)
                        if raw is None:
                            api_log.decision("contact_fallback", reason="site blocked by robots.txt or unreachable", model=search_model)
                            stats["contact_fallbacks"] += 1
                            raw = contact_search(
                                contact_search_payload(properties, discovery["website_url"], search_model),
                                openrouter_key, search_endpoint,
                            )
                            contact_cache[contact_key] = raw
                            store.append_cache("contact", contact_key, raw)
                        else:
                            api_log.decision("contact_cache_hit", reason="reused cached contact lookup; no API call")
                        contacts = {k: str(raw.get(k, "")) for k in ("email", "phone", "contact_page_url")}
                        # The model may echo a directory's mailbox or Cloudflare's
                        # "[email protected]" placeholder; keep only the org's own.
                        site = discovery["website_url"]
                        if not email_matches_site(contacts["email"], site):
                            contacts["email"] = ""
                        if contacts["contact_page_url"] and site_domain(contacts["contact_page_url"]) != site_domain(site):
                            contacts["contact_page_url"] = ""
                        # A number counts only if the model cites a page on the org's own domain.
                        phone_source = str(raw.get("phone_source_url", ""))
                        if not phone_source or site_domain(phone_source) != site_domain(site):
                            contacts["phone"] = ""
                        contacts["phone"] = normalize_phone(contacts["phone"])
                        api_log.decision("contact_fallback_result", kept={k: bool(v) for k, v in contacts.items()})
                    except Exception as error:
                        api_log.decision("contact_fallback_failed", reason=str(error)[:300])
                        contacts = {"email": "", "phone": "", "contact_page_url": ""}
                properties["email"] = contacts["email"]
                properties["phone"] = contacts["phone"]
                properties["contact_version"] = CONTACT_VERSION
                if contacts.get("contact_page_url"):
                    properties["contact_page_url"] = contacts["contact_page_url"]

            if is_survey_verified(properties):
                api_log.decision("jev_skipped", reason="survey-verified: the organization's own survey answers are its categories")
                stats["survey_answers_kept"] += 1
                continue
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
                store.append_cache("jev", jev_key, jev_response)
            else:
                api_log.decision("jev_cache_hit", reason="reused cached classification; no API call")
            apply_enrichment(properties, discovery, jev_response, jev_model)
            stats["classified"] += 1
        except BraveKeyError as error:
            # Every later record would hit the same rejection and silently pay
            # for OpenRouter fallbacks, so stop after saving finished work.
            stats["processed"] -= 1
            brave_failure = error
            break
        except Exception as error:
            stats["failed"] += 1
            properties["jev_classification_status"] = "error"
            properties["enrichment_error"] = str(error)
            if fail_on_error:
                raise

    # Failed and unvisited records remain pending, while successful ones do not.
    stats["remaining"] = len(pending) - stats["processed"] + stats["failed"]

    if brave_failure:
        raise brave_failure
    return stats


def parse_args() -> argparse.Namespace:
    """Parse enrichment settings, model overrides, caches, and batch limits."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--state", help="Only enrich organizations in this two-letter state, e.g. MA")
    parser.add_argument(
        "--contact-fallback", action="store_true",
        help="Pay for an OpenRouter contact lookup (about 2 cents) when a site blocks the crawler; off by default",
    )
    parser.add_argument("--search-model", default=os.environ.get("SEARCH_MODEL", DEFAULT_SEARCH_MODEL))
    parser.add_argument("--jev-model", default=os.environ.get("JEV_MODEL", DEFAULT_JEV_MODEL))
    parser.add_argument("--search-endpoint", default=os.environ.get("SEARCH_BASE_URL", OPENROUTER_CHAT_ENDPOINT))
    parser.add_argument("--jev-endpoint", default=os.environ.get("JEV_BASE_URL", OPENROUTER_DECISIONS_ENDPOINT))
    parser.add_argument("--openrouter-api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--brave-api-key-env", default="BRAVE_API_KEY")
    parser.add_argument("--fail-on-error", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    return args


def main() -> None:
    """Load local configuration, validate secrets, and run enrichment."""
    load_environment(PROJECT_ROOT / ".env")
    args = parse_args()
    openrouter_key = os.environ.get(args.openrouter_api_key_env)
    brave_key = os.environ.get(args.brave_api_key_env)
    if not openrouter_key:
        raise SystemExit(f"Missing API key environment variable: {args.openrouter_api_key_env}")
    payload = store.load_payload()
    try:
        stats = enrich_payload(
            payload, openrouter_key, args.search_model, args.jev_model,
            args.search_endpoint, args.jev_endpoint, args.limit,
            fail_on_error=args.fail_on_error, brave_key=brave_key or None, state=args.state,
            contact_fallback=args.contact_fallback,
        )
    finally:
        # Finished records are saved even when a run stops early.
        print(f"Organizations saved to Supabase: {store.save_payload(payload):,}")
    print(f"Organizations processed: {stats['processed']:,}")
    print(f"Official websites found: {stats['websites_found']:,}")
    print(f"Organizations classified by Jev: {stats['classified']:,}")
    print(f"Websites found by Brave: {stats['brave_matches']:,}")
    print(f"OpenRouter web-search fallbacks: {stats['web_search_fallbacks']:,}")
    print(f"OpenRouter contact fallbacks: {stats['contact_fallbacks']:,}")
    print(f"Errors: {stats['failed']:,}")
    print("Full request log: Supabase table api_log")


if __name__ == "__main__":
    main()
