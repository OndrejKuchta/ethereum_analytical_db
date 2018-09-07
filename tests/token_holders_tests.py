import unittest
from token_holders import TokenHolders, InternalTokenTransactions
from tests.test_utils import TestElasticSearch, mockify
from unittest.mock import MagicMock, ANY, patch

class TokenHoldersTestCase(unittest.TestCase):
  def setUp(self):
    self.client = TestElasticSearch()
    self.client.recreate_index(TEST_CONTRACT_INDEX)
    self.client.recreate_index(TEST_TOKEN_TX_INDEX)
    self.client.recreate_index(TEST_ITX_INDEX)
    self.token_holders = InternalTokenTransactions({
      'contract': TEST_CONTRACT_INDEX, 
      'internal_transaction': TEST_ITX_INDEX,
      'token_tx': TEST_TOKEN_TX_INDEX})

  def iterate_processed(self):
    return self.token_holders.client.iterate(TEST_CONTRACT_INDEX, 'contract', '_exists_:cmc_id AND tx_descr_scanned:true')

  def iterate_supply_transfers(self):
    return self.token_holders.client.iterate(TEST_TOKEN_TX_INDEX, 'tx', 'method:initial')

  def iterate_token_txs(self):
    return self.token_holders.client.iterate(TEST_TOKEN_TX_INDEX, 'tx', 'token:*')

  def test_extract_token_txs(self):
    self.token_holders._create_transactions_request = MagicMock(return_value={
      "query_string": {
        "query": "*"
      }
    })
    test_max_block = 10
    test_tokens = [{"_source": {"address": '0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d'}}]
    self.client.index(TEST_CONTRACT_INDEX, 'contract', {'address': TEST_TOKEN_ADDRESSES[0], 'total_supply': '100000000', 'blockNumber': 5000000, 'owner': '0x1554aa0026292d03cfc8a2769df8dd4d169d590a', 'parent_transaction': TEST_PARENT_TXS[0], 'cmc_id': '1234', 'token_name': TEST_TOKEN_NAMES[0], 'token_symbol': TEST_TOKEN_SYMBOLS[0], 'abi': ['mock_abi'], 'decimals': 18}, id=TEST_TOKEN_ADDRESSES[0], refresh=True)
    for tx in TEST_TOKEN_TXS:
      self.client.index(TEST_ITX_INDEX, 'itx', tx, refresh=True)
    self.token_holders._extract_tokens_txs(test_tokens, test_max_block)
    
    token_txs = self.token_holders._iterate_token_tx_descriptions('0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d')
    token_txs = [tx for txs_list in token_txs for tx in txs_list]
    methods = [tx['_source']['method'] for tx in token_txs]
    amounts = [tx['_source']['value'] for tx in token_txs]
    
    with_error = [tx for tx in token_txs if tx['_source']['valid'] == False]
    self.assertCountEqual(['transfer', 'transferFrom'], methods)
    self.assertCountEqual([356.24568, 2266.0], amounts)
    assert len(with_error) == 1

  def test_iterate_tokens_with_cmc_id(self):
    test_max_block = 10
    self.client.index(TEST_CONTRACT_INDEX, 'contract', {'address': TEST_TOKEN_ADDRESSES[0], 'total_supply': '100000000', 'blockNumber': 5000000, 'owner': '0x1554aa0026292d03cfc8a2769df8dd4d169d590a', 'parent_transaction': TEST_PARENT_TXS[0], 'cmc_id': '1234', 'token_name': TEST_TOKEN_NAMES[0], 'token_symbol': TEST_TOKEN_SYMBOLS[0], 'abi': ['mock_abi'], 'decimals': 18}, id=TEST_TOKEN_ADDRESSES[0], refresh=True)
    self.client.index(TEST_CONTRACT_INDEX, 'contract', {'address': TEST_TOKEN_ADDRESSES[1], 'total_supply': '100000000', 'blockNumber': 5000000, 'owner': '0x1554aa0026292d03cfc8a2769df8dd4d169d590a', 'parent_transaction': TEST_PARENT_TXS[0], 'cmc_id': '1235', 'tx_descr_scanned': True, 'token_name': TEST_TOKEN_NAMES[0], 'token_symbol': TEST_TOKEN_SYMBOLS[0], 'abi': ['mock_abi'], 'decimals': 18}, id=TEST_TOKEN_ADDRESSES[1], refresh=True)
    tokens = self.token_holders._iterate_tokens(test_max_block)
    tokens = [t['_source'] for token in tokens for t in token]
    assert tokens[0]['cmc_id'] == '1234'

  def test_get_listed_tokens_txs(self):
    self.token_holders._create_transactions_request = MagicMock(return_value={
      "terms": {
        "to": TEST_TOKEN_ADDRESSES
      }
    })
    test_max_block = 6000000
    test_max_block_mock = MagicMock(return_value=test_max_block)
    for i, address in enumerate(TEST_TOKEN_ADDRESSES):
      self.client.index(TEST_CONTRACT_INDEX, 'contract', {'address': address, 'total_supply': '100000000', 'blockNumber': 5000000, 'owner': '0x1554aa0026292d03cfc8a2769df8dd4d169d590a', 'parent_transaction': TEST_PARENT_TXS[0], 'cmc_id': str(1234+i), 'token_name': TEST_TOKEN_NAMES[i], 'token_symbol': TEST_TOKEN_SYMBOLS[i], 'abi': ['mock_abi'], 'decimals': 18}, id=address, refresh=True)
    for tx in TEST_TOKEN_TXS:
      self.client.index(TEST_ITX_INDEX, 'itx', tx, refresh=True)
    with patch('utils.get_max_block', test_max_block_mock):
      self.token_holders.get_listed_tokens_txs()
      all_descrptions = self.token_holders._iterate_tx_descriptions()
      all_descrptions = [tx for txs_list in all_descrptions for tx in txs_list]
      tokens = set([descr['_source']['token'] for descr in all_descrptions])
      amounts = [tx['_source']['value'] for tx in all_descrptions]

      test_max_block_mock.assert_any_call()
      self.assertCountEqual([2266.0, 356.24568, 2352.0, 100000000, 100000000], amounts)
      self.assertCountEqual(['0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d', '0xa74476443119a942de498590fe1f2454d7d4ac0d'], tokens)
      assert len(all_descrptions) == 5

  def test_set_transaction_index(self):
    self.token_holders._create_transactions_request = MagicMock(return_value={
      "query_string": {
        "query": "*"
      }
    })
    test_max_block = 10
    test_tokens = [{"_source": {"address": '0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d'}}]
    self.client.index(TEST_CONTRACT_INDEX, 'contract', {'address': TEST_TOKEN_ADDRESSES[0], 'cmc_id': '1234', 'token_name': TEST_TOKEN_NAMES[0], 'token_symbol': TEST_TOKEN_SYMBOLS[0], 'abi': ['mock_abi'], 'decimals': 18}, id=TEST_TOKEN_ADDRESSES[0], refresh=True)
    for tx in TEST_TOKEN_TXS:
      self.client.index(TEST_ITX_INDEX, 'itx', tx, refresh=True)
    self.token_holders._extract_tokens_txs(test_tokens, test_max_block)
    
    token_txs = self.token_holders._iterate_token_tx_descriptions('0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d')
    token_txs = [tx for txs_list in token_txs for tx in txs_list]
    tx_indices = [tx['_source']['tx_index'] for tx in token_txs]
    tx_indices = list(set(tx_indices))
    self.assertCountEqual([TEST_ITX_INDEX], tx_indices)

  def test_extract_contract_creation_descr(self):
    self.client.index(TEST_CONTRACT_INDEX, 'contract', {
      'address': TEST_TOKEN_ADDRESSES[0], 
      'total_supply': '100000000', 
      'blockNumber': 5000000, 
      'owner': '0x1554aa0026292d03cfc8a2769df8dd4d169d590a', 
      'parent_transaction': TEST_PARENT_TXS[0], 
      'decimals': 18,
      'cmc_id': str(1234)
    }, id=TEST_TOKEN_ADDRESSES[0], refresh=True)
    self.client.index(TEST_CONTRACT_INDEX, 'contract', {
      'address': TEST_TOKEN_ADDRESSES[1], 
      'total_supply': '200000000', 
      'blockNumber': 5000010, 
      'parent_transaction': TEST_PARENT_TXS[1], 
      'cmc_id': str(1235),  
      'decimals': 18,
      'owner': '0x17Bc58b788808DaB201a9A90817fF3C168BF3d61'
    }, id=TEST_TOKEN_ADDRESSES[1], refresh=True)
    for tx in TEST_TOKEN_TXS:
      self.client.index(TEST_ITX_INDEX, 'itx', tx, refresh=True)
    self.token_holders.get_listed_tokens_txs()
    
    supply_transfers = self.iterate_supply_transfers()
    supply_transfers = [t['_source'] for transfers in supply_transfers for t in transfers]
    values = [t['raw_value'] for t in supply_transfers]
    owners = [t['to'] for t in supply_transfers]
    self.assertCountEqual(['100000000', '200000000'], values)
    self.assertCountEqual(['0x1554aa0026292d03cfc8a2769df8dd4d169d590a', '0x17Bc58b788808DaB201a9A90817fF3C168BF3d61'], owners)

  def test_round_value(self):
    values = self.token_holders._convert_transfer_value('10000000000000000', 18)
    assert type(values[0]) is str
    assert type(values[1]) is float
    assert values[1] == 0.01

  def test_process_only_uint(self):
    tokens = [
      {'_source': {'address': '0xb8c77482e45f1f44de1745f52c74426c631bdd52'}},
      {'_source': {'address': '0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2'}}
    ]
    txs = [
      {"blockHash":"0x37dada95b3bf37bc9f9e2029c2af291e8e099348ffadd270f1fc897573964671","to_contract":True,"traceAddress":[],"decoded_input":{"name":"unfreeze","params":[{"type":"uint256","value":"16000000000000000000000000"}]},"type":"call","transactionHash":"0x20b2be5acb83856e56c64429b096c8d0852e1b810356c8fcea9d278aeee094a6","callType":"call","output":"0x0000000000000000000000000000000000000000000000000000000000000001","input":"0x6623fc460000000000000000000000000000000000000000000d3c21bcecceda10000000","gasUsed":"0x33c2","transactionPosition":129,"blockNumber":5987277,"gas":"0x5ada","from":"0x00c5e04176d95a286fcce0e68c683ca0bfec8454","to":"0xb8c77482e45f1f44de1745f52c74426c631bdd52","value":0.0,"subtraces":0},
      {"blockHash":"0xee385ac028bb7d8863d70afa02d63181894e0b2d51b99c0c525ef24538c44c24","to_contract":True,"traceAddress":[1],"decoded_input":{"name":"mint","params":[{"type":"uint256","value":"1000000000000000000000000"}]},"type":"call","callType":"call","transactionHash":"0x5c9b0f9c6c32d2690771169ec62dd648fef7bce3d45fe8a6505d99fdcbade27a","output":"0x","input":"0xa0712d6800000000000000000000000000000000000000000000d3c21bcecceda1000000","gasUsed":"0xab31","transactionPosition":55,"blockNumber":4620855,"gas":"0x209a04","from":"0x731c6f8c754fa404cfcc2ed8035ef79262f65702","to":"0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2","value":0.0,"subtraces":0}      
    ]
    for tx in txs:
      self.client.index(TEST_ITX_INDEX, 'itx', tx, refresh=True, id=tx['transactionHash'])
    self.token_holders._extract_tokens_txs(tokens, 7000000)
    token_txs = self.iterate_token_txs()
    token_txs = [tx['_source'] for txs in token_txs for tx in txs]
    amount = [tx['value'] for tx in token_txs]
    self.assertCountEqual([16000000.0, 1000000.0], amount)

  def test_process_only_uint_negative(self):
    txs = [
      {"blockHash":"0xbcae7deb3db192a04d913de137f6dcd6a2b2f3da8507a929a006548b2263a69e","to_contract":True,"traceAddress":[0],"decoded_input":{"name":"burnTokens","params":[{"type":"uint256","value":"6000000000"}]},"type":"call","callType":"call","transactionHash":"0x2b135d9f0e1a766dee8190fec050bfea9575f4f95d89e90f51f43d349d8368f3","output":"0x0000000000000000000000000000000000000000000000000000000000000001","input":"0x6d1b229d0000000000000000000000000000000000000000000000000000000165a0bc0000000000000000000000000000000000000000000000000000000000","gasUsed":"0x2d93","transactionPosition":77,"blockNumber":5375200,"gas":"0x34d16","from":"0xecf8db4968a8817e21bdd5ecda830e413089b534","to":"0x014b50466590340d41307cc54dcee990c8d58aa8","value":0.0,"subtraces":0},
      {"blockHash":"0xde18db2a41c7250412ff1297ad983173ccce8281c1d19498427a765e73cf9b98","to_contract":True,"traceAddress":[],"decoded_input":{"name":"freeze","params":[{"type":"uint256","value":"64000000000000000000000000"}]},"type":"call","callType":"call","transactionHash":"0x72af0f55b97b033af3b6e6162463681730c6429d0bc9c6c6ae9ad595aa2fbc57","output":"0x0000000000000000000000000000000000000000000000000000000000000001","input":"0xd7a78db800000000000000000000000000000000000000000034f086f3b33b6840000000","gasUsed":"0x6ede","transactionPosition":70,"blockNumber":3978360,"gas":"0x9629","from":"0x00c5e04176d95a286fcce0e68c683ca0bfec8454","to":"0xb8c77482e45f1f44de1745f52c74426c631bdd52","value":0.0,"subtraces":0},
      {"blockHash":"0x51cc9f042550639ab691b83b52edf5df9e0c2b7671c547e04d08c41bd6c6dee8","to_contract":True,"traceAddress":[],"decoded_input":{"name":"sell","params":[{"type":"uint256","value":"2550"}]},"type":"call","callType":"call","transactionHash":"0xf6519730315fdcdd4c6e7dde1585ebe93bee7832addba0b6c06498f19d03a6ff","output":"0x","input":"0xe4849b3200000000000000000000000000000000000000000000000000000000000009f6","gasUsed":"0x52fe","transactionPosition":118,"blockNumber":5934288,"gas":"0x53fd","from":"0x0eaf6b9bee938435f71c1c3f8b998ee338d7b8c3","to":"0x12480e24eb5bec1a9d4369cab6a80cad3c0a377a","value":0.0,"subtraces":1},
      {"blockHash":"0x78eb2c45274cac457f788426f09d22c2fc00864dc733d62f2b91ad0c8d011209","to_contract":True,"traceAddress":[],"decoded_input":{"name":"sell","params":[{"type":"uint256","value":"1"}]},"type":"call","callType":"call","transactionHash":"0xcd64ac8f0517a35eb3350e190f7a70a29a38be33ea97dc6cbb60968bb938234c","output":"0x","input":"0xe4849b320000000000000000000000000000000000000000000000000000000000000001","gasUsed":"0x52fe","transactionPosition":174,"blockNumber":5771056,"gas":"0x53fd","from":"0x63353fba2f6a015949f0aa6ad18a1739da4aaf5e","to":"0x12480e24eb5bec1a9d4369cab6a80cad3c0a377a","value":0.0,"subtraces":1},
      {"blockHash":"0x4fe50638a0382e5a9112d6183505e91e86538069ae5db2514a782f8bbae3a16e","to_contract":True,"traceAddress":[],"decoded_input":{"name":"burn","params":[{"type":"uint256","value":"250000000000000000000000"}]},"type":"call","transactionHash":"0x9efa420d547eed423421c2c8e9626a4de7eed8f167303ef36b6a44cc10ea1bee","callType":"call","output":"0x","input":"0x42966c680000000000000000000000000000000000000000000034f086f3b33b68400000","gasUsed":"0x7043","transactionPosition":13,"blockNumber":6027920,"gas":"0x7043","from":"0x964d9d1a532b5a5daeacbac71d46320de313ae9c","to":"0x8dd5fbce2f6a956c3022ba3663759011dd51e73e","value":0.0,"subtraces":5}
    ]
    tokens = [{'_source': {'address': item}} for item in set([tx['to'] for tx in txs])]
    for tx in txs:
      self.client.index(TEST_ITX_INDEX, 'itx', tx, refresh=True, id=tx['transactionHash'])
    self.token_holders._extract_tokens_txs(tokens, 7000000)
    token_txs = self.iterate_token_txs()
    token_txs = [tx['_source'] for txs in token_txs for tx in txs]
    only_negative = list(set([tx['value'] <= 0 for tx in token_txs]))
    self.assertCountEqual([True], only_negative)

  def test_process_multiple_addr_tx(self):
    txs = [
      {"blockHash":"0xeb8da1f537b7850889dd234dc5328f2c5133467dffa63366369457d20ee820ab","to_contract":True,"traceAddress":[],"decoded_input":{"name":"transfers","params":[{"type":"address[]","value":"['0xad5583aa4a0372102b671862c70dd5024747c298', '0xbb50e800ad522740ae8ec058f5320ae8319e64e6', '0x3091e1a9be756581b44c61ed5591c7a842fed0c5', '0x3ab1d58e9f92148df1c9b45ff9a0af45a59796b4', '0xde962ec72491985a28e9a630a1dd092cd313192e', '0x970a0f23c69b42c595612489c97300cb8265eb5e', '0x53fb39bbe132dfd658a0fc35c2634561d1000e32', '0x2064d2cfc17e25de93bf8874c5826bf5363f55bc', '0x6a0ec8c9e15feb70a489f8bfb49e857c921339d6', '0x4334d90fcf57dc5abdf6addaf1ae60c237411147', '0xc968214fa62bf0edaa7ae9025130381bb7abec9a', '0xf9f1e87d80300bbba0370193a5cebe1425b48643', '0xabdbbc24b3a3489f961c096cce37e50f590e0b9f', '0x8a38504cb731808a1ab2fd2d41cdf38c737a78a1', '0xdae809267a3ce4ef5237f248c54fcb4fa5e12505', '0x1b460e46c3f16a589d2933861005d082bef7aab5', '0xaaef5997e3bc73d5b8766779e1322ea426a1759d', '0x96c7b33c068aa97c5758442adec89d1f6033be6a', '0x442b88b865b8de103a12970a0f50ef83ab677fd9', '0xef9d921e4b6a0006d3df1bfebee824ea5c032841', '0x27680b6c9ddf2910c3a7eac51e6ef0d90edf9945', '0xc05a822bb90bf9a20402d09edcbbd5f004fb2ac4', '0x00204885b78a57f67129e06a5fc5a2bc9d6ba0b2', '0x8d99977a9fb49ba83b6b6507994b08c7e9ddc8ac', '0x237ec5207db39a850e77e2ced0bdf8159cedebdb']"},{"type":"uint256[]","value":"[347050583290000000000, 61990659630000000000, 28511650680000000000, 28212315760000000000, 31654667290000000000, 68676737920000000000, 46900269540000000000, 28207860590000000000, 28171659310000000000, 36360221620000000000, 112520807750000000000, 255896559320000000000, 27920049390000000000, 139081157240000000000, 30302841130000000000, 238761454510000020000, 28381041760000000000, 76576965590000000000, 66921546880000000000, 64765185920000000000, 27469005810000000000, 94306416960000000000, 56729497150000000000, 78623734090000000000, 140622418070000000000]"}]},"type":"call","callType":"call","transactionHash":"0x59cc939cfffc79e239de3c3cf13f59a667a096abf04100dd3b8909d3cd4ad263","output":"0x0000000000000000000000000000000000000000000000000000000000000001","gasUsed":"0x85cc0","transactionPosition":76,"blockNumber":5744643,"gas":"0xe25a8","from":"0x00d5718ab3b3e9afce7c2b4e106d2a97ad477526","to":"0xd0a4b8946cb52f0661273bfbc6fd0e0c75fc6433","value":0.0,"subtraces":0}
    ]
    tokens = [{'_source': {'address': item}} for item in set([tx['to'] for tx in txs])]
    for tx in txs:
      self.client.index(TEST_ITX_INDEX, 'itx', tx, refresh=True, id=tx['transactionHash'])
    self.token_holders._extract_tokens_txs(tokens, 7000000)
    token_txs = self.iterate_token_txs()
    token_txs = [tx['_source'] for txs in token_txs for tx in txs]
    assert len(token_txs) == 25

  def test_process_multi_addr_one_uint(self):
    descriptions = self.token_holders._process_multi_addr_one_uint(TEST_MINT_ADDRESSES)
    values = list(set([tx['value'] for tx in descriptions]))
    addresses = [tx['to'] for tx in descriptions]
    assert len(values) == 1
    assert '0x36230df54a0265a96af387dd23bacc2a58cfbd9a' in addresses
    assert len(descriptions) == 150

  def test_iterate_unprocessed_tokens(self):
    test_iterator = "iterator"
    test_max_block = 10
    self.token_holders._iterate_contracts = MagicMock(return_value=test_iterator)

    iterator = self.token_holders._iterate_tokens(test_max_block)

    self.token_holders._iterate_contracts.assert_any_call(test_max_block, ANY)
    assert iterator == test_iterator

  def test_iterate_unprocessed_transactions(self):
    test_iterator = "iterator"
    test_max_block = 10
    test_contracts = ["contract"]
    self.token_holders._iterate_transactions = MagicMock(return_value=test_iterator)

    iterator = self.token_holders._iterate_tokens_txs(test_contracts, test_max_block)

    self.token_holders._iterate_transactions.assert_any_call(test_contracts, test_max_block, ANY)
    assert iterator == test_iterator

  def test_save_max_block(self):
    test_max_block = 10
    test_max_block_mock = MagicMock(return_value=test_max_block)
    test_tokens = [[{"_source": {"address": "token1"}}]]
    test_tokens_addresses = ["token1"]
    mockify(self.token_holders, {
      '_iterate_tokens': MagicMock(return_value=test_tokens)
    }, 'get_listed_tokens_txs')

    with patch('utils.get_max_block', test_max_block_mock):
      self.token_holders.get_listed_tokens_txs()

      self.token_holders._save_max_block.assert_any_call(test_tokens_addresses, test_max_block)

