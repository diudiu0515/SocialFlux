import json
import unittest
from unittest.mock import Mock, patch
from providers.base import ProviderRefusalError
from providers.anthropic import AnthropicProvider
from providers.openai_compatible import OpenAICompatibleProvider
from providers.openai_responses import OpenAIResponsesProvider
from providers.failover import FailoverProvider
from tests.test_failover_provider import FakeProvider
from tests.test_anthropic_provider import FakeResponse

class ProviderRefusalTest(unittest.TestCase):
    def test_anthropic_refusal_without_text_is_terminal(self):
        response=FakeResponse()
        response.read=lambda:json.dumps({'content':[{'type':'thinking','thinking':'private'}], 'stop_reason':'refusal'}).encode()
        provider=AnthropicProvider('https://example.invalid','model','token')
        provider._open=Mock(return_value=response)
        with self.assertRaises(ProviderRefusalError):provider.complete([{'role':'user','content':'test'}])
        self.assertEqual(provider.metrics['failed_request_count'],1)
        self.assertEqual(provider.metrics['stop_reasons'],{'refusal':1})
        self.assertEqual(provider._open.call_count,1)

    @patch('providers.failover._next_candidate_slot',return_value=0)
    def test_failover_does_not_try_another_route_after_refusal(self,_slot):
        first=FakeProvider(error=ProviderRefusalError('refused'));second=FakeProvider(result='ok')
        provider=FailoverProvider([first,second],model='model')
        with self.assertRaises(ProviderRefusalError):provider.complete([{'role':'user','content':'test'}])
        self.assertEqual((first.calls,second.calls),(1,0))
        self.assertEqual(provider.metrics['circuit_open_events'],0)

    @patch('providers.openai_compatible.build_opener')
    def test_chat_refusal_field_and_finish_reason_are_terminal(self,opener):
        for choice in [{'message':{'content':None,'refusal':'no'},'finish_reason':'stop'},
                       {'message':{'content':None},'finish_reason':'content_filter'}]:
            response=FakeResponse();response.read=lambda:json.dumps({'choices':[choice]}).encode()
            opener.return_value.open.return_value=response
            p=OpenAICompatibleProvider('http://localhost/v1/chat/completions','model')
            with self.assertRaises(ProviderRefusalError):p.complete([{'role':'user','content':'test'}])

    def test_stream_and_responses_refusals_are_terminal(self):
        p=OpenAICompatibleProvider('http://localhost/v1/chat/completions','model')
        event={'choices':[{'delta':{'refusal':'no'}}]}
        with self.assertRaises(ProviderRefusalError):p._read_stream([('data: '+json.dumps(event)).encode()])
        with self.assertRaises(ProviderRefusalError):OpenAIResponsesProvider._extract_text({'output':[{'type':'message','content':[{'type':'refusal','refusal':'no'}]}]})

    @patch.object(OpenAICompatibleProvider,'_complete_single',side_effect=ProviderRefusalError('refused'))
    def test_credential_pool_does_not_rotate_after_refusal(self,complete):
        p=OpenAICompatibleProvider('http://localhost/v1/chat/completions','model',api_keys=['one','two'])
        with self.assertRaises(ProviderRefusalError):p.complete([{'role':'user','content':'test'}])
        self.assertEqual(complete.call_count,1)
