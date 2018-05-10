from custom_elastic_search import CustomElasticSearch
from config import INDICES

class ContractTransactions:
  def __init__(self, indices=INDICES, elasticsearch_host="http://localhost:9200", ethereum_api_host="http://localhost:8545"):
    self.indices = indices
    self.client = CustomElasticSearch(elasticsearch_host)
    self.ethereum_api_host = ethereum_api_host

  def _iterate_contract_transactions(self):
    return self.client.iterate(self.indices["transaction"], 'tx', 'input:0x?* AND !(_exists_:to_contract)', paginate=True, scrolling=False)

  def _extract_contract_addresses(self):
    for contract_transactions in self._iterate_contract_transactions():
      contracts = [transaction["_source"]["to"] for transaction in contract_transactions]
      docs = [{'address': contract, 'id': contract} for contract in contracts]
      self.client.bulk_index(docs=docs, doc_type='contract', index=self.indices["contract"], refresh=True)

  def _iterate_contracts(self):
    return self.client.iterate(self.indices["contract"], 'contract', 'address:* AND !(_exists_:transactions_detected)', paginate=True)

  def _detect_transactions_by_contracts(self, contracts):
    transactions_query = {
      "terms": {
        "to": contracts
      }
    }
    contracts_query = {
      "terms": {
        "address": contracts
      }
    }
    self.client.update_by_query(self.indices["transaction"], 'tx', transactions_query, "ctx._source.to_contract = true")
    self.client.update_by_query(self.indices["contract"], 'contract', contracts_query, "ctx._source.transactions_detected = true")

  def detect_contract_transactions(self):
    self._extract_contract_addresses()
    for contracts in self._iterate_contracts():
      contracts = [contract["_source"]["address"] for contract in contracts]
      self._detect_transactions_by_contracts(contracts)