TEST_CONTRACT_INDEX = 'test-ethereum-contracts'
TEST_ITX_INDEX = 'test-ethereum-internal-txs'
TEST_TOKEN_TX_INDEX = 'test-token-txs'

TEST_TOKEN_ADDRESSES = ['0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d',
  '0xa74476443119a942de498590fe1f2454d7d4ac0d'
  ]
TEST_PARENT_TXS = ['0x8a634bd8b381c09eec084fd7df6bdce03ccbc92f247f59d4fcc22e02131c0158', '0xf349e35ce06112455d01e63ee2d447f626a88b646749c1cf2bffe474afeb703a']
TEST_TOKEN_NAMES = ['Aeternity', 'Golem Network Token']
TEST_TOKEN_SYMBOLS = ['AE', 'GNT']
TEST_TOKEN_TXS = [
  {'from': '0x6b25d0670a34c1c7b867cd9c6ad405aa1759bda0', 'to': '0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d', 'decoded_input': {'name': 'transfer', 'params': [{'type': 'address', 'value': '0xa60c4c379246a7f1438bd76a92034b6c82a183a5'}, {'type': 'uint256', 'value': '2266000000000000000000'}]}, 'blockNumber': 5635149, 'hash': '0xd8f583bcb81d12dc2d3f18e0a015ef0f6e71c177913ef8f251e37b6e4f7f1f26'},
  {'from': '0xc917e19946d64aa31d1aeacb516bae2579995aa9', 'to': '0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d', 'error': 'Out of gas', 'decoded_input': {'name': 'transferFrom', 'params': [{'type': 'address', 'value': '0xc917e19946d64aa31d1aeacb516bae2579995aa9'}, {'type': 'address', 'value': '0x4e6b129bbb683952ed1ec935c778d74a77b352ce'}, {'type': 'uint256', 'value': '356245680000000000000'}]}, 'blockNumber': 5635142, 'hash': '0xca811570188b2e5d186da8292eda7e0bf7dde797a68d90b9ac2e014e321a94b2'},
  {'from': '0x6b25d0670a34c1c7b867cd9c6ad405aa1759bda0', 'to': '0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d', 'blockNumber': 5635149, 'hash': '0x2497b3dcbce36c4d2cbe42931fa160cb39703ae5487bf73044520410101e7c8c'},
  {'from': '0x892ce7dbc4a0efbbd5933820e53d2c945ef9f722', 'to': '0x51ada638582e51c931147c9abd2a6d63bc02e337', 'decoded_input': {'name': 'transfer', 'params': [{'type': 'address', 'value': '0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be'}, {'type': 'uint256', 'value': '2294245680000000000000'}]}, 'blockNumber': 5632141, 'hash': '0x4188f8c914b5f58f911674ff766d45da2a19c1375a8487841dc4bdb5214c3aa2'},
  {'from': '0x930aa9a843266bdb02847168d571e7913907dd84', 'to': '0xa74476443119a942de498590fe1f2454d7d4ac0d', 'decoded_input': {'name': 'transfer', 'params': [{'type': 'address', 'value': '0xc18118a2976a9e362a0f8d15ca10761593242a85'}, {'type': 'uint256', 'value': '2352000000000000000000'}]}, 'blockNumber': 5235141, 'hash': '0x64778c57705c4bad6b2ef8fd485052faf5c40d2197a44eb7105ce71244ded043'}
]
TEST_TOKEN_ITXS = [
  {"blockHash": "0xfdcb99de3c0bab02f7e3f38f8a74d4fd15e36dc082683763884ff6322b0c0aef", "input": "0x", "gasUsed": "0x0", "type": "call", "gas": "0x8fc", "traceAddress": [2], "transactionPosition": 42, "value": "0x13b4da79fd0e0000", "to": "0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d", "subtraces": 0, "blockNumber": 5032235, "from": "0xf04436b2edaa1b777045e1eefc6dba8bd2aebab8", "callType": "call", "output": "0x", "transactionHash": "0x366c6344bdb4cb1bb8cfbce5770419b03f49d631d5803e5fbcf8de9b8f1a5d66.4", 'decoded_input': {'name': 'transfer', 'params': [{'type': 'address', 'value': '0xa60c4c379246a7f1438bd76a92034b6c82a183a5'}, {'type': 'uint256', 'value': '2266000000000000000000'}]}},
  {"blockHash": "0xfdcb99de3c0bab02f7e3f38f8a74d4fd15e36dc082683763884ff6322b0c0aef", "input": "0x", "gasUsed": "0x0", "type": "call", "gas": "0x8fc", "traceAddress": [0, 0], "transactionPosition": 89, "value": "0x1991d2e42bc5c00", "to": "0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d", "subtraces": 0, "blockNumber": 5032235, "from": "0xa36ae0f959046a18d109dc5b1fb8df655cf0aa81", "callType": "call", "output": "0x", "transactionHash": "0xce37439c6809ca9d1b1d5707c7df34ceec1e4e472f0ca07c87fa449a93b02431.4", 'decoded_input': {'name': 'transfer', 'params': [{'type': 'address', 'value': '0xa60c4c379246a7f1438bd76a92034b6c82a183a5'}, {'type': 'uint256', 'value': '2266000000000000000000'}]}},
  {"blockHash": "0xfdcb99de3c0bab02f7e3f38f8a74d4fd15e36dc082683763884ff6322b0c0aef", "input": "0xc281d19e", "gasUsed": "0x5a4", "type": "call", "gas": "0x303d8", "traceAddress": [1], "transactionPosition": 102, "value": "0x0", "to": "0x5ca9a71b1d01849c0a95490cc00559717fcf0d1d", "subtraces": 0, "blockNumber": 5032235, "from": "0xd91e45416bfbbec6e2d1ae4ac83b788a21acf583", "callType": "call", "output": "0x00000000000000000000000026588a9301b0428d95e6fc3a5024fce8bec12d51", "transactionHash": "0x04692fb0a2d1a9c8b6ea8cfc643422800b81da50df1578f3494aef0ef9be6009.4", 'decoded_input': {'name': 'transfer', 'params': [{'type': 'address', 'value': '0xa60c4c379246a7f1438bd76a92034b6c82a183a5'}, {'type': 'uint256', 'value': '2266000000000000000000'}]}}
]

