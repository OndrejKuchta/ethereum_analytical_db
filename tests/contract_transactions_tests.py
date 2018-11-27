import unittest 
from operations.contract_transactions import ElasticSearchContractTransactions, ClickhouseContractTransactions
from pyelasticsearch import ElasticSearch
from time import sleep
from tqdm import *
from tests.test_utils import TestElasticSearch, TestClickhouse
from unittest.mock import MagicMock, Mock, call, ANY, patch
from operations.indices import ClickhouseIndices

class ElasticSearchContractTransactionsTestCase(unittest.TestCase):
  contract_transactions_class = ElasticSearchContractTransactions
  index = "internal_transaction"
  doc_type = "itx"

  def setUp(self):
    self.client = TestElasticSearch()
    self.client.recreate_fast_index(TEST_TRANSACTIONS_INDEX)
    self.client.recreate_index(TEST_CONTRACTS_INDEX)
    self.contract_transactions = self.contract_transactions_class({"contract": TEST_CONTRACTS_INDEX, self.index: TEST_TRANSACTIONS_INDEX})

  def test_iterate_contract_transactions(self):
    """
    Test iterations through transactions that create contracts
    """
    self.client.index(TEST_TRANSACTIONS_INDEX, 'itx', {'type': "call"}, id=1, refresh=True)
    self.client.index(TEST_TRANSACTIONS_INDEX, 'itx', {'type': "create"}, id=2, refresh=True)
    self.client.index(TEST_TRANSACTIONS_INDEX, 'itx', {'type': "create", "error": "Out of gas"}, id=3, refresh=True)
    self.client.index(TEST_TRANSACTIONS_INDEX, 'nottx', {'type': "create"}, id=4, refresh=True)
    self.client.index(TEST_TRANSACTIONS_INDEX, 'itx', {'type': "create", "contract_created": True}, id=5, refresh=True)
    iterator = self.contract_transactions._iterate_contract_transactions()
    transactions = next(iterator)
    transactions = [transaction['_id'] for transaction in transactions]
    self.assertCountEqual(['2'], transactions)

  def test_extract_contract_from_internal_transaction(self):
    """
    Test extracting contract from a defined transaction
    """
    transaction = {
      "from": "0x0",
      "input": "0x1",
      "address": "0x2",
      "code": "0x3",
      "blockNumber": 100
    }
    transaction_id = "0x10"
    contract = self.contract_transactions._extract_contract_from_transactions({
      "_source": transaction,
      "_id": transaction_id
    })
    assert contract["owner"] == transaction["from"]
    assert contract["blockNumber"] == transaction["blockNumber"]
    assert contract["parent_transaction"] == transaction_id
    assert contract["address"] == transaction["address"]
    assert contract["id"] == transaction["address"]
    assert contract["bytecode"] == transaction["code"]

  def test_extract_contract_addresses(self):
    """
    Test extracting contracts from transactions to ElasticSearch
    """
    transactions_list = [
      [{"_source": {"hash": "transaction" + str(i)}} for i in range(10)],
      [{"_source": {"hash": "transaction" + str(i)}} for i in range(10, 11)]
    ]
    self.contract_transactions._iterate_contract_transactions = MagicMock(return_value=transactions_list)
    self.contract_transactions._extract_contract_from_transactions = MagicMock(return_value="contract")
    self.contract_transactions.client.bulk_index = MagicMock()
    self.contract_transactions._save_contract_created = MagicMock()

    process = Mock()
    process.configure_mock(
      iterate=self.contract_transactions._iterate_contract_transactions,
      extract=self.contract_transactions._extract_contract_from_transactions,
      save_flag=self.contract_transactions._save_contract_created,
      index=self.contract_transactions.client.bulk_index
    )
    calls = [call.iterate()]
    for transactions in transactions_list:
      for transaction in transactions:
        calls.append(call.extract(transaction))
      calls.append(call.index(
        refresh=True,
        doc_type='contract',
        index=TEST_CONTRACTS_INDEX,
        docs=["contract" for _ in transactions]
      ))
      calls.append(call.save_flag(transactions))
    self.contract_transactions.extract_contract_addresses()

    process.assert_has_calls(calls)

  def test_save_flag_for_contracts(self):
    """
    Test save flag for processed transactions
    """
    transactions = [{
      "hash": "0x" + str(i)
    } for i in range(10)]
    self.client.bulk_index(
      index=TEST_TRANSACTIONS_INDEX,
      doc_type=self.doc_type,
      docs=transactions,
      refresh=True
    )
    transactions_from_elasticsearch = self.client.search(
      index=TEST_TRANSACTIONS_INDEX,
      doc_type=self.doc_type,
      query="*",
      size=len(transactions)
    )['hits']['hits']

    self.contract_transactions._save_contract_created(transactions_from_elasticsearch)
    transactions_count = self.client.count(
      index=TEST_TRANSACTIONS_INDEX,
      doc_type=self.doc_type,
      query="_exists_:contract_created"
    )["count"]
    assert transactions_count == 10

  def test_iterate_contracts(self):
    """
    Test iterations through all contracts
    """
    self.client.index(TEST_CONTRACTS_INDEX, 'contract', {'address': TEST_TRANSACTION_TO}, id=1, refresh=True)
    self.client.index(TEST_CONTRACTS_INDEX, 'contract', {'address': TEST_TRANSACTION_TO_CONTRACT}, id=2, refresh=True)
    iterator = self.contract_transactions._iterate_contracts_without_detected_transactions(0)
    contracts = [c for contracts_list in iterator for c in contracts_list]
    contracts = [contract['_id'] for contract in contracts]
    self.assertCountEqual(["1", "2"], contracts)

  def test_iterate_unprocessed_contracts(self):
    """
    Test iterations through unprocessed contracts with helper class usage
    """
    test_iterator = "iterator"
    test_max_block = 0
    self.contract_transactions._iterate_contracts = MagicMock(return_value=test_iterator)

    contracts = self.contract_transactions._iterate_contracts_without_detected_transactions(test_max_block)
    self.contract_transactions._iterate_contracts.assert_any_call(test_max_block, ANY)
    assert contracts == test_iterator

  def test_detect_transactions_by_contracts(self):
    """
    Test to_contract flag placement in ElasticSearch
    """
    test_query = {"test": "query"}
    test_max_block = 0
    self.contract_transactions.client.update_by_query = MagicMock()
    self.contract_transactions._create_transactions_request = MagicMock(return_value=test_query)
    contracts = [{"_source": {"address": "0x1"}}, {"_source": {"address": "0x2"}}]
    contracts_addresses = ["0x1", "0x2"]
    self.contract_transactions._detect_transactions_by_contracts(contracts, test_max_block)

    self.contract_transactions._create_transactions_request.assert_any_call(ANY, test_max_block)
    self.contract_transactions.client.update_by_query.assert_any_call(
      TEST_TRANSACTIONS_INDEX,
      self.doc_type,
      {
        "bool": {
          "must": [
            {"terms": {"to": contracts_addresses}},
            test_query
          ]
        }
      },
      "ctx._source.to_contract = true"
    )

  def test_detect_contract_transactions(self):
    """
    Test contract transactions detection process
    """
    test_max_block = 10
    contracts_list = [[TEST_TRANSACTION_TO + str(j * 10 + i) for i in range(10)] for j in range(5)]
    contracts_from_es_list = [[{"_source": {"address": contract}} for contract in contracts] for contracts in
                              contracts_list]
    self.contract_transactions.extract_contract_addresses = MagicMock()
    self.contract_transactions._iterate_contracts_without_detected_transactions = MagicMock(return_value=contracts_from_es_list)
    self.contract_transactions._detect_transactions_by_contracts = MagicMock()
    self.contract_transactions._save_max_block = MagicMock()
    test_max_block_mock = MagicMock(side_effect=[test_max_block])
    with patch('utils.get_max_block', test_max_block_mock):
      process = Mock()
      process.configure_mock(
        get_max_block=test_max_block_mock,
        iterate=self.contract_transactions._iterate_contracts_without_detected_transactions,
        detect=self.contract_transactions._detect_transactions_by_contracts,
        save=self.contract_transactions._save_max_block
      )

      self.contract_transactions.detect_contract_transactions()

      call_part = []
      for index, contracts in enumerate(contracts_from_es_list):
        call_part.append(call.detect(contracts, test_max_block))
        call_part.append(call.save(contracts_list[index], test_max_block))
      process.assert_has_calls([
                                 call.get_max_block(),
                                 call.iterate(test_max_block)
                               ] + call_part)

