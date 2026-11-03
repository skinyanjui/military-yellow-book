"""Each connector's normalize() against responses recorded from the real publisher (tests/fixtures), plus the privacy rules."""
import copy

import pytest

from conftest import NOW, NoNetwork, fixture
from ingest import bundle as B
from ingest.connectors import pncp, secop, ted, uk, usaspending, worldbank


def validate(rec, source_id):
    b = {"run": {"run_id": "4f0e3a1e-8f9d-4d51-9a53-0d0f0f0f0f0f", "source_id": source_id, "mode": "test"}, "records": [rec], "rejected": []}
    assert B.schema_errors(b) == []
    assert len(rec["content_hash"]) == 64 and rec["process"]["ocid"] and rec["external_id"]
    return rec


def test_uk_find_a_tender_ocds_release():
    pkg = fixture("uk_fts_sample.json")
    c = uk.UkFindATender(NoNetwork())
    c.publisher, c.licence = pkg["publisher"]["name"], pkg["license"]
    for rel in pkg["releases"]:
        r = validate(c.normalize(rel, NOW), "uk_fts")
        assert r["process"]["ocid_native"] is True and r["process"]["ocid"] == rel["ocid"]
        assert r["publisher"] and r["licence"] and r["source_url"].startswith("https://www.find-tender.service.gov.uk/Notice/")


def test_uk_contracts_finder_ocds_release_values_stay_in_original_currency():
    pkg = fixture("uk_cf_sample.json")
    c = uk.UkContractsFinder(NoNetwork())
    c.publisher, c.licence = pkg["publisher"]["name"], pkg["license"]
    got = [validate(c.normalize(rel, NOW), "uk_cf") for rel in pkg["releases"]]
    assert any(g["process"].get("value") for g in got)
    assert all(g["process"]["value"]["currency"] == "GBP" for g in got if g["process"].get("value"))


def test_ted_notice_maps_multilingual_fields_and_iso3_country():
    for n in fixture("ted_search_sample.json")["notices"]:
        r = validate(ted.Ted(NoNetwork()).normalize(n, NOW), "ted")
        assert len(r["process"]["country"]) == 2 and r["process"]["ocid_native"] is False
        assert r["process"]["stage"] in ("tender", "award", "planning", "contract")
        assert "links" in r["raw"] and r["source_url"].startswith("https://ted.europa.eu/")


def test_ted_requires_a_publication_number():
    with pytest.raises(B.Reject):
        ted.Ted(NoNetwork()).normalize({"notice-title": {"eng": "x"}}, NOW)


def test_world_bank_notice_has_no_invented_buyer():
    for row in fixture("worldbank_sample.json")["data"]:
        r = validate(worldbank.WorldBankNotices(NoNetwork()).normalize(row, NOW), "worldbank_procurement")
        assert r["process"].get("buyer") is None and "buyer_not_in_dataset" in r["validation_notes"]
        assert r["process"]["financier"] == "World Bank"


def test_pncp_procurements_and_contracts():
    c = pncp.BrazilPncp(NoNetwork())
    for it in fixture("pncp_contratacoes_sample.json")["data"]:
        r = validate(c.normalize(it, NOW), "brazil_pncp")
        assert r["process"]["stage"] == "tender" and r["process"]["ocid"].startswith("myb-brazil_pncp-")
        assert "usuarioNome" not in r["raw"]
    for it in fixture("pncp_contratos_sample.json")["data"]:
        r = validate(c.normalize(it, NOW), "brazil_pncp")
        assert r["contracts"]


def test_pncp_natural_person_supplier_is_not_stored():
    contract = copy.deepcopy(fixture("pncp_contratos_sample.json")["data"][0])
    contract.update(tipoPessoa="PF", niFornecedor="12345678901", nomeRazaoSocialFornecedor="FULANO DE TAL")
    r = validate(pncp.BrazilPncp(NoNetwork()).normalize(contract, NOW), "brazil_pncp")
    assert r["awards"] == []
    assert "12345678901" not in str(r) and "FULANO" not in str(r) and "supplier_omitted_not_a_company" in r["validation_notes"]


