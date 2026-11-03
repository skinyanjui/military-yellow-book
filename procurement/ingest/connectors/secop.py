"""Colombia SECOP II electronic contracts, published by Colombia Compra Eficiente on datos.gov.co (Socrata dataset jbjy-vk9h,
identified through the Socrata catalog API; licence reported by that catalog: CC BY-SA 4.0). Legal-representative fields and
non-company supplier identifiers are dropped before storage."""
from ..bundle import Reject, classification, make_record, money, party, to_ts
from .base import Connector

URL = "https://www.datos.gov.co/resource/jbjy-vk9h.json"
TZ = "-05:00"      # Socrata floating timestamps carry no zone; Colombia is UTC-5 all year
PERSONAL = ("nombre_representante_legal", "nacionalidad_representante_legal", "domicilio_representante_legal", "tipo_de_identificaci_n_representante_legal",
            "identificaci_n_representante_legal", "g_nero_representante_legal")


class ColombiaSecop(Connector):
    source_id = "colombia_secop"
    expected_fields = frozenset({"nombre_entidad", "nit_entidad", "proceso_de_compra", "id_contrato", "estado_contrato", "descripcion_del_proceso", "tipo_de_contrato",
                                 "modalidad_de_contratacion", "proveedor_adjudicado", "documento_proveedor", "tipodocproveedor", "valor_del_contrato", "urlproceso"})
    report_unexpected = False

    def fetch(self, *, limit, since, until):
        offset, n = 0, 0
        where = "fecha_de_firma >= '%s' AND fecha_de_firma <= '%s'" % (since.strftime("%Y-%m-%dT00:00:00"), until.strftime("%Y-%m-%dT23:59:59"))
        while n < limit:
            rows = self.get_json(URL, params={"$limit": min(200, limit - n), "$offset": offset, "$order": "fecha_de_firma DESC, id_contrato", "$where": where})
            for r in rows:
                self.observe(r)
                yield r
                n += 1
            if len(rows) == 0:
                return
            offset += len(rows)

    def normalize(self, raw, fetched_at):
        cid, proc = raw.get("id_contrato"), raw.get("proceso_de_compra")
        if not cid or not proc:
            raise Reject("missing_contract_or_process_id")
        slim, notes = {k: v for k, v in raw.items() if k not in PERSONAL}, ["naive_timestamps_assumed_bogota_time"]
        sup = []
        if raw.get("tipodocproveedor") == "NIT" and raw.get("documento_proveedor"):
            sup = [party(raw.get("proveedor_adjudicado"), raw["documento_proveedor"], "CO-NIT", "CO")]
        else:
            slim.pop("documento_proveedor", None)
            slim.pop("proveedor_adjudicado", None)
            notes.append("supplier_omitted_not_a_company")
        cat = raw.get("codigo_de_categoria_principal") or ""
        cls = [classification("UNSPSC", cat.split(".", 1)[1])] if cat.startswith("V1.") and cat[3:].isdigit() else []
        url = ((raw.get("urlproceso") or {}).get("url")) if isinstance(raw.get("urlproceso"), dict) else None
        val = money(raw.get("valor_del_contrato"), "COP") if raw.get("valor_del_contrato") not in (None, "") else None
        process = {"ocid": "myb-colombia_secop-%s" % proc, "ocid_native": False, "stage": "contract", "title": (raw.get("descripcion_del_proceso") or "")[:200] or None,
                   "description": raw.get("descripcion_del_proceso"), "buyer": party(raw.get("nombre_entidad"), raw.get("nit_entidad"), "CO-NIT", "CO"), "country": "CO",
                   "status": raw.get("estado_contrato"), "procurement_method": raw.get("modalidad_de_contratacion"), "main_category": raw.get("tipo_de_contrato"),
                   "published_at": to_ts(raw.get("fecha_de_firma"), TZ), "updated_at": to_ts(raw.get("ultima_actualizacion") or raw.get("fecha_de_firma"), TZ),
                   "classifications": cls, "language": "es", "url": url}
        awards = [{"award_id": cid, "date": to_ts(raw.get("fecha_de_firma"), TZ), "suppliers": sup}] if sup else []
        contracts = [{"contract_id": cid, "award_id": cid if sup else None, "status": raw.get("estado_contrato"), "date_signed": to_ts(raw.get("fecha_de_firma"), TZ),
                      "period_start": to_ts(raw.get("fecha_de_inicio_del_contrato"), TZ), "period_end": to_ts(raw.get("fecha_de_fin_del_contrato"), TZ), "value": val}]
        return make_record(source_id=self.source_id, external_id=cid, raw=slim, process=process, fetched_at=fetched_at, source_url=url,
                           publisher="Agencia Nacional de Contratación Pública - Colombia Compra Eficiente", published_at=process["published_at"],
                           source_updated_at=process["updated_at"], language="es", licence="CC BY-SA 4.0 (as reported by the datos.gov.co catalog)",
                           awards=awards, contracts=contracts, validation_notes=notes)