class ClickhouseContractTransactionsTestCase(unittest.TestCase):
  def setUp(self):
    self.indices = {
      "internal_transaction": TEST_TRANSACTIONS_INDEX,
      "contract": TEST_CONTRACTS_INDEX
    }
    self.client = TestClickhouse()
    for index in self.indices.values():
      self.client.send_sql_request("DROP TABLE IF EXISTS {}".format(index))
    ClickhouseIndices(self.indices).prepare_indices()
    self.contract_transactions = ClickhouseContractTransactions(self.indices)
    self.contract_transactions.extract_contract_addresses()

  def test_extract_contract_addresses(self):
    transaction = {
      "id": "0x12345",
      "type": "create",
      "address": "0x0",
      "blockNumber": 1000,
      "from": "0x01",
      "code": "0x12345678"
    }
    self.client.bulk_index(index=TEST_TRANSACTIONS_INDEX, docs=[transaction])
    result = self.client.search(index=TEST_CONTRACTS_INDEX, fields=[
      "address",
      "blockNumber",
      "owner",
      "bytecode"
    ])
    contract = result[0]
    print(contract)
    assert contract["_id"] == transaction["address"]
    assert contract['_source']["address"] == transaction["address"]
    assert contract['_source']["blockNumber"] == transaction["blockNumber"]
    assert contract['_source']["owner"] == transaction["from"]
    assert contract['_source']["bytecode"] == transaction["code"]

  def test_extract_contract_standards(self):
    transactions = [{
      "id": "0x1",
      "type": "create",
      "code": TEST_ERC20_BYTECODE,
    }, {
      "id": "0x2",
      "type": "create",
      "code": "0x0"
    }]
    self.client.bulk_index(index=TEST_TRANSACTIONS_INDEX, docs=transactions)
    result = self.client.search(index=TEST_CONTRACTS_INDEX, fields=[
      "standard_erc20"
    ])
    assert result[0]["_source"]["standard_erc20"]
    assert not result[1]["_source"]["standard_erc20"]

  def test_extract_contract_addresses_if_exists(self):
    self.contract_transactions.extract_contract_addresses()

  def test_extract_contract_addresses_ignore_transactions(self):
    transactions = [{
      "id": 1,
      "type": "call"
    }, {
      "id": 2,
      "type": "create",
      "address": "0x0",
      "error": "Out of gas"
    }, {
      "id": 3,
      "type": "create",
      "address": "0x0",
      "parent_error": True,
    }]
    self.client.bulk_index(index=TEST_TRANSACTIONS_INDEX, docs=transactions)
    count = self.client.count(index=TEST_CONTRACTS_INDEX)
    assert not count

  def test_extract_contract_addresses_ignore_duplicates(self):
    transaction = {
      "id": 1,
      "type": "create"
    }
    self.client.bulk_index(index=TEST_TRANSACTIONS_INDEX, docs=[transaction, transaction])
    count = self.client.count(index=TEST_CONTRACTS_INDEX)
    assert count == 1

  # Cases:
  # self.client.index(TEST_TRANSACTIONS_INDEX, 'itx', {'type': "call"}, id=1, refresh=True)
  # self.client.index(TEST_TRANSACTIONS_INDEX, 'itx', {'type': "create"}, id=2, refresh=True)
  # self.client.index(TEST_TRANSACTIONS_INDEX, 'itx', {'type': "create", "error": "Out of gas"}, id=3, refresh=True)
  # self.client.index(TEST_TRANSACTIONS_INDEX, 'nottx', {'type': "create"}, id=4, refresh=True)
  # self.client.index(TEST_TRANSACTIONS_INDEX, 'itx', {'type': "create", "contract_created": True}, id=5, refresh=True)

  # Fields:
  # assert contract["owner"] == transaction["from"]
  # assert contract["blockNumber"] == transaction["blockNumber"]
  # assert contract["parent_transaction"] == transaction_id
  # assert contract["address"] == transaction["address"]
  # assert contract["id"] == transaction["address"]
  # assert contract["bytecode"] == transaction["code"]
  pass

