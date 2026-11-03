"""Brazil PNCP consultation API (public). Two record kinds: procurements (/v1/contratacoes/publicacao) and contracts (/v1/contratos).
Natural-person suppliers are not stored: identifiers and names of individuals are removed from the raw payload and no supplier is created."""
import copy
import re

from ..bundle import Reject, make_record, money, party, to_ts
from .base import Connector

TZ = "-03:00"      # PNCP timestamps carry no zone; they are Brasilia time (recorded as an assumption in validation_notes)
BASE = "https://pncp.gov.br/api/consulta/v1"


def _ymd(d):
    return d.strftime("%Y%m%d")


class BrazilPncp(Connector):
    source_id = "brazil_pncp"
    expected_fields = frozenset({"numeroControlePNCP", "orgaoEntidade", "objetoCompra", "dataPublicacaoPncp", "dataAtualizacaoGlobal", "modalidadeId", "modalidadeNome",
                                 "situacaoCompraNome", "valorTotalEstimado", "valorTotalHomologado", "anoCompra", "sequencialCompra", "linkSistemaOrigem",
                                 "dataAberturaProposta", "dataEncerramentoProposta", "unidadeOrgao"})
    ignorable_fields = frozenset({"dataInclusao", "dataAtualizacao", "processo", "informacaoComplementar", "orgaoSubRogado", "unidadeSubRogada", "amparoLegal",
                                  "linkProcessoEletronico", "justificativaPresencial", "emendaParlamentar", "numeroCompra", "srp", "modoDisputaId",
                                  "modoDisputaNome", "tipoInstrumentoConvocatorioCodigo", "tipoInstrumentoConvocatorioNome", "fontesOrcamentarias",
                                  "situacaoCompraId", "usuarioNome",
                                  # contract records
                                  "numeroControlePncpCompra", "numeroControlePncpAta", "objetoContrato", "valorGlobal", "niFornecedor",
                                  "nomeRazaoSocialFornecedor", "tipoPessoa", "dataAssinatura", "dataVigenciaInicio", "dataVigenciaFim", "anoContrato",
                                  "sequencialContrato", "tipoContrato", "categoriaProcesso", "numeroContratoEmpenho", "valorInicial", "valorParcela",
                                  "valorAcumulado", "numeroParcelas", "numeroRetificacao", "receita", "temRemanejamento", "frutoAdesao",
                                  "codigoPaisFornecedor", "tipoPessoaSubContratada", "niFornecedorSubContratado", "nomeFornecedorSubContratado",
                                  "identificadorCipi", "urlCipi", "unidadeSubRogada", "orgaoSubRogado"})

    def _pages(self, path, params, limit):
        page, n = 1, 0
        while n < limit:
            j = self.get_json(BASE + path, params={**params, "pagina": page, "tamanhoPagina": min(50, max(10, limit - n))})
            for it in j.get("data") or []:
                self.observe(it)
                yield it
                n += 1
                if n >= limit:
                    return
            if not j.get("data") or page >= (j.get("totalPaginas") or 0):
                return
            page += 1

    def fetch(self, *, limit, since, until):
        d = {"dataInicial": _ymd(since), "dataFinal": _ymd(until)}
        half = max(1, limit // 2)
        for mod in self.opts.get("modalidades", (6,)):
            yield from self._pages("/contratacoes/publicacao", {**d, "codigoModalidadeContratacao": mod}, half)
        yield from self._pages("/contratos", d, limit - half)

    @staticmethod
    def _buyer(raw):
        o = raw.get("orgaoEntidade") or {}
        return party(o.get("razaoSocial"), o.get("cnpj"), "BR-CNPJ", "BR")

    def normalize(self, raw, fetched_at):
        return self._contract(raw, fetched_at) if "numeroControlePncpCompra" in raw else self._procurement(raw, fetched_at)

    def _procurement(self, raw, fetched_at):
        num = raw.get("numeroControlePNCP")
        if not num:
            raise Reject("missing_numeroControlePNCP")
        slim = {k: v for k, v in raw.items() if k != "usuarioNome"}          # a named user account, not needed
        o = raw.get("orgaoEntidade") or {}
        url = raw.get("linkSistemaOrigem") or "https://pncp.gov.br/app/editais/%s/%s/%s" % (o.get("cnpj"), raw.get("anoCompra"), raw.get("sequencialCompra"))
        est = money(raw.get("valorTotalEstimado"), "BRL") if raw.get("valorTotalEstimado") not in (None, 0) else None
        process = {
            "ocid": "myb-brazil_pncp-%s" % num, "ocid_native": False, "stage": "tender", "title": (raw.get("objetoCompra") or "")[:200] or None,
            "description": raw.get("objetoCompra"), "buyer": self._buyer(raw), "country": "BR", "status": raw.get("situacaoCompraNome"),
            "procurement_method": raw.get("modalidadeNome"), "value": est, "published_at": to_ts(raw.get("dataPublicacaoPncp"), TZ),
            "updated_at": to_ts(raw.get("dataAtualizacaoGlobal") or raw.get("dataAtualizacao"), TZ), "tender_start": to_ts(raw.get("dataAberturaProposta"), TZ),
            "tender_end": to_ts(raw.get("dataEncerramentoProposta"), TZ), "language": "pt", "url": url,
        }
        return make_record(source_id=self.source_id, external_id="compra:%s" % num, raw=slim, process=process, fetched_at=fetched_at, source_url=url,
                           publisher="Portal Nacional de Contratações Públicas (PNCP)", published_at=process["published_at"], source_updated_at=process["updated_at"],
                           language="pt", validation_notes=["naive_timestamps_assumed_brasilia_time"])

    def _contract(self, raw, fetched_at):
        num, compra = raw.get("numeroControlePNCP"), raw.get("numeroControlePncpCompra")
        if not num or not compra:
            raise Reject("missing_contract_identifiers")
        slim, notes = copy.deepcopy(raw), ["naive_timestamps_assumed_brasilia_time"]
        awards = []
        if raw.get("tipoPessoa") == "PJ" and raw.get("niFornecedor"):
            awards = [{"award_id": num, "status": None, "date": to_ts(raw.get("dataAssinatura"), TZ), "value": None,
                       "suppliers": [party(raw.get("nomeRazaoSocialFornecedor"), raw.get("niFornecedor"), "BR-CNPJ", "BR")]}]
        else:
            for k in ("niFornecedor", "nomeRazaoSocialFornecedor"):
                slim.pop(k, None)
            notes.append("supplier_omitted_not_a_company")
        if raw.get("tipoPessoaSubContratada") != "PJ":
            for k in ("niFornecedorSubContratado", "nomeFornecedorSubContratado"):
                slim.pop(k, None)
        val = money(raw.get("valorGlobal"), "BRL") if raw.get("valorGlobal") is not None else None
        o = raw.get("orgaoEntidade") or {}
        m = re.fullmatch(r"(\d+)-\d+-0*(\d+)/(\d{4})", compra)
        url = "https://pncp.gov.br/app/editais/%s/%s/%s" % (m[1], m[3], m[2]) if m else None
        process = {"ocid": "myb-brazil_pncp-%s" % compra, "ocid_native": False, "stage": "contract", "title": (raw.get("objetoContrato") or "")[:200] or None,
                   "description": raw.get("objetoContrato"), "buyer": self._buyer(raw), "country": "BR", "published_at": to_ts(raw.get("dataPublicacaoPncp"), TZ),
                   "updated_at": to_ts(raw.get("dataAtualizacaoGlobal") or raw.get("dataAtualizacao"), TZ), "language": "pt", "url": url}
        contracts = [{"contract_id": num, "award_id": num if awards else None, "title": (raw.get("objetoContrato") or "")[:200] or None,
                      "date_signed": to_ts(raw.get("dataAssinatura"), TZ), "period_start": to_ts(raw.get("dataVigenciaInicio"), TZ),
                      "period_end": to_ts(raw.get("dataVigenciaFim"), TZ), "value": val}]
        return make_record(source_id=self.source_id, external_id="contrato:%s" % num, raw=slim, process=process, fetched_at=fetched_at, source_url=url,
                           publisher="Portal Nacional de Contratações Públicas (PNCP)", published_at=process["published_at"], source_updated_at=process["updated_at"],
                           language="pt", awards=awards, contracts=contracts, validation_notes=notes)
