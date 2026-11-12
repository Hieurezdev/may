"""Integration tests for order integrity, ownership and speech service boundaries."""

import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from backend import db
from backend.main import app
from backend.assistant import AssistantAnswer
from backend.seed import PRODUCTS


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment=patch.dict(os.environ,{"MAY_DEMO_MODE":"1"})
        self.environment.start()
        self.directory = tempfile.TemporaryDirectory()
        self.database = patch.object(db, "DB_PATH", Path(self.directory.name) / "test.sqlite3")
        self.database.start()
        self.client = TestClient(app)
        self.client.__enter__()
        self.client.get("/api/me")
        self.client.post("/api/auth/register", json={"email": "shopper@example.com", "password": "A-private-test-password", "full_name": "Khách mua hàng"}).raise_for_status()
        self.product = self.client.get("/api/products").json()[0]
        self.variant = self.product["variants"][0]
        self.assistant_mock = patch("backend.api.chat.complete", new_callable=AsyncMock)
        self.complete = self.assistant_mock.start()
        self.complete.return_value = AssistantAnswer(content="Ami có thể giúp bạn chọn đồ từ danh mục hiện tại.",product_ids=[self.product["id"]])

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.database.stop()
        self.assistant_mock.stop()
        self.directory.cleanup()
        self.environment.stop()

    def add_item(self, quantity: int = 1) -> httpx.Response:
        return self.client.post("/api/cart", json={"variant_id": self.variant["id"], "quantity": quantity})

    def order_data(self, method: str = "cod", voucher: str = "") -> dict[str, str | int]:
        return {
            "recipient_name": "Khách thử nghiệm", "phone": "0901234567",
            "address": "123 Nguyễn Huệ, Quận 1, TP. Hồ Chí Minh",
            "payment_method": method, "voucher": voucher,
            "idempotency_key": "test-idempotency-key-0001",
            "expected_total": self.variant["price"] + (30000 if self.variant["price"] < 499000 else 0),
        }

    def test_catalog_has_real_sources_and_search_ignores_accents(self) -> None:
        products = self.client.get("/api/products").json()
        self.assertEqual({p["id"] for p in products}, {p["id"] for p in PRODUCTS})
        self.assertTrue(all(p["source_url"].startswith("https://") for p in products))
        self.assertTrue(self.client.get("/api/products", params={"q": "ao len nu"}).json())
        self.assertEqual(self.client.get("/api/products", params={"q": "nonexistent-product"}).json(), [])

    def test_source_images_and_frontend_modules_are_served(self) -> None:
        self.assertEqual(self.client.get("/").status_code, 200)
        for name in ["app.js", "api.js", "speech.js", "tryon.js", "camera.js", "ami-voice.js", "icons.js", "styles.css"]:
            self.assertEqual(self.client.get("/static/" + name).status_code, 200)
        for product in self.client.get("/api/products").json():
            self.assertEqual(self.client.get("/static/assets/" + product["image"]).status_code, 200, product["id"])
        self.assertEqual(self.client.get("/.env.local").status_code, 404)
        self.assertEqual(self.client.get("/static/../.env.local").status_code, 404)

    def test_application_code_is_revalidated_after_updates(self) -> None:
        for path in ["/", "/static/app.js", "/static/api.js", "/static/landing.js", "/static/styles.css", "/static/landing.css"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "no-cache")
                if path != "/" and "etag" in response.headers:
                    cached = self.client.get(path, headers={"If-None-Match": response.headers["etag"]})
                    self.assertEqual(cached.status_code, 304)
                    self.assertEqual(cached.headers["cache-control"], "no-cache")

    def test_new_arrivals_use_catalog_date_then_newly_added_products(self) -> None:
        response = self.client.get("/api/products", params={"sort": "new"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id"], PRODUCTS[-1]["id"])
        with db.connection() as connection:
            connection.execute("UPDATE products SET collected_at='2099-01-01' WHERE id=?", (self.product["id"],))
        latest = self.client.get("/api/products", params={"sort": "new"}).json()
        self.assertEqual(latest[0]["id"], self.product["id"])
        self.assertEqual(latest[1]["id"], PRODUCTS[-1]["id"])
        filtered = self.client.get("/api/products", params={"sort": "new", "category": self.product["category"]}).json()
        self.assertEqual(filtered[0]["id"], self.product["id"])
        self.assertTrue(all(product["category"] == self.product["category"] for product in filtered))

    def test_cart_is_persistent_and_stock_is_enforced(self) -> None:
        self.assertEqual(self.add_item(2).status_code, 200)
        self.assertEqual(self.client.get("/api/cart").json()[0]["quantity"], 2)
        self.assertEqual(self.add_item(30).status_code, 409)
        self.assertEqual(self.client.get("/api/cart").json()[0]["quantity"], 2)
        self.assertEqual(self.client.post("/api/cart", json={"variant_id": self.variant["id"], "quantity": -1}).status_code, 422)

    def test_order_totals_stock_and_idempotency(self) -> None:
        self.add_item()
        quote = self.client.post("/api/checkout/quote", json={"voucher": "HELLOMAY"}).json()
        self.assertEqual(quote["discount"], self.variant["price"] // 10)
        command = {**self.order_data(voucher="HELLOMAY"), "expected_total": quote["total"]}
        response = self.client.post("/api/orders", json=command)
        self.assertEqual(response.status_code, 201, response.text)
        order = response.json()
        self.assertEqual(order["total"], quote["total"])
        self.assertEqual(order["payment_status"], "pending")
        self.assertEqual(order["items"][0]["size"], self.variant["size"])
        self.assertEqual(self.client.get("/api/cart").json(), [])
        again = self.client.post("/api/orders", json=command)
        self.assertEqual(again.json()["id"], order["id"])
        current = self.client.get("/api/products/" + self.product["id"]).json()
        stock = next(v["stock"] for v in current["variants"] if v["id"] == self.variant["id"])
        self.assertEqual(stock, self.variant["stock"] - 1)
        with db.connection() as connection:
            self.assertEqual(connection.execute("SELECT used_count FROM vouchers WHERE code='HELLOMAY'").fetchone()[0], 1)

    def test_invalid_shipping_and_voucher_leave_cart_unchanged(self) -> None:
        self.add_item()
        invalid = self.order_data()
        invalid["phone"] = "123"
        self.assertEqual(self.client.post("/api/orders", json=invalid).status_code, 422)
        self.assertEqual(self.client.post("/api/orders", json=self.order_data(voucher="WRONG")).status_code, 422)
        self.assertEqual(len(self.client.get("/api/cart").json()), 1)
        self.assertEqual(self.client.get("/api/orders").json(), [])

    def test_stock_is_rechecked_at_order_time(self) -> None:
        self.add_item()
        with db.connection() as connection:
            connection.execute("UPDATE inventory_positions SET on_hand=0 WHERE variant_id=?", (self.variant["id"],))
        self.assertEqual(self.client.post("/api/orders", json=self.order_data()).status_code, 409)
        self.assertEqual(self.client.get("/api/orders").json(), [])
        self.assertEqual(len(self.client.get("/api/cart").json()), 1)

    def test_customer_cannot_read_or_pay_another_customers_order(self) -> None:
        self.add_item()
        order = self.client.post("/api/orders", json=self.order_data(method="online-demo")).json()
        with TestClient(app) as other:
            other.get("/api/me")
            other.post("/api/auth/register", json={"email": "other@example.com", "password": "Another-test-password", "full_name": "Khách khác"}).raise_for_status()
            self.assertEqual(other.get("/api/orders").json(), [])
            self.assertEqual(other.post("/api/orders/" + order["id"] + "/demo-payment", json={"outcome": "success"}).status_code, 404)
            answer = other.post("/api/chat", json={"content": "Đơn hàng " + order["id"]}).json()
            self.assertNotIn(order["id"], answer["content"])
            self.assertEqual(self.complete.call_args.args[2].orders,[])

    def test_failed_payment_cannot_mark_order_paid(self) -> None:
        self.add_item()
        order=self.client.post('/api/orders',json=self.order_data(method='online-demo')).json()
        path='/api/orders/'+order['id']+'/demo-payment'
        self.assertEqual(self.client.post(path,json={'outcome':'failure'}).json()['payment_status'],'failed')
        self.assertEqual(self.client.post(path,json={'outcome':'success'}).status_code,409)
        self.assertEqual(self.client.get('/api/orders/'+order['id']).json()['status'],'payment_failed')

    def test_register_login_rotation_and_history_access(self) -> None:
        self.client.post("/api/auth/logout")
        self.client.get("/api/me")
        credentials = {"email": "test@example.com", "password": "A-private-test-password", "full_name": "Khách test"}
        old_token = self.client.cookies.get("may_session")
        self.assertEqual(self.client.post("/api/auth/register", json=credentials).status_code, 201)
        self.add_item()
        order = self.client.post("/api/orders", json=self.order_data()).json()
        self.client.post("/api/auth/logout")
        self.client.get("/api/me")
        self.assertEqual(self.client.get("/api/orders").json(), [])
        self.assertEqual(self.client.post("/api/auth/login", json=credentials).status_code, 200)
        self.assertNotEqual(self.client.cookies.get("may_session"), old_token)
        self.assertEqual(self.client.get("/api/orders").json()[0]["id"], order["id"])

    def test_guest_shopping_is_scoped_to_verified_session(self) -> None:
        with TestClient(app) as guest:
            guest.get('/api/me')
            self.assertEqual(guest.post('/api/cart',json={'variant_id':self.variant['id'],'quantity':1}).status_code,200)
            order=guest.post('/api/orders',json=self.order_data()).json()
            self.assertEqual(order['status'],'confirmed')
            self.assertEqual(self.client.get('/api/orders/'+order['id']).status_code,404)
            self.assertEqual(guest.get('/api/orders/'+order['id']).status_code,200)
        self.assertEqual(self.client.get('/api/cart').json(),[])

    def test_owner_cancellation_releases_stock_once(self) -> None:
        self.assertEqual(self.client.get('/api/admin/orders').status_code,403)
        self.add_item()
        order=self.client.post('/api/orders',json=self.order_data()).json()
        path='/api/orders/'+order['id']+'/cancel'
        for _ in range(2):
            self.assertEqual(self.client.post(path,json={'reason':'Changed delivery plan'}).status_code,200)
        current=self.client.get('/api/products/'+self.product['id']).json()
        stock=next(v['stock'] for v in current['variants'] if v['id']==self.variant['id'])
        self.assertEqual(stock,self.variant['stock'])

    def test_try_on_session_ownership_and_deletion(self) -> None:
        session = self.client.post("/api/try-on", json={"product_id": self.product["id"]})
        self.assertEqual(session.status_code, 201)
        path = "/api/try-on/" + session.json()["id"]
        with TestClient(app) as other:
            other.get("/api/me")
            self.assertEqual(other.delete(path).status_code, 404)
        self.assertEqual(self.client.delete(path).status_code, 200)
        with db.connection() as connection:
            row = connection.execute("SELECT status,deleted_at FROM try_on_sessions WHERE id=?", (session.json()["id"],)).fetchone()
            self.assertEqual(row["status"], "deleted")
            self.assertIsNotNone(row["deleted_at"])

    def test_chat_validation_and_private_history(self) -> None:
        self.assertEqual(self.client.post("/api/chat", json={"content": "   "}).status_code, 422)
        result = self.client.post("/api/chat", json={"content": "Tư vấn áo len"}).json()
        self.assertEqual(result["mode"], "qwen-proxy")
        self.assertTrue(result["product_ids"])
        self.assertEqual(len(self.client.get("/api/chat").json()), 2)
        context = self.complete.call_args.args[2]
        self.assertEqual({p.id for p in context.products}, {p["id"] for p in PRODUCTS})
        self.assertEqual(context.orders,[])
        self.assertIsInstance(result["message_id"],int)
        self.assertEqual(self.client.delete("/api/chat").status_code, 200)
        self.assertEqual(self.client.get("/api/chat").json(), [])

    def test_cross_origin_writes_are_blocked(self) -> None:
        response = self.client.post("/api/cart", json={"variant_id": self.variant["id"], "quantity": 1}, headers={"Origin": "https://untrusted.example"})
        self.assertEqual(response.status_code, 403)

    def test_ami_reads_current_stock_and_available_sizes_from_database(self) -> None:
        with db.connection() as connection:
            connection.execute("UPDATE inventory_positions SET on_hand=0 WHERE variant_id IN (SELECT id FROM variants WHERE product_id=?)",(self.product["id"],))
        self.client.post("/api/chat",json={"content":"Mẫu áo này còn hàng không?"})
        context=self.complete.call_args.args[2]
        product=next(product for product in context.products if product.id==self.product["id"])
        self.assertEqual(product.stock,0)
        self.assertFalse(product.available)
        self.assertEqual(product.sizes,[])
        with db.connection() as connection:
            connection.execute("UPDATE inventory_positions SET on_hand=3 WHERE variant_id=?",(self.variant["id"],))
        self.client.post("/api/chat",json={"content":"Kiểm tra lại tồn kho giúp mình"})
        context=self.complete.call_args.args[2]
        product=next(product for product in context.products if product.id==self.product["id"])
        self.assertEqual(product.stock,3)
        self.assertTrue(product.available)
        self.assertEqual(product.sizes,[self.variant["size"]])

    def test_speech_is_limited_to_the_owners_assistant_messages(self) -> None:
        answer = self.client.post("/api/chat",json={"content":"Chào Ami"}).json()
        path = "/api/chat/"+str(answer["message_id"])+"/speech"
        with patch("backend.api.chat.synthesize",new_callable=AsyncMock,return_value=b"ID3-test-audio") as synthesize:
            with TestClient(app) as other:
                other.get("/api/me")
                self.assertEqual(other.post(path).status_code,404)
                synthesize.assert_not_called()
            result=self.client.post(path)
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.content,b"ID3-test-audio")

    def test_clearing_chat_during_generation_does_not_restore_deleted_history(self) -> None:
        from backend.api.chat import clear_chat
        customer=self.client.get("/api/me").json()["id"]
        async def clear_during_generation(content,history,context):
            clear_chat(customer)
            return AssistantAnswer(content="Một câu trả lời đến muộn.",product_ids=[])
        self.complete.side_effect=clear_during_generation
        self.assertEqual(self.client.post("/api/chat",json={"content":"Chào Ami"}).status_code,409)
        self.assertEqual(self.client.get("/api/chat").json(),[])

    def test_elevenlabs_transcription_contract(self) -> None:
        real_client = httpx.AsyncClient

        def respond(request: httpx.Request) -> httpx.Response:
            self.assertEqual(str(request.url), "https://api.elevenlabs.io/v1/speech-to-text")
            self.assertEqual(request.headers["xi-api-key"], "test-credential")
            self.assertIn(b"scribe_v2", request.content)
            self.assertIn(b"vie", request.content)
            return httpx.Response(200, json={"text": "Áo len nữ", "language_code": "vie"})

        with patch("backend.speech.api_key", return_value="test-credential"):
            with patch("backend.speech.httpx.AsyncClient", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs)):
                response = self.client.post("/api/search/transcribe", content=b"audio" * 100, headers={"X-Media-Consent":"true", "Content-Type": "audio/webm;codecs=opus"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["text"], "Áo len nữ")
        self.assertEqual(response.json()["provider"], "elevenlabs")

    def test_speech_rejects_invalid_files_and_hides_provider_errors(self) -> None:
        with patch("backend.speech.api_key", return_value="test-credential"):
            self.assertEqual(self.client.post("/api/search/transcribe", content=b"x" * 200, headers={"X-Media-Consent":"true", "Content-Type": "text/plain"}).status_code, 415)
            self.assertEqual(self.client.post("/api/search/transcribe", content=b"", headers={"X-Media-Consent":"true", "Content-Type": "audio/webm"}).status_code, 422)
            self.assertEqual(self.client.post("/api/search/transcribe", content=b"x" * (10 * 1024 * 1024 + 1), headers={"X-Media-Consent":"true", "Content-Type": "audio/webm"}).status_code, 413)
            real_client = httpx.AsyncClient
            with patch("backend.speech.httpx.AsyncClient", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(lambda request: httpx.Response(401, json={"detail": "private-upstream-detail"})), **kwargs)):
                response = self.client.post("/api/search/transcribe", content=b"audio" * 100, headers={"X-Media-Consent":"true", "Content-Type": "audio/webm"})
            self.assertEqual(response.status_code, 502)
            self.assertNotIn("private-upstream-detail", response.text)
            self.assertNotIn("test-credential", response.text)


if __name__ == "__main__":
    unittest.main()
