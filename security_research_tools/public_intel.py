"""Public security intelligence and local research workspace tools."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
from typing import Any, Literal
import zipfile

from agency_swarm.tools import BaseTool
from dotenv import load_dotenv
from pydantic import Field, model_validator
import requests

from workspace_context import get_artifact_root, has_active_working_directory


_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_SECURITY_WORKSPACE = _REPO_ROOT / "research_workspace" / "security"
_SECURITY_WORKSPACE = _DEFAULT_SECURITY_WORKSPACE
_DEFAULT_TIMEOUT = 30


class LookupCVE(BaseTool):
    """
    Look up CVE records from the public NVD 2.0 API.

    Supports no-key use and will add the optional NVD_API_KEY environment variable
    when present. Use a CVE ID for precise lookup or a keyword search for discovery.
    """

    cve_id: str | None = Field(default=None, description="Specific CVE ID, for example CVE-2024-3094.")
    keyword: str | None = Field(default=None, description="Optional NVD keyword search phrase.")
    max_results: int = Field(default=5, ge=1, le=50, description="Maximum CVE records to return.")
    timeout_seconds: int = Field(default=_DEFAULT_TIMEOUT, ge=5, le=120, description="HTTP timeout in seconds.")

    @model_validator(mode="after")
    def _require_query(self) -> "LookupCVE":
        if not (self.cve_id or self.keyword):
            raise ValueError("Provide either cve_id or keyword.")
        return self

    def run(self) -> str:
        load_dotenv(override=True)
        params: dict[str, Any] = {"resultsPerPage": self.max_results}
        if self.cve_id:
            params["cveId"] = self.cve_id.strip().upper()
        if self.keyword:
            params["keywordSearch"] = self.keyword.strip()

        headers = {"User-Agent": "OpenSwarm security research tools"}
        api_key = os.getenv("NVD_API_KEY", "").strip()
        if api_key:
            headers["apiKey"] = api_key

        payload = _http_json(
            "https://services.nvd.nist.gov/rest/json/cves/2.0",
            params=params,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        records = [_summarize_nvd_vulnerability(item) for item in payload.get("vulnerabilities", [])]
        return _json(
            {
                "source": "NVD",
                "query": {"cve_id": self.cve_id, "keyword": self.keyword},
                "total_results": payload.get("totalResults"),
                "results": records[: self.max_results],
            }
        )


class LookupCISAKEV(BaseTool):
    """
    Look up CISA Known Exploited Vulnerabilities from the public KEV JSON feed.

    Filter by CVE ID, vendor, product, or keyword. This is useful for confirming
    known exploitation and remediation due dates.
    """

    cve_id: str | None = Field(default=None, description="Optional CVE ID filter.")
    vendor: str | None = Field(default=None, description="Optional vendor/project filter.")
    product: str | None = Field(default=None, description="Optional product filter.")
    keyword: str | None = Field(default=None, description="Optional keyword filter across KEV text fields.")
    max_results: int = Field(default=20, ge=1, le=200, description="Maximum KEV records to return.")
    timeout_seconds: int = Field(default=_DEFAULT_TIMEOUT, ge=5, le=120, description="HTTP timeout in seconds.")

    def run(self) -> str:
        payload = _http_json(
            "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
            timeout=self.timeout_seconds,
        )
        records = payload.get("vulnerabilities", [])
        filtered = [
            _summarize_kev_record(record)
            for record in records
            if _matches_filters(
                record,
                {
                    "cveID": self.cve_id,
                    "vendorProject": self.vendor,
                    "product": self.product,
                    "*": self.keyword,
                },
            )
        ]
        return _json(
            {
                "source": "CISA KEV",
                "catalog_version": payload.get("catalogVersion"),
                "date_released": payload.get("dateReleased"),
                "count": len(filtered),
                "results": filtered[: self.max_results],
            }
        )


class LookupEPSS(BaseTool):
    """
    Look up FIRST EPSS exploit probability scores for one or more CVEs.
    """

    cve_ids: list[str] = Field(..., min_length=1, max_length=100, description="CVE IDs to score.")
    date: str | None = Field(default=None, description="Optional EPSS score date in YYYY-MM-DD format.")
    timeout_seconds: int = Field(default=_DEFAULT_TIMEOUT, ge=5, le=120, description="HTTP timeout in seconds.")

    def run(self) -> str:
        params = {"cve": ",".join(cve.strip().upper() for cve in self.cve_ids if cve.strip())}
        if self.date:
            params["date"] = self.date
        payload = _http_json("https://api.first.org/data/v1/epss", params=params, timeout=self.timeout_seconds)
        return _json(
            {
                "source": "FIRST EPSS",
                "date": payload.get("date"),
                "count": payload.get("total"),
                "results": [
                    {
                        "cve": row.get("cve"),
                        "epss": _to_float(row.get("epss")),
                        "percentile": _to_float(row.get("percentile")),
                        "date": row.get("date"),
                    }
                    for row in payload.get("data", [])
                ],
            }
        )


class LookupMitreKnowledge(BaseTool):
    """
    Search public MITRE ATT&CK, CWE, or CAPEC knowledge bases.

    ATT&CK is read from the MITRE CTI STIX bundle. CWE and CAPEC are read from
    MITRE CSV ZIP exports. All sources are public and require no API key.
    """

    knowledge_base: Literal["attack", "cwe", "capec"] = Field(
        ..., description="Which MITRE corpus to search: attack, cwe, or capec."
    )
    query: str = Field(..., min_length=1, description="ID or text to search for.")
    max_results: int = Field(default=10, ge=1, le=50, description="Maximum records to return.")
    timeout_seconds: int = Field(default=_DEFAULT_TIMEOUT, ge=5, le=120, description="HTTP timeout in seconds.")

    def run(self) -> str:
        query = self.query.strip().lower()
        if self.knowledge_base == "attack":
            records = _search_attack(query, self.timeout_seconds)
        elif self.knowledge_base == "cwe":
            records = _search_mitre_csv_zip(
                "https://cwe.mitre.org/data/csv/1000.csv.zip",
                query,
                id_key="CWE-ID",
                timeout=self.timeout_seconds,
            )
        else:
            records = _search_mitre_csv_zip(
                "https://capec.mitre.org/data/csv/1000.csv.zip",
                query,
                id_key="ID",
                timeout=self.timeout_seconds,
            )
        return _json(
            {
                "source": f"MITRE {self.knowledge_base.upper()}",
                "query": self.query,
                "count": len(records),
                "results": records[: self.max_results],
            }
        )


class ManageSecurityResearchNote(BaseTool):
    """
    Read, list, write, or append Markdown notes under research_workspace/security.

    Paths are always relative to the security workspace and cannot escape it.
    """

    action: Literal["read", "list", "write", "append"] = Field(..., description="Note action.")
    path: str = Field(default="notes/default.md", description="Workspace-relative Markdown note path.")
    content: str | None = Field(default=None, description="Content for write or append actions.")

    def run(self) -> str:
        base = _ensure_workspace()
        target = _safe_workspace_path(self.path)
        if self.action == "list":
            notes_dir = target if target.exists() and target.is_dir() else base / "notes"
            files = [str(path.relative_to(base)) for path in sorted(notes_dir.rglob("*.md"))] if notes_dir.exists() else []
            return _json({"workspace": str(base), "notes": files})
        if self.action == "read":
            return _json({"path": str(target.relative_to(base)), "content": target.read_text(encoding="utf-8")})
        if self.content is None:
            raise ValueError("content is required for write and append actions.")
        target.parent.mkdir(parents=True, exist_ok=True)
        if self.action == "write":
            target.write_text(self.content, encoding="utf-8")
        else:
            with target.open("a", encoding="utf-8") as handle:
                handle.write(self.content)
        return _json({"path": str(target.relative_to(base)), "bytes": target.stat().st_size, "action": self.action})


class ManageSecurityResearchResource(BaseTool):
    """
    Add, list, or read source/resource records in a JSONL file under the security workspace.
    """

    action: Literal["add", "list", "read"] = Field(..., description="Resource action.")
    title: str | None = Field(default=None, description="Resource title for add action.")
    url: str | None = Field(default=None, description="Source URL for add action.")
    source_type: str = Field(default="web", description="Source type, such as advisory, blog, paper, or dataset.")
    summary: str | None = Field(default=None, description="Short source summary.")
    tags: list[str] = Field(default_factory=list, description="Tags for filtering and later synthesis.")
    path: str = Field(default="resources/resources.jsonl", description="Workspace-relative JSONL resource file.")

    def run(self) -> str:
        base = _ensure_workspace()
        target = _safe_workspace_path(self.path)
        if self.action == "add":
            if not (self.title and self.url):
                raise ValueError("title and url are required for add action.")
            target.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "title": self.title,
                "url": self.url,
                "source_type": self.source_type,
                "summary": self.summary or "",
                "tags": self.tags,
                "created_at": _utc_now(),
            }
            with target.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            return _json({"path": str(target.relative_to(base)), "record": record})
        records = _read_jsonl(target)
        return _json({"path": str(target.relative_to(base)), "count": len(records), "resources": records})


class UpdateSecurityResearchProgress(BaseTool):
    """
    Track project progress as JSON under research_workspace/security/progress.
    """

    action: Literal["set", "read", "list"] = Field(..., description="Progress action.")
    project: str = Field(default="default", description="Project slug.")
    task: str | None = Field(default=None, description="Task or milestone name for set action.")
    status: Literal["todo", "in_progress", "blocked", "done"] | None = Field(default=None, description="Task status.")
    details: str = Field(default="", description="Optional details or evidence.")
    next_steps: list[str] = Field(default_factory=list, description="Optional next steps.")

    def run(self) -> str:
        base = _ensure_workspace()
        progress_dir = base / "progress"
        progress_dir.mkdir(parents=True, exist_ok=True)
        if self.action == "list":
            files = [path.stem for path in sorted(progress_dir.glob("*.json"))]
            return _json({"projects": files})
        target = progress_dir / f"{_slug(self.project)}.json"
        if self.action == "read":
            return _json({"project": self.project, "progress": _read_json_file(target, default={"tasks": []})})
        if not (self.task and self.status):
            raise ValueError("task and status are required for set action.")
        data = _read_json_file(target, default={"project": self.project, "tasks": []})
        tasks = data.setdefault("tasks", [])
        existing = next((item for item in tasks if item.get("task") == self.task), None)
        update = {
            "task": self.task,
            "status": self.status,
            "details": self.details,
            "next_steps": self.next_steps,
            "updated_at": _utc_now(),
        }
        if existing:
            existing.update(update)
        else:
            tasks.append(update)
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return _json({"project": self.project, "progress": data})


class CreateSecurityResearchDeliverable(BaseTool):
    """
    Create a Markdown, HTML, or text deliverable under research_workspace/security/outputs.

    Use this for blog drafts, briefs, advisories, image prompts, and report source
    files that should stay portable and reviewable without native document tooling.
    """

    file_name: str = Field(..., min_length=1, description="Output filename, without path traversal.")
    content: str = Field(..., min_length=1, description="Full deliverable content.")
    format: Literal["markdown", "html", "text"] = Field(default="markdown", description="Output format.")
    project: str = Field(default="default", description="Project slug used as the output subdirectory.")

    def run(self) -> str:
        base = _ensure_workspace()
        extension = {"markdown": ".md", "html": ".html", "text": ".txt"}[self.format]
        clean_name = _slug(Path(self.file_name).stem)
        target = _safe_workspace_path(f"outputs/{_slug(self.project)}/{clean_name}{extension}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.content, encoding="utf-8")
        return _json(
            {
                "path": str(target.relative_to(base)),
                "format": self.format,
                "bytes": target.stat().st_size,
            }
        )


class LoadSecurityDesignLanguage(BaseTool):
    """
    Load a tracked design-language profile for security visuals and reports.
    """

    profile: str = Field(default="default", description="Design profile name. The default profile is built in.")

    def run(self) -> str:
        base = _ensure_workspace()
        profile_name = _slug(self.profile)
        target = base / "design_language.md" if profile_name == "default" else base / "templates" / f"{profile_name}.md"
        if not target.exists():
            raise FileNotFoundError(f"Design language profile not found: {target.relative_to(base)}")
        assets_dir = base / "design_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        assets = [
            str(path.relative_to(base))
            for path in sorted(assets_dir.rglob("*"))
            if path.is_file() and path.name != ".gitkeep"
        ]
        return _json(
            {
                "profile": profile_name,
                "path": str(target.relative_to(base)),
                "assets_dir": str(assets_dir.relative_to(base)),
                "assets": assets,
                "content": target.read_text(encoding="utf-8"),
            }
        )


def _http_json(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int) -> dict[str, Any]:
    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _http_bytes(url: str, *, timeout: int) -> bytes:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content


def _summarize_nvd_vulnerability(item: dict[str, Any]) -> dict[str, Any]:
    cve = item.get("cve", {})
    metrics = cve.get("metrics", {})
    cvss = _first_cvss(metrics)
    weaknesses = [
        desc.get("value")
        for weakness in cve.get("weaknesses", [])
        for desc in weakness.get("description", [])
        if desc.get("lang") == "en" and desc.get("value")
    ]
    return {
        "id": cve.get("id"),
        "published": cve.get("published"),
        "last_modified": cve.get("lastModified"),
        "status": cve.get("vulnStatus"),
        "description": _english_description(cve.get("descriptions", [])),
        "cvss": cvss,
        "weaknesses": weaknesses,
        "references": _nvd_reference_urls(cve.get("references", [])),
    }


def _first_cvss(metrics: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(key) or []
        if entries:
            data = entries[0].get("cvssData", {})
            return {
                "version": data.get("version"),
                "base_score": data.get("baseScore"),
                "base_severity": entries[0].get("baseSeverity"),
                "vector": data.get("vectorString"),
            }
    return None


def _english_description(descriptions: list[dict[str, Any]]) -> str:
    for item in descriptions:
        if item.get("lang") == "en":
            return item.get("value", "")
    return descriptions[0].get("value", "") if descriptions else ""


def _nvd_reference_urls(references: Any) -> list[str]:
    if isinstance(references, dict):
        references = references.get("referenceData", [])
    if not isinstance(references, list):
        return []
    return [ref.get("url") for ref in references if isinstance(ref, dict) and ref.get("url")]


def _summarize_kev_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "cve_id": record.get("cveID"),
        "vendor_project": record.get("vendorProject"),
        "product": record.get("product"),
        "vulnerability_name": record.get("vulnerabilityName"),
        "date_added": record.get("dateAdded"),
        "due_date": record.get("dueDate"),
        "known_ransomware_campaign_use": record.get("knownRansomwareCampaignUse"),
        "required_action": record.get("requiredAction"),
        "notes": record.get("notes"),
    }


def _matches_filters(record: dict[str, Any], filters: dict[str, str | None]) -> bool:
    for field, expected in filters.items():
        if not expected:
            continue
        needle = expected.strip().lower()
        if field == "*":
            haystack = " ".join(str(value) for value in record.values()).lower()
        else:
            haystack = str(record.get(field, "")).lower()
        if needle not in haystack:
            return False
    return True


def _search_attack(query: str, timeout: int) -> list[dict[str, Any]]:
    payload = _http_json(
        "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json",
        timeout=timeout,
    )
    results = []
    for item in payload.get("objects", []):
        if item.get("type") != "attack-pattern" or item.get("revoked") or item.get("x_mitre_deprecated"):
            continue
        attack_id = _external_id(item, "mitre-attack")
        text = " ".join([attack_id, item.get("name", ""), item.get("description", "")]).lower()
        if query not in text:
            continue
        results.append(
            {
                "id": attack_id,
                "name": item.get("name"),
                "description": item.get("description", ""),
                "tactics": [phase.get("phase_name") for phase in item.get("kill_chain_phases", [])],
                "url": _external_url(item, "mitre-attack"),
            }
        )
    return results


def _search_mitre_csv_zip(url: str, query: str, *, id_key: str, timeout: int) -> list[dict[str, Any]]:
    zipped = _http_bytes(url, timeout=timeout)
    with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
        csv_name = next((name for name in archive.namelist() if name.lower().endswith(".csv")), None)
        if not csv_name:
            raise ValueError(f"No CSV file found in MITRE ZIP export: {url}")
        with archive.open(csv_name) as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8-sig", newline="")
            reader = csv.DictReader(text)
            results = []
            for row in reader:
                haystack = " ".join(str(value) for value in row.values()).lower()
                mitre_id = row.get(id_key, "")
                if query not in haystack and query not in mitre_id.lower():
                    continue
                results.append(
                    {
                        "id": mitre_id,
                        "name": row.get("Name"),
                        "description": row.get("Description") or row.get("Extended Description") or "",
                        "status": row.get("Status"),
                    }
                )
            return results


def _external_id(item: dict[str, Any], source_name: str) -> str:
    for ref in item.get("external_references", []):
        if ref.get("source_name") == source_name:
            return ref.get("external_id", "")
    return ""


def _external_url(item: dict[str, Any], source_name: str) -> str:
    for ref in item.get("external_references", []):
        if ref.get("source_name") == source_name:
            return ref.get("url", "")
    return ""


def _ensure_workspace() -> Path:
    base = _security_workspace()
    for child in ("notes", "resources", "progress", "scratch"):
        (base / child).mkdir(parents=True, exist_ok=True)
    return base


def _security_workspace() -> Path:
    if _SECURITY_WORKSPACE != _DEFAULT_SECURITY_WORKSPACE:
        return _SECURITY_WORKSPACE
    if has_active_working_directory():
        return get_artifact_root() / "research_workspace" / "security"
    return _DEFAULT_SECURITY_WORKSPACE


def _safe_workspace_path(relative_path: str) -> Path:
    base = _ensure_workspace().resolve()
    candidate = (base / relative_path).resolve()
    if candidate == base or base not in candidate.parents:
        raise ValueError(f"Path escapes security research workspace: {relative_path}")
    return candidate


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _read_json_file(path: Path, *, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default.copy()
    return json.loads(path.read_text(encoding="utf-8"))


def _slug(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    return "-".join(part for part in slug.split("-") if part) or "default"


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