TEST_MINT_ADDRESSES = {
    "blockTimestamp" : "2017-12-26T22:39:56",
    "from" : "0xec4f63c53223c54cf0eb7a57c2f984ab5e5bfdac",
    "creates" : None,
    "input" : "0xf190ac5f00000000000000000000000000000000000000000000000000000000000000400000000000000000000000000000000000000000000000000de0b6b3a7640000000000000000000000000000000000000000000000000000000000000000009600000000000000000000000036230df54a0265a96af387dd23bacc2a58cfbd9a0000000000000000000000002fd6320ee113b83f0a4636dece0e6330fb1ca605000000000000000000000000ba9e442d7357984815716bfcb7471f3b349b2618000000000000000000000000ee056a44e39219de1d0027cbe81756d8cf26da49000000000000000000000000d0926f304d8e101bc9366345213ce45ee579065d00000000000000000000000037254d31a6bec7c5789f68287aac897d7ca3244d00000000000000000000000043ba366eb497fa986eb2031d01e1e9a74054d318000000000000000000000000aa6aa499b8241ae0699fe4346e366c9cf7bc6e700000000000000000000000008a39c67843d18384960b0c65bf5db46fdadbde84000000000000000000000000aec6372d9d80f4e6e04e5195e5e778a65647ae9e0000000000000000000000004125e658640d5b0a86441fc10ea02f9230f9b8e7000000000000000000000000c11b7067acaac311d2b77b91b8655663ba8731990000000000000000000000009050ebc8e2b0b6a123634d0fad9a44b35aef548a000000000000000000000000be59e1a83508c70b2cf0bf7415c3512cabbbf05200000000000000000000000064dcee549acf529da0605e8736beed64276bd755000000000000000000000000223eb313426ff2a6fe8e7683020c54bf7930521d000000000000000000000000fe7c793ed4f16b6d05ec763d98389590b0c812e1000000000000000000000000071bd3aa323b82df25b27407d314f104e69deaac000000000000000000000000c06d5cc009a7ade2b08fc49118e9ea690a6994f80000000000000000000000003ed01da8472800e6213931d624dbec3c3e4eb0cf0000000000000000000000006eb60cf761d51500d31250c3a3bd6e2ce6d21377000000000000000000000000879019114f873e291c94866af98e87382188e38b0000000000000000000000008e563f01316be4d44c084030e7ff896afe450ad9000000000000000000000000fbcd0645dfe99fb6470b2df617c4df78fb0582090000000000000000000000007a1f999a9501d50861cd54bd6dd2a001eb6ed80700000000000000000000000046eb3f5e97db81cc6c9d32102ed01614b80c2af9000000000000000000000000ab4117dfbcdfc8e8966fc5128d2e1d4c4807580f00000000000000000000000061dc365e74b318187a07970f68001c36e2613da00000000000000000000000006bbfcc3d25799fd4e9c4fd17d3fd350a57665f160000000000000000000000004260e9cffe03787181ebc152f5fd00bfef3f52cf000000000000000000000000c1608e55471cc27ec5437f0ae2355315473f841d00000000000000000000000064d603faeb69451e1cb6bc253d76c92048875a13000000000000000000000000c4dd4c7eb15bfd48aa35509dd390e2f014227bea0000000000000000000000005e7d4f04d0cd0e57a8d28cf3b56f8e1b478b7bbf00000000000000000000000036b68ca8c8f8e9b4ec7e083773bc19e485768e630000000000000000000000007aa76d0c2bee3a7995b8a798fcd56ee32c0b56050000000000000000000000005542803080981f61a0a859bf41065ba1ac1475e0000000000000000000000000d003436e741a706f683647374896a9ff5891823000000000000000000000000089f6aaa4f58211aaa24c87010670688ef3374f80000000000000000000000000534757e5f5d980e73d837c786a58a8abf2691d100000000000000000000000000061533a3829c585db7ecb7d3cf9651d31c1bc23000000000000000000000000810b326b15856eca9b3b083182997ae0d181f7960000000000000000000000008824885c9a56eb7b63bd517d542626d12a4e55010000000000000000000000006292bda9278e3372acf3114fd8a4de9271625578000000000000000000000000324e45fb5bb54982c7ee084ca54277d966880d2f00000000000000000000000016893e10b99a59afd2c60331e0b49241d4d4d7cc00000000000000000000000080ea495e24eb7a8a3f6564c46fe0715578c74688000000000000000000000000d1ee5ea14f1edfe1efd1c39e97bdd4b7df3f6dcc0000000000000000000000000e9e0c5723c1dbf7120ea52cb81ab1f08b5a452b000000000000000000000000f1775a48a3488edb81034e25dc9772c83c74df120000000000000000000000003df3b28a46859176078336197a9e3d436283efb2000000000000000000000000bb1396676bdce688a2050ad1a10f2f73f60f2f7300000000000000000000000082da55c051b977a84b3deaec3169c478f6e3e2a90000000000000000000000001dcf5557d81c9547e8cd86133c7e66471f121e7500000000000000000000000037ed9d4025c65e12706e5c5e2d119ff47da9b78f000000000000000000000000faa43e0faabd8bc859be9b85db079a818d77e604000000000000000000000000a2262ca10a472b73d8a640d5c7dd71d03775238f000000000000000000000000e5bb2be67ad6ea88b9e3effa9b214cdfd6756ee70000000000000000000000006ed165d527127a7e20d658ef6d7fa7997fd4f97c0000000000000000000000006e7f248c959f4b364adf9b0fcfd6340dfbaaec1c000000000000000000000000ee665a8abfc6c02dade26072f0b6855f61c561a40000000000000000000000008b52ceb9f1004eb7b60f369e323581340339cf75000000000000000000000000cc852edb0c0115f03a0fd9aeff48bfc101914b2e000000000000000000000000200c601aa7449aa2cc2ccbd5f46645941654cde100000000000000000000000043f16f609ab45e89b95985d3ef4a28de97011627000000000000000000000000b7a23cc3e8c61f4aaef5f6a17173a29fbf2da628000000000000000000000000b5a05c6e7ea3ddcf4a42cfebb097796a2afd47da0000000000000000000000001323367b36f387319494c2c37b60cd482218473b000000000000000000000000e87897b164f841caf4b72b672b0422707d13833d0000000000000000000000004ec5f054ee87c51e4321f2f113e0337bbb314b6d00000000000000000000000063b21a269a7bbd63cf53997c43a7a5a95e40062400000000000000000000000000a3d158cf962f698c50b9402ebfb0e40c928536000000000000000000000000e630b30bc224c9892d7547569f1e16ffd501d47300000000000000000000000000fab3e776084660815773dbb5f56b05f78afd9c0000000000000000000000007153d3412ae77673100917f0f27b280de4befd2e0000000000000000000000002955a2d35904914637d37b4b290d3418c81cdc0c00000000000000000000000000a539248b104621fa75d171c33692425975dc32000000000000000000000000a8ebcfb7f8a7a9d6721cbf15a154986a2df909cb00000000000000000000000022b080ce0119f82d938524e61be35d03e3521efd0000000000000000000000006d79e413646214530e2b6fd39cb4d4f8e8263f660000000000000000000000001a1a57dd243f74ea2e594795ffda2fb80bf89a1a000000000000000000000000f40acf3e0a12e2534d1f2ccbcff78ad610defbf0000000000000000000000000f5a1deec0bea778b80547ab8eca779eb99b0280a000000000000000000000000fcec74b7ecba248ee727c3a8beb62a4e85554b060000000000000000000000007d424336be9f81982a08c8338c804ef8617f843900000000000000000000000084466fe4857177b2f11692ff198ad289408db13f000000000000000000000000a2afd1fa1e188457a9c6db1bd50424250eb784ce000000000000000000000000a66f03dc235473642d0322d50716d5a25d4ba1460000000000000000000000000cb5428bf8f8cdda4eeb46d4db8094602c7f369a000000000000000000000000552de0a5966d13f4a59719dd4d032651d1aecd97000000000000000000000000b8138dc6f1a1c868d319684b5f62256d081cf9d2000000000000000000000000b49fcc248a2bba533527f4e06e96b5c2182844c5000000000000000000000000c530c704740f865280c37b471b92f9790a695b8c000000000000000000000000abc70d6044edaff29e7c153005d8286a3847d7dc000000000000000000000000ecc874511bb8077445a757e9540b30dfe69dfd9f000000000000000000000000a65d5f1486e8ea401a20e337ab135c64f357de48000000000000000000000000c44bd46afbbc9c41fb76eb064598db39c9f52b6c0000000000000000000000007a08ed303cdea0a4809158740335e7759cf4da2600000000000000000000000024f57d0be8fb9f9ef4f1e912dfc4f8ef06fdcce7000000000000000000000000a69eb8efbbb5c4fd4092d110a023773ba23509f600000000000000000000000062d4f2b9e56b6b4111b961dd41eea98667831be8000000000000000000000000b10ce34857128de7346944d9050f107c131e279f000000000000000000000000823538ef6fbc3e8944138a92380bf1217726907a000000000000000000000000539cdb209674378507ee586a06f2fb4b2f1b594900000000000000000000000080e6db644c334f73966127b485734370a31381b9000000000000000000000000d47b4cc77d53a6785c969fe99d7379801148c3780000000000000000000000001d36c5d2f77280376b857ba83a28d7a3ed7e580f000000000000000000000000c2974033b2488690b521c5d32c6b7993e40441d2000000000000000000000000c6ad60ea09f61d1d42eca99a31f853af86e141f60000000000000000000000006b7580d3bc2ee3e4dbf82c426625dbcecc0342140000000000000000000000009ca6404f7eaedc3aefe9839d78cab5eaceb84e8400000000000000000000000060c4775b2377bca9d7ff724606aa17fdba038ce6000000000000000000000000ac9bb6a6b131d9529d05dc8728e432167eaa9e680000000000000000000000008a80aa5835c08fed3a7d8820f02c17babdb2c0510000000000000000000000009ab74e8494bce9219377675b5f50514b807f578c00000000000000000000000044f303f4847405176981e2f3e773773df5d3fc420000000000000000000000009b21e11514c418d3279e0a8ea41cb8618cc39a1500000000000000000000000080ec51509ec3644e201b15e578246890727edbca00000000000000000000000012a2aa3e5898426f6ae6def1a7915d82f0f5113400000000000000000000000028bc4fcc5dcd62abbbd140e7364f73575bf8c2c3000000000000000000000000c1535158cfb9352bf6a441373afb1737259ec403000000000000000000000000eac45e4aa47eef6810ad75d930e83fed544024f30000000000000000000000000de98266d8021090068f15b466c6ae389b5b0744000000000000000000000000bf6b500ad8df9cdd777655d6faa97fd9f475748a000000000000000000000000f406317925ad6a9ea40cdf40cc1c9b0dd65ca10c000000000000000000000000c88fcf7668e5fa3b180e964dcc990896e36bcd39000000000000000000000000f22b904c4926a925825deb75d9a9645d10f788160000000000000000000000008eca04e62b5887fbc0862884919f6a27677260b90000000000000000000000001c1ef062943fc4f0777b50ee98e794ddf16b94b2000000000000000000000000301ab3ad422ee85447b96d93e7ee710925fc6e6b0000000000000000000000004c2230715e37675957233227b78784e8ff6fc4750000000000000000000000008b163f35b076c53e44d0975b3c07a27e7364153f00000000000000000000000005fc91878c77a6d49116bc5451afc7bb8ee904f3000000000000000000000000a98887cd3504c8a5f39e0fafc21978fef8d483c100000000000000000000000055772ec91f52b084d752ff9daaa41af713febb280000000000000000000000004fbd4432a6cc4606bdaa83f7233da29cfbf3a4c40000000000000000000000008a35be53529cd6ebfeb5033a89b42995123b376f000000000000000000000000bee3b5acece21526ebb14e983441f787d5f192e7000000000000000000000000cafaac75f9d2f91dd92dc865d0c98c0aff33982e00000000000000000000000059e339b921ccb69f6e00663126af7888862f6b1c000000000000000000000000dacf6478b90a55a2e054960134f4ea2378074f180000000000000000000000003c1f833e7cc6b37cc9145103106a0957d6e0ea9d00000000000000000000000053e53a6f9ec5a9d02993a82042cc96c78c8505200000000000000000000000001538f85a6241f7470464b6469094174b1310e040000000000000000000000000a31b5816c1c461069e4bcd42ea8ca00fa0a257d6000000000000000000000000e174f334e6874196f37d1df019b3177ed5c0881d000000000000000000000000edc148759dfdffa3eeff01ea64b2abf20642799f0000000000000000000000008dcf18eca7b6a5afd17f0dba07c94e53d9f4117b000000000000000000000000cfebcd59bccbe2549eadc1e7bbcffd0cee699ff10000000000000000000000004cb8b2421df9878f61300e64765fc70eb23bf329",
    "transactionIndex" : 26,
    "hash" : "0x62e2f27cd5ada06ec9a7a4cb351d51ce697c07beadaeb1e30f5e2e2e9031ba58",
    "blockNumber" : 4802804,
    "value" : 0.0,
    "to" : "0x1234567461d3f8db7496581774bd869c83d51c93",
    "decoded_input" : {
      "name" : "mintToAddresses",
      "params" : [
        {
          "type" : "address[]",
          "value" : "['0x36230df54a0265a96af387dd23bacc2a58cfbd9a', '0x2fd6320ee113b83f0a4636dece0e6330fb1ca605', '0xba9e442d7357984815716bfcb7471f3b349b2618', '0xee056a44e39219de1d0027cbe81756d8cf26da49', '0xd0926f304d8e101bc9366345213ce45ee579065d', '0x37254d31a6bec7c5789f68287aac897d7ca3244d', '0x43ba366eb497fa986eb2031d01e1e9a74054d318', '0xaa6aa499b8241ae0699fe4346e366c9cf7bc6e70', '0x8a39c67843d18384960b0c65bf5db46fdadbde84', '0xaec6372d9d80f4e6e04e5195e5e778a65647ae9e', '0x4125e658640d5b0a86441fc10ea02f9230f9b8e7', '0xc11b7067acaac311d2b77b91b8655663ba873199', '0x9050ebc8e2b0b6a123634d0fad9a44b35aef548a', '0xbe59e1a83508c70b2cf0bf7415c3512cabbbf052', '0x64dcee549acf529da0605e8736beed64276bd755', '0x223eb313426ff2a6fe8e7683020c54bf7930521d', '0xfe7c793ed4f16b6d05ec763d98389590b0c812e1', '0x071bd3aa323b82df25b27407d314f104e69deaac', '0xc06d5cc009a7ade2b08fc49118e9ea690a6994f8', '0x3ed01da8472800e6213931d624dbec3c3e4eb0cf', '0x6eb60cf761d51500d31250c3a3bd6e2ce6d21377', '0x879019114f873e291c94866af98e87382188e38b', '0x8e563f01316be4d44c084030e7ff896afe450ad9', '0xfbcd0645dfe99fb6470b2df617c4df78fb058209', '0x7a1f999a9501d50861cd54bd6dd2a001eb6ed807', '0x46eb3f5e97db81cc6c9d32102ed01614b80c2af9', '0xab4117dfbcdfc8e8966fc5128d2e1d4c4807580f', '0x61dc365e74b318187a07970f68001c36e2613da0', '0x6bbfcc3d25799fd4e9c4fd17d3fd350a57665f16', '0x4260e9cffe03787181ebc152f5fd00bfef3f52cf', '0xc1608e55471cc27ec5437f0ae2355315473f841d', '0x64d603faeb69451e1cb6bc253d76c92048875a13', '0xc4dd4c7eb15bfd48aa35509dd390e2f014227bea', '0x5e7d4f04d0cd0e57a8d28cf3b56f8e1b478b7bbf', '0x36b68ca8c8f8e9b4ec7e083773bc19e485768e63', '0x7aa76d0c2bee3a7995b8a798fcd56ee32c0b5605', '0x5542803080981f61a0a859bf41065ba1ac1475e0', '0xd003436e741a706f683647374896a9ff58918230', '0x89f6aaa4f58211aaa24c87010670688ef3374f80', '0x534757e5f5d980e73d837c786a58a8abf2691d10', '0x0061533a3829c585db7ecb7d3cf9651d31c1bc23', '0x810b326b15856eca9b3b083182997ae0d181f796', '0x8824885c9a56eb7b63bd517d542626d12a4e5501', '0x6292bda9278e3372acf3114fd8a4de9271625578', '0x324e45fb5bb54982c7ee084ca54277d966880d2f', '0x16893e10b99a59afd2c60331e0b49241d4d4d7cc', '0x80ea495e24eb7a8a3f6564c46fe0715578c74688', '0xd1ee5ea14f1edfe1efd1c39e97bdd4b7df3f6dcc', '0x0e9e0c5723c1dbf7120ea52cb81ab1f08b5a452b', '0xf1775a48a3488edb81034e25dc9772c83c74df12', '0x3df3b28a46859176078336197a9e3d436283efb2', '0xbb1396676bdce688a2050ad1a10f2f73f60f2f73', '0x82da55c051b977a84b3deaec3169c478f6e3e2a9', '0x1dcf5557d81c9547e8cd86133c7e66471f121e75', '0x37ed9d4025c65e12706e5c5e2d119ff47da9b78f', '0xfaa43e0faabd8bc859be9b85db079a818d77e604', '0xa2262ca10a472b73d8a640d5c7dd71d03775238f', '0xe5bb2be67ad6ea88b9e3effa9b214cdfd6756ee7', '0x6ed165d527127a7e20d658ef6d7fa7997fd4f97c', '0x6e7f248c959f4b364adf9b0fcfd6340dfbaaec1c', '0xee665a8abfc6c02dade26072f0b6855f61c561a4', '0x8b52ceb9f1004eb7b60f369e323581340339cf75', '0xcc852edb0c0115f03a0fd9aeff48bfc101914b2e', '0x200c601aa7449aa2cc2ccbd5f46645941654cde1', '0x43f16f609ab45e89b95985d3ef4a28de97011627', '0xb7a23cc3e8c61f4aaef5f6a17173a29fbf2da628', '0xb5a05c6e7ea3ddcf4a42cfebb097796a2afd47da', '0x1323367b36f387319494c2c37b60cd482218473b', '0xe87897b164f841caf4b72b672b0422707d13833d', '0x4ec5f054ee87c51e4321f2f113e0337bbb314b6d', '0x63b21a269a7bbd63cf53997c43a7a5a95e400624', '0x00a3d158cf962f698c50b9402ebfb0e40c928536', '0xe630b30bc224c9892d7547569f1e16ffd501d473', '0x00fab3e776084660815773dbb5f56b05f78afd9c', '0x7153d3412ae77673100917f0f27b280de4befd2e', '0x2955a2d35904914637d37b4b290d3418c81cdc0c', '0x00a539248b104621fa75d171c33692425975dc32', '0xa8ebcfb7f8a7a9d6721cbf15a154986a2df909cb', '0x22b080ce0119f82d938524e61be35d03e3521efd', '0x6d79e413646214530e2b6fd39cb4d4f8e8263f66', '0x1a1a57dd243f74ea2e594795ffda2fb80bf89a1a', '0xf40acf3e0a12e2534d1f2ccbcff78ad610defbf0', '0xf5a1deec0bea778b80547ab8eca779eb99b0280a', '0xfcec74b7ecba248ee727c3a8beb62a4e85554b06', '0x7d424336be9f81982a08c8338c804ef8617f8439', '0x84466fe4857177b2f11692ff198ad289408db13f', '0xa2afd1fa1e188457a9c6db1bd50424250eb784ce', '0xa66f03dc235473642d0322d50716d5a25d4ba146', '0x0cb5428bf8f8cdda4eeb46d4db8094602c7f369a', '0x552de0a5966d13f4a59719dd4d032651d1aecd97', '0xb8138dc6f1a1c868d319684b5f62256d081cf9d2', '0xb49fcc248a2bba533527f4e06e96b5c2182844c5', '0xc530c704740f865280c37b471b92f9790a695b8c', '0xabc70d6044edaff29e7c153005d8286a3847d7dc', '0xecc874511bb8077445a757e9540b30dfe69dfd9f', '0xa65d5f1486e8ea401a20e337ab135c64f357de48', '0xc44bd46afbbc9c41fb76eb064598db39c9f52b6c', '0x7a08ed303cdea0a4809158740335e7759cf4da26', '0x24f57d0be8fb9f9ef4f1e912dfc4f8ef06fdcce7', '0xa69eb8efbbb5c4fd4092d110a023773ba23509f6', '0x62d4f2b9e56b6b4111b961dd41eea98667831be8', '0xb10ce34857128de7346944d9050f107c131e279f', '0x823538ef6fbc3e8944138a92380bf1217726907a', '0x539cdb209674378507ee586a06f2fb4b2f1b5949', '0x80e6db644c334f73966127b485734370a31381b9', '0xd47b4cc77d53a6785c969fe99d7379801148c378', '0x1d36c5d2f77280376b857ba83a28d7a3ed7e580f', '0xc2974033b2488690b521c5d32c6b7993e40441d2', '0xc6ad60ea09f61d1d42eca99a31f853af86e141f6', '0x6b7580d3bc2ee3e4dbf82c426625dbcecc034214', '0x9ca6404f7eaedc3aefe9839d78cab5eaceb84e84', '0x60c4775b2377bca9d7ff724606aa17fdba038ce6', '0xac9bb6a6b131d9529d05dc8728e432167eaa9e68', '0x8a80aa5835c08fed3a7d8820f02c17babdb2c051', '0x9ab74e8494bce9219377675b5f50514b807f578c', '0x44f303f4847405176981e2f3e773773df5d3fc42', '0x9b21e11514c418d3279e0a8ea41cb8618cc39a15', '0x80ec51509ec3644e201b15e578246890727edbca', '0x12a2aa3e5898426f6ae6def1a7915d82f0f51134', '0x28bc4fcc5dcd62abbbd140e7364f73575bf8c2c3', '0xc1535158cfb9352bf6a441373afb1737259ec403', '0xeac45e4aa47eef6810ad75d930e83fed544024f3', '0x0de98266d8021090068f15b466c6ae389b5b0744', '0xbf6b500ad8df9cdd777655d6faa97fd9f475748a', '0xf406317925ad6a9ea40cdf40cc1c9b0dd65ca10c', '0xc88fcf7668e5fa3b180e964dcc990896e36bcd39', '0xf22b904c4926a925825deb75d9a9645d10f78816', '0x8eca04e62b5887fbc0862884919f6a27677260b9', '0x1c1ef062943fc4f0777b50ee98e794ddf16b94b2', '0x301ab3ad422ee85447b96d93e7ee710925fc6e6b', '0x4c2230715e37675957233227b78784e8ff6fc475', '0x8b163f35b076c53e44d0975b3c07a27e7364153f', '0x05fc91878c77a6d49116bc5451afc7bb8ee904f3', '0xa98887cd3504c8a5f39e0fafc21978fef8d483c1', '0x55772ec91f52b084d752ff9daaa41af713febb28', '0x4fbd4432a6cc4606bdaa83f7233da29cfbf3a4c4', '0x8a35be53529cd6ebfeb5033a89b42995123b376f', '0xbee3b5acece21526ebb14e983441f787d5f192e7', '0xcafaac75f9d2f91dd92dc865d0c98c0aff33982e', '0x59e339b921ccb69f6e00663126af7888862f6b1c', '0xdacf6478b90a55a2e054960134f4ea2378074f18', '0x3c1f833e7cc6b37cc9145103106a0957d6e0ea9d', '0x53e53a6f9ec5a9d02993a82042cc96c78c850520', '0x1538f85a6241f7470464b6469094174b1310e040', '0xa31b5816c1c461069e4bcd42ea8ca00fa0a257d6', '0xe174f334e6874196f37d1df019b3177ed5c0881d', '0xedc148759dfdffa3eeff01ea64b2abf20642799f', '0x8dcf18eca7b6a5afd17f0dba07c94e53d9f4117b', '0xcfebcd59bccbe2549eadc1e7bbcffd0cee699ff1', '0x4cb8b2421df9878f61300e64765fc70eb23bf329']"
        },
        {
          "type" : "uint256",
          "value" : "1000000000000000000"
        }
      ]
    },
    "output" : "0x",
    "id": "0x62e2f27cd5ada06ec9a7a4cb351d51ce697c07beadaeb1e30f5e2e2e9031ba58"
  }