TEST_TRANSACTIONS_INDEX = 'test_ethereum_transactions'
TEST_CONTRACTS_INDEX = 'test_ethereum_contracts'
TEST_TRANSACTION_INPUT = '0x38a999ebba98a14a67ea7a83921e3e58d04a29fc55adfa124a985771f323052a'
TEST_TRANSACTION_TO = '0xb1631db29e09ec5581a0ec398f1229abaf105d3524c49727621841af947bdc44'
TEST_TRANSACTION_TO_COMMON = '0x38a999ebba98a14a67ea7a83921e3e58d04a29fc55adfa124a985771f323052a'
TEST_TRANSACTION_TO_CONTRACT = '0x69a999ebba98a14a67ea7a83921e3e58d04a29fc55adfa124a985771f323052a'
TEST_ERC20_BYTECODE = "606060405260126006556000600790600019169055341561001c57fe5b604051602080611c5d833981016040528080519060200190919050505b5b60005b80600160003373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200190815260200160002081905550806000819055505b5033600460006101000a81548173ffffffffffffffffffffffffffffffffffffffff021916908373ffffffffffffffffffffffffffffffffffffffff1602179055503373ffffffffffffffffffffffffffffffffffffffff167fce241d7ca1f669fee44b6fc00b8eba2df3bb514eed0f6f668f8f89096e81ed9460405180905060405180910390a25b80600581600019169055505b505b611b2e8061012f6000396000f3006060604052361561011b576000357c0100000000000000000000000000000000000000000000000000000000900463ffffffff16806306fdde031461011d57806307da68f51461014b578063095ea7b31461015d57806313af4035146101b457806318160ddd146101ea57806323b872dd14610210578063313ce567146102865780633452f51d146102ac5780635ac801fe1461031557806369d3e20e1461033957806370a082311461036b57806375f12b21146103b55780637a9e5e4b146103df5780638402181f146104155780638da5cb5b1461047e57806390bc1693146104d057806395d89b4114610502578063a9059cbb14610530578063be9a655514610587578063bf7e214f14610599578063dd62ed3e146105eb575bfe5b341561012557fe5b61012d610654565b60405180826000191660001916815260200191505060405180910390f35b341561015357fe5b61015b61065a565b005b341561016557fe5b61019a600480803573ffffffffffffffffffffffffffffffffffffffff1690602001909190803590602001909190505061075e565b604051808215151515815260200191505060405180910390f35b34156101bc57fe5b6101e8600480803573ffffffffffffffffffffffffffffffffffffffff1690602001909190505061083c565b005b34156101f257fe5b6101fa610920565b6040518082815260200191505060405180910390f35b341561021857fe5b61026c600480803573ffffffffffffffffffffffffffffffffffffffff1690602001909190803573ffffffffffffffffffffffffffffffffffffffff1690602001909190803590602001909190505061092b565b604051808215151515815260200191505060405180910390f35b341561028e57fe5b610296610a0b565b6040518082815260200191505060405180910390f35b34156102b457fe5b6102fb600480803573ffffffffffffffffffffffffffffffffffffffff169060200190919080356fffffffffffffffffffffffffffffffff16906020019091905050610a11565b604051808215151515815260200191505060405180910390f35b341561031d57fe5b610337600480803560001916906020019091905050610a38565b005b341561034157fe5b61036960048080356fffffffffffffffffffffffffffffffff16906020019091905050610a7e565b005b341561037357fe5b61039f600480803573ffffffffffffffffffffffffffffffffffffffff16906020019091905050610c44565b6040518082815260200191505060405180910390f35b34156103bd57fe5b6103c5610c8e565b604051808215151515815260200191505060405180910390f35b34156103e757fe5b610413600480803573ffffffffffffffffffffffffffffffffffffffff16906020019091905050610ca1565b005b341561041d57fe5b610464600480803573ffffffffffffffffffffffffffffffffffffffff169060200190919080356fffffffffffffffffffffffffffffffff16906020019091905050610d85565b604051808215151515815260200191505060405180910390f35b341561048657fe5b61048e610dad565b604051808273ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200191505060405180910390f35b34156104d857fe5b61050060048080356fffffffffffffffffffffffffffffffff16906020019091905050610dd3565b005b341561050a57fe5b610512610f99565b60405180826000191660001916815260200191505060405180910390f35b341561053857fe5b61056d600480803573ffffffffffffffffffffffffffffffffffffffff16906020019091908035906020019091905050610f9f565b604051808215151515815260200191505060405180910390f35b341561058f57fe5b61059761107d565b005b34156105a157fe5b6105a9611181565b604051808273ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200191505060405180910390f35b34156105f357fe5b61063e600480803573ffffffffffffffffffffffffffffffffffffffff1690602001909190803573ffffffffffffffffffffffffffffffffffffffff169060200190919050506111a7565b6040518082815260200191505060405180910390f35b60075481565b61069061068b336000357fffffffff000000000000000000000000000000000000000000000000000000001661122f565b611491565b6000600060043591506024359050806000191682600019163373ffffffffffffffffffffffffffffffffffffffff166000357fffffffff00000000000000000000000000000000000000000000000000000000167bffffffffffffffffffffffffffffffffffffffffffffffffffffffff19163460003660405180848152602001806020018281038252848482818152602001925080828437820191505094505050505060405180910390a46001600460146101000a81548160ff0219169083151502179055505b5b50505b565b6000610779600460149054906101000a900460ff1615611491565b6000600060043591506024359050806000191682600019163373ffffffffffffffffffffffffffffffffffffffff166000357fffffffff00000000000000000000000000000000000000000000000000000000167bffffffffffffffffffffffffffffffffffffffffffffffffffffffff19163460003660405180848152602001806020018281038252848482818152602001925080828437820191505094505050505060405180910390a461082f85856114a2565b92505b5b50505b92915050565b61087261086d336000357fffffffff000000000000000000000000000000000000000000000000000000001661122f565b611491565b80600460006101000a81548173ffffffffffffffffffffffffffffffffffffffff021916908373ffffffffffffffffffffffffffffffffffffffff160217905550600460009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff167fce241d7ca1f669fee44b6fc00b8eba2df3bb514eed0f6f668f8f89096e81ed9460405180905060405180910390a25b5b50565b600060005490505b90565b6000610946600460149054906101000a900460ff1615611491565b6000600060043591506024359050806000191682600019163373ffffffffffffffffffffffffffffffffffffffff166000357fffffffff00000000000000000000000000000000000000000000000000000000167bffffffffffffffffffffffffffffffffffffffffffffffffffffffff19163460003660405180848152602001806020018281038252848482818152602001925080828437820191505094505050505060405180910390a46109fd868686611595565b92505b5b50505b9392505050565b60065481565b6000610a2f83836fffffffffffffffffffffffffffffffff16610f9f565b90505b92915050565b610a6e610a69336000357fffffffff000000000000000000000000000000000000000000000000000000001661122f565b611491565b80600781600019169055505b5b50565b610ab4610aaf336000357fffffffff000000000000000000000000000000000000000000000000000000001661122f565b611491565b610acd600460149054906101000a900460ff1615611491565b6000600060043591506024359050806000191682600019163373ffffffffffffffffffffffffffffffffffffffff166000357fffffffff00000000000000000000000000000000000000000000000000000000167bffffffffffffffffffffffffffffffffffffffffffffffffffffffff19163460003660405180848152602001806020018281038252848482818152602001925080828437820191505094505050505060405180910390a4610bd4600160003373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200190815260200160002054846fffffffffffffffffffffffffffffffff166118f9565b600160003373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200190815260200160002081905550610c35600054846fffffffffffffffffffffffffffffffff166118f9565b6000819055505b5b50505b5b50565b6000600160008373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020016000205490505b919050565b600460149054906101000a900460ff1681565b610cd7610cd2336000357fffffffff000000000000000000000000000000000000000000000000000000001661122f565b611491565b80600360006101000a81548173ffffffffffffffffffffffffffffffffffffffff021916908373ffffffffffffffffffffffffffffffffffffffff160217905550600360009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff167f1abebea81bfa2637f28358c371278fb15ede7ea8dd28d2e03b112ff6d936ada460405180905060405180910390a25b5b50565b6000610da48333846fffffffffffffffffffffffffffffffff1661092b565b90505b92915050565b600460009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1681565b610e09610e04336000357fffffffff000000000000000000000000000000000000000000000000000000001661122f565b611491565b610e22600460149054906101000a900460ff1615611491565b6000600060043591506024359050806000191682600019163373ffffffffffffffffffffffffffffffffffffffff166000357fffffffff00000000000000000000000000000000000000000000000000000000167bffffffffffffffffffffffffffffffffffffffffffffffffffffffff19163460003660405180848152602001806020018281038252848482818152602001925080828437820191505094505050505060405180910390a4610f29600160003373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200190815260200160002054846fffffffffffffffffffffffffffffffff16611913565b600160003373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200190815260200160002081905550610f8a600054846fffffffffffffffffffffffffffffffff16611913565b6000819055505b5b50505b5b50565b60055481565b6000610fba600460149054906101000a900460ff1615611491565b6000600060043591506024359050806000191682600019163373ffffffffffffffffffffffffffffffffffffffff166000357fffffffff00000000000000000000000000000000000000000000000000000000167bffffffffffffffffffffffffffffffffffffffffffffffffffffffff19163460003660405180848152602001806020018281038252848482818152602001925080828437820191505094505050505060405180910390a4611070858561192d565b92505b5b50505b92915050565b6110b36110ae336000357fffffffff000000000000000000000000000000000000000000000000000000001661122f565b611491565b6000600060043591506024359050806000191682600019163373ffffffffffffffffffffffffffffffffffffffff166000357fffffffff00000000000000000000000000000000000000000000000000000000167bffffffffffffffffffffffffffffffffffffffffffffffffffffffff19163460003660405180848152602001806020018281038252848482818152602001925080828437820191505094505050505060405180910390a46000600460146101000a81548160ff0219169083151502179055505b5b50505b565b600360009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1681565b6000600260008473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200190815260200160002060008373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020016000205490505b92915050565b60003073ffffffffffffffffffffffffffffffffffffffff168373ffffffffffffffffffffffffffffffffffffffff16141561126e576001905061148b565b600460009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff168373ffffffffffffffffffffffffffffffffffffffff1614156112cd576001905061148b565b600073ffffffffffffffffffffffffffffffffffffffff16600360009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16141561132d576000905061148b565b600360009054906101000a900473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1663b70096138430856000604051602001526040518463ffffffff167c0100000000000000000000000000000000000000000000000000000000028152600401808473ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020018373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff168152602001827bffffffffffffffffffffffffffffffffffffffffffffffffffffffff19167bffffffffffffffffffffffffffffffffffffffffffffffffffffffff191681526020019350505050602060405180830381600087803b151561146957fe5b6102c65a03f1151561147757fe5b50505060405180519050905061148b565b5b5b5b92915050565b80151561149e5760006000fd5b5b50565b600081600260003373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200190815260200160002060008573ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff168152602001908152602001600020819055508273ffffffffffffffffffffffffffffffffffffffff163373ffffffffffffffffffffffffffffffffffffffff167f8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925846040518082815260200191505060405180910390a3600190505b92915050565b600081600160008673ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200190815260200160002054101515156115e257fe5b81600260008673ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200190815260200160002060003373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff168152602001908152602001600020541015151561166a57fe5b6116f0600260008673ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200190815260200160002060003373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020016000205483611913565b600260008673ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200190815260200160002060003373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff168152602001908152602001600020819055506117b9600160008673ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020016000205483611913565b600160008673ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200190815260200160002081905550611845600160008573ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200190815260200160002054836118f9565b600160008573ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff168152602001908152602001600020819055508273ffffffffffffffffffffffffffffffffffffffff168473ffffffffffffffffffffffffffffffffffffffff167fddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef846040518082815260200191505060405180910390a3600190505b9392505050565b6000828284019150811015151561190c57fe5b5b92915050565b6000828284039150811115151561192657fe5b5b92915050565b600081600160003373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff168152602001908152602001600020541015151561197a57fe5b6119c3600160003373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff1681526020019081526020016000205483611913565b600160003373ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200190815260200160002081905550611a4f600160008573ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff16815260200190815260200160002054836118f9565b600160008573ffffffffffffffffffffffffffffffffffffffff1673ffffffffffffffffffffffffffffffffffffffff168152602001908152602001600020819055508273ffffffffffffffffffffffffffffffffffffffff163373ffffffffffffffffffffffffffffffffffffffff167fddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef846040518082815260200191505060405180910390a3600190505b929150505600a165627a7a723058204432a84cfe06a995bd95935559d84003b39a006720c2eabd96115f376347f9b80029454f530000000000000000000000000000000000000000000000000000000000"