import io
import json
import zipfile

import pytest

from security_research_tools import (
    CreateSecurityResearchDeliverable,
    LoadSecurityDesignLanguage,
    LookupCISAKEV,
    LookupCVE,
    LookupEPSS,
    LookupMitreKnowledge,
    ManageSecurityResearchNote,
    ManageSecurityResearchResource,
    UpdateSecurityResearchProgress,
)
import security_research_tools.public_intel as public_intel


class FakeResponse:
    def __init__(self, payload=None, content=b""):
        self._payload = payload
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_lookup_cve_summarizes_nvd_payload(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(
            {
                "totalResults": 1,
                "vulnerabilities": [
                    {
                        "cve": {
                            "id": "CVE-2024-0001",
                            "published": "2024-01-01T00:00:00.000",
                            "lastModified": "2024-01-02T00:00:00.000",
                            "vulnStatus": "Analyzed",
                            "descriptions": [{"lang": "en", "value": "Example vulnerability."}],
                            "metrics": {
                                "cvssMetricV31": [
                                    {
                                        "baseSeverity": "HIGH",
                                        "cvssData": {
                                            "version": "3.1",
                                            "baseScore": 8.8,
                                            "vectorString": "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H",
                                        },
                                    }
                                ]
                            },
                            "weaknesses": [{"description": [{"lang": "en", "value": "CWE-79"}]}],
                            "references": {"referenceData": [{"url": "https://example.test/advisory"}]},
                        }
                    }
                ],
            }
        )

    monkeypatch.setattr(public_intel.requests, "get", fake_get)
    result = json.loads(LookupCVE(cve_id="cve-2024-0001").run())

    assert calls[0][0].endswith("/rest/json/cves/2.0")
    assert calls[0][1]["params"]["cveId"] == "CVE-2024-0001"
    assert result["results"][0]["id"] == "CVE-2024-0001"
    assert result["results"][0]["cvss"]["base_severity"] == "HIGH"
    assert result["results"][0]["weaknesses"] == ["CWE-79"]


def test_lookup_cisa_kev_filters_records(monkeypatch):
    def fake_get(url, **kwargs):
        return FakeResponse(
            {
                "catalogVersion": "2026.05.01",
                "dateReleased": "2026-05-01",
                "vulnerabilities": [
                    {"cveID": "CVE-1", "vendorProject": "Acme", "product": "Widget", "vulnerabilityName": "Bug one"},
                    {"cveID": "CVE-2", "vendorProject": "Other", "product": "Thing", "vulnerabilityName": "Bug two"},
                ],
            }
        )

    monkeypatch.setattr(public_intel.requests, "get", fake_get)
    result = json.loads(LookupCISAKEV(vendor="acme").run())

    assert result["count"] == 1
    assert result["results"][0]["cve_id"] == "CVE-1"


def test_lookup_epss_parses_floats(monkeypatch):
    def fake_get(url, **kwargs):
        return FakeResponse(
            {
                "date": "2026-05-07",
                "total": 1,
                "data": [{"cve": "CVE-2024-0001", "epss": "0.12345", "percentile": "0.98765", "date": "2026-05-07"}],
            }
        )

    monkeypatch.setattr(public_intel.requests, "get", fake_get)
    result = json.loads(LookupEPSS(cve_ids=["CVE-2024-0001"]).run())

    assert result["results"][0]["epss"] == pytest.approx(0.12345)
    assert result["results"][0]["percentile"] == pytest.approx(0.98765)


def test_lookup_mitre_attack_search(monkeypatch):
    def fake_get(url, **kwargs):
        return FakeResponse(
            {
                "objects": [
                    {
                        "type": "attack-pattern",
                        "name": "Phishing",
                        "description": "Adversaries send phishing messages.",
                        "kill_chain_phases": [{"phase_name": "initial-access"}],
                        "external_references": [
                            {
                                "source_name": "mitre-attack",
                                "external_id": "T1566",
                                "url": "https://attack.mitre.org/techniques/T1566/",
                            }
                        ],
                    }
                ]
            }
        )

    monkeypatch.setattr(public_intel.requests, "get", fake_get)
    result = json.loads(LookupMitreKnowledge(knowledge_base="attack", query="T1566").run())

    assert result["results"][0]["id"] == "T1566"
    assert result["results"][0]["tactics"] == ["initial-access"]


def test_lookup_mitre_cwe_csv_zip(monkeypatch):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w") as archive:
        archive.writestr("1000.csv", "CWE-ID,Name,Description,Status\n79,Cross-site Scripting,Improper neutralization,Draft\n")

    def fake_get(url, **kwargs):
        return FakeResponse(content=zip_buffer.getvalue())

    monkeypatch.setattr(public_intel.requests, "get", fake_get)
    result = json.loads(LookupMitreKnowledge(knowledge_base="cwe", query="79").run())

    assert result["results"][0]["id"] == "79"
    assert result["results"][0]["name"] == "Cross-site Scripting"


def test_workspace_tools_use_safe_local_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(public_intel, "_SECURITY_WORKSPACE", tmp_path)

    note = ManageSecurityResearchNote(action="write", path="notes/case.md", content="# Case\n").run()
    assert json.loads(note)["path"] == "notes/case.md"
    assert json.loads(ManageSecurityResearchNote(action="read", path="notes/case.md").run())["content"] == "# Case\n"

    resource = ManageSecurityResearchResource(
        action="add",
        title="Advisory",
        url="https://example.test/advisory",
        source_type="advisory",
        tags=["vendor"],
    ).run()
    assert json.loads(resource)["record"]["title"] == "Advisory"

    progress = UpdateSecurityResearchProgress(action="set", project="Case 1", task="Triage", status="done").run()
    assert json.loads(progress)["progress"]["tasks"][0]["status"] == "done"

    deliverable = CreateSecurityResearchDeliverable(
        file_name="blog draft",
        content="# Draft\n",
        project="Case 1",
    ).run()
    assert json.loads(deliverable)["path"] == "outputs/case-1/blog-draft.md"

    (tmp_path / "design_language.md").write_text("# Design\n", encoding="utf-8")
    assert json.loads(LoadSecurityDesignLanguage().run())["content"] == "# Design\n"

    with pytest.raises(ValueError):
        ManageSecurityResearchNote(action="write", path="../escape.md", content="no").run()
