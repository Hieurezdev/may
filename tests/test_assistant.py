"""Verify the Qwen HTTP boundary without making external model calls."""

import json
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException

from backend.assistant import AssistantContext, AssistantProduct, ChatTurn, complete


class AssistantTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.context=AssistantContext(
            products=[AssistantProduct(id="shirt-1",name="Áo len",brand="CANIFA",category="tops",price=299000,available=True,stock=10,colors=["Đen"],sizes=["M"],specs={"Chất liệu":"Cotton"})],
            vouchers=[],orders=[],
        )
        self.config={"LLM_BASE_URL":"https://qwen.example/v1","LLM_API_KEY":"test-secret","LLM_MODEL":"test-qwen","LLM_TIMEOUT":"5"}
        self.original_client=httpx.AsyncClient

    async def request(self, handler):
        with patch("backend.assistant.setting",side_effect=self.config.get):
            with patch("backend.assistant.httpx.AsyncClient",side_effect=lambda **kwargs:self.original_client(transport=httpx.MockTransport(handler),**kwargs)):
                return await complete("Có áo dưới 400 nghìn không?",[ChatTurn(role="user",content="Mình thích áo len")],self.context)

    async def test_one_system_message_with_database_context_and_history(self) -> None:
        def handler(request):
            self.assertEqual(request.headers["Authorization"],"Bearer test-secret")
            body=json.loads(request.content)
            self.assertEqual([m["role"] for m in body["messages"]],["system","user","user"])
            self.assertIn('"price":299000',body["messages"][0]["content"])
            self.assertIn('"sizes":["M"]',body["messages"][0]["content"])
            return httpx.Response(200,json={"choices":[{"message":{"content":json.dumps({"content":"Bạn có thể chọn áo len 299.000đ.","product_ids":["shirt-1"]})}}]})
        result=await self.request(handler)
        self.assertEqual(result.product_ids,["shirt-1"])

    async def test_invented_product_is_rejected(self) -> None:
        def handler(request):
            return httpx.Response(200,json={"choices":[{"message":{"content":'{"content":"Sản phẩm khác","product_ids":["invented"]}'}}]})
        with self.assertRaises(HTTPException) as caught:
            await self.request(handler)
        self.assertEqual(caught.exception.status_code,502)

    async def test_provider_auth_details_are_not_exposed(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            await self.request(lambda request:httpx.Response(401,json={"detail":"test-secret private upstream"}))
        self.assertEqual(caught.exception.status_code,502)
        self.assertNotIn("test-secret",caught.exception.detail)

    async def test_unstructured_model_reply_fails_explicitly(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            await self.request(lambda request:httpx.Response(200,json={"choices":[{"message":{"content":"unstructured answer"}}]}))
        self.assertEqual(caught.exception.status_code,502)
