"""Sources whose access needs a credential this deployment does not hold. These connectors fail closed: they raise before any
request is made. No field mapping is written because none has been checked against a real response."""
from .base import Connector


class _Gated(Connector):
    note = ""

    def fetch(self, *, limit, since, until):
        self.check_credentials()
        raise NotImplementedError("%s: credential present but the field mapping has not been written against a real response yet. %s" % (self.source_id, self.note))

    def normalize(self, raw, fetched_at):
        raise NotImplementedError(self.source_id)


class SamOpportunities(_Gated):
    source_id, credential_env = "sam_opportunities", "SAM_GOV_API_KEY"
    note = "Docs: api_key required, postedFrom/postedTo (MM/dd/yyyy, max 1 year apart), limit max 1000, latest active version only."


class ChileLicitaciones(_Gated):
    source_id, credential_env = "chile_mercado", "CHILECOMPRA_TICKET"
    note = "Docs (verified quote in evidence/claims_reviewed.json): ticket via Clave Unica, 10,000 requests per day per ticket."


class ChileOrdenes(_Gated):
    source_id, credential_env = "chile_orders", "CHILECOMPRA_TICKET"
    note = "Docs (verified quote in evidence/claims_reviewed.json): ticket via Clave Unica, 10,000 requests per day per ticket."