def test_pncp_company_supplier_is_kept_with_cnpj_scheme():
    contract = copy.deepcopy(fixture("pncp_contratos_sample.json")["data"][0])
    contract.update(tipoPessoa="PJ", niFornecedor="00000000000191", nomeRazaoSocialFornecedor="EMPRESA EXEMPLO LTDA")
    r = validate(pncp.BrazilPncp(NoNetwork()).normalize(contract, NOW), "brazil_pncp")
    assert r["awards"][0]["suppliers"][0]["scheme"] == "BR-CNPJ" and r["awards"][0]["suppliers"][0]["id"] == "00000000000191"


def test_pncp_user_name_field_is_dropped():
    it = copy.deepcopy(fixture("pncp_contratacoes_sample.json")["data"][0])
    it["usuarioNome"] = "Maria Exemplo"
    assert "Maria" not in str(pncp.BrazilPncp(NoNetwork()).normalize(it, NOW))


def test_secop_contract_company_supplier_and_unspsc():
    rows = fixture("secop_contratos_sample.json")
    c = secop.ColombiaSecop(NoNetwork())
    got = [validate(c.normalize(r, NOW), "colombia_secop") for r in rows]
    assert all(g["process"]["country"] == "CO" for g in got)
    assert all(g["process"]["stage"] == "contract" for g in got)


def test_secop_individual_supplier_and_legal_rep_fields_are_not_stored():
    row = copy.deepcopy(fixture("secop_contratos_sample.json")[0])
    row.update(tipodocproveedor="Cédula de Ciudadanía", documento_proveedor="1234567", proveedor_adjudicado="PERSONA NATURAL",
               nombre_representante_legal="REP LEGAL", identificaci_n_representante_legal="999888")
    r = validate(secop.ColombiaSecop(NoNetwork()).normalize(row, NOW), "colombia_secop")
    text = str(r)
    assert r["awards"] == [] and "PERSONA NATURAL" not in text and "REP LEGAL" not in text and "1234567" not in text and "999888" not in text


def test_usaspending_award_amount_is_obligated_not_contract_value():
    for raw in fixture("usaspending_sample.json"):
        r = validate(usaspending.UsaSpending(NoNetwork()).normalize(raw, NOW), "usaspending")
        a = r["awards"][0]
        assert a["obligated"]["currency"] == "USD" and a.get("value") is None
        assert r["contracts"][0].get("value") is None


@pytest.mark.parametrize("name", ["REDACTED DUE TO PII", "MULTIPLE RECIPIENTS"])
def test_usaspending_redacted_recipients_are_dropped(name):
    raw = copy.deepcopy(fixture("usaspending_sample.json")[0])
    raw["Recipient Name"] = name
    r = usaspending.UsaSpending(NoNetwork()).normalize(raw, NOW)
    assert r["awards"][0]["suppliers"] == [] and "Recipient Name" not in r["raw"] and "Recipient UEI" not in r["raw"]


def test_usaspending_needs_both_identifiers():
    with pytest.raises(B.Reject):
        usaspending.UsaSpending(NoNetwork()).normalize({"Award ID": "X"}, NOW)


def test_identical_input_gives_identical_hash_and_a_change_gives_a_new_one():
    n = fixture("ted_search_sample.json")["notices"][0]
    a, b = ted.Ted(NoNetwork()).normalize(n, NOW), ted.Ted(NoNetwork()).normalize(copy.deepcopy(n), "2026-11-04T00:00:00+00:00")
    assert a["content_hash"] == b["content_hash"]                          # fetch time is not part of the hash
    n2 = copy.deepcopy(n)
    n2["notice-title"] = {"eng": "A different title"}
    assert ted.Ted(NoNetwork()).normalize(n2, NOW)["content_hash"] != a["content_hash"]


def test_every_connector_declares_its_expected_fields_for_drift_detection():
    for c in (uk.UkFindATender, uk.UkContractsFinder, ted.Ted, pncp.BrazilPncp, usaspending.UsaSpending, worldbank.WorldBankNotices):
        assert c.expected_fields, c
