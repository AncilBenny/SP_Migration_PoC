"""Research-only, offline SharePoint page-family classifier.

No credentials, network calls, HTML scraping, or production extraction.
Input: a JSON object containing independently collected / approved evidence.
The caller MUST verify source validity. A public URL is not a page-type proof.

Usage:
    python -m research_spike.classify examples/route-evidence.synthetic.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ASSESSMENT_TYPES = {
    "WikiPage": ("classic-wiki", "classic-wiki"),
    "WebPartPage": ("classic-webpart", "classic-webpart"),
    "PublishingPage": ("classic-publishing", "classic-publishing"),
    "BlogPage": ("other", None),
    "ASPXPage": ("other", None),
    "DelveBlogPage": ("other", None),
}
FAMILIES = {
    "modern": "modern-graph",
    "classic-wiki": "classic-wiki",
    "classic-webpart": "classic-webpart",
    "classic-publishing": "classic-publishing",
}


def classify(evidence: dict[str, Any]) -> dict[str, Any]:
    """Return a conservative page-family route and the evidence behind it.

    The strength of a flag is determined by authenticated/source-verified data
    supplied by the caller, not guessed from paths or HTML markers.
    """
    findings: list[dict[str, str]] = []
    warnings: list[str] = []
    candidates: set[str] = set()

    deployment = evidence.get("deployment", "unknown")
    if deployment not in ("online", "server-2013", "server-2016",
                          "server-2019", "server-subscription", "unknown"):
        warnings.append("DEPLOYMENT_UNRECOGNIZED")
        deployment = "unknown"

    graph = evidence.get("graphSitePage")
    if isinstance(graph, dict) and graph.get("@odata.type", "").lower() == "#microsoft.graph.sitepage":
        candidates.add("modern")
        findings.append({"source": "graph-sitepage", "family": "modern",
                         "strength": "source-api"})
        if not isinstance(graph.get("canvasLayout"), dict):
            warnings.append("MODERN_CANVAS_ABSENT_VERIFY_HOMEPAGE")

    assessment = evidence.get("assessmentPageType")
    if assessment is not None:
        if evidence.get("assessmentCoverageVerified") is True:
            if assessment in ASSESSMENT_TYPES:
                family, _ = ASSESSMENT_TYPES[assessment]
                candidates.add(family)
                findings.append({"source": "verified-classic-assessment",
                                 "family": family, "strength": "assessment"})
            else:
                warnings.append("ASSESSMENT_TYPE_UNRECOGNIZED")
        else:
            warnings.append("ASSESSMENT_UNVERIFIED_IGNORED")

    if evidence.get("authenticatedFieldsVerified") is True:
        fields = evidence.get("fields")
        fields = fields if isinstance(fields, dict) else {}
        if fields.get("PublishingPageLayout"):
            candidates.add("classic-publishing")
            findings.append({"source": "publishing-layout-field",
                             "family": "classic-publishing", "strength": "field-structure"})
        elif fields.get("WikiField"):
            candidates.add("classic-wiki")
            findings.append({"source": "wiki-content-field",
                             "family": "classic-wiki", "strength": "field-structure"})
        elif evidence.get("classicZonesPresent") is True:
            candidates.add("classic-webpart")
            findings.append({"source": "classic-zone-manager",
                             "family": "classic-webpart", "strength": "field-structure"})
    elif evidence.get("fields") or evidence.get("classicZonesPresent"):
        warnings.append("UNVERIFIED_SOURCE_FIELDS_IGNORED")

    if len(candidates) > 1:
        return {"status": "needs-review", "pageFamily": "unknown", "adapter": None,
                "deployment": deployment, "evidence": findings,
                "warnings": warnings + ["CONFLICTING_SOURCE_EVIDENCE"]}

    if candidates:
        family = next(iter(candidates))
        if family == "other":
            return {"status": "needs-review", "pageFamily": family, "adapter": None,
                    "deployment": deployment, "evidence": findings,
                    "warnings": warnings + ["SPECIALIZED_PAGE_ADAPTER_REQUIRED"]}
        status = "confirmed" if any(
            f["strength"] in ("source-api", "assessment") for f in findings
        ) else "tentative"
        if status == "tentative":
            warnings.append("REVIEW_FIELD_ONLY_CLASSIFICATION")
        if family == "modern" and deployment.startswith("server-"):
            return {"status": "needs-review", "pageFamily": "unknown", "adapter": None,
                    "deployment": deployment, "evidence": findings,
                    "warnings": warnings + ["MODERN_GRAPH_ON_SERVER_DEPLOYMENT_CONFLICT"]}
        return {"status": status, "pageFamily": family, "adapter": FAMILIES[family],
                "deployment": deployment, "evidence": findings, "warnings": warnings}

    # A public site, HTML snapshot or .aspx URL never proves the SharePoint family.
    use_fallback = evidence.get("publicHtmlObserved") is True and (
        evidence.get("allowPublicHtmlFallback") is True
    )
    if evidence.get("url", "").lower().endswith(".aspx"):
        warnings.append("ASPX_URL_INSUFFICIENT")
    if use_fallback:
        warnings.append("PUBLIC_HTML_IS_A_RENDERED_SNAPSHOT_ONLY")
    return {"status": "unknown", "pageFamily": "unknown",
            "adapter": "public-dom" if use_fallback else None,
            "deployment": deployment, "evidence": findings,
            "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_json", type=Path)
    args = parser.parse_args()
    data = json.loads(args.evidence_json.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        parser.error("Evidence JSON root must be an object")
    result = classify(data)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["status"] == "needs-review" else 0


if __name__ == "__main__":
    raise SystemExit(main())
