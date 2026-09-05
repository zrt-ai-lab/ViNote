import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.core.middleware import BrowserRequestMiddleware


class BrowserBoundaryTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.add_middleware(BrowserRequestMiddleware, allowed_origins=["http://localhost:5173"], allowed_hosts=["testserver", "localhost", "::1"])

        @app.post("/api/mutate")
        async def mutate():
            return {"ok": True}

        @app.get("/health")
        async def health():
            return {"ok": True}

        self.client = TestClient(app)

    def test_cross_site_form_is_rejected_before_mutation(self):
        response = self.client.post("/api/mutate", headers={"Origin": "https://untrusted.example"}, data={"url": "demo"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.post("/api/mutate", headers={"Origin": "null"}).status_code, 403)

    def test_same_origin_and_development_frontend_remain_usable(self):
        for origin in ("http://testserver", "http://localhost:5173"):
            self.assertEqual(self.client.post("/api/mutate", headers={"Origin": origin}).status_code, 200)

    def test_cli_without_origin_remains_usable(self):
        self.assertEqual(self.client.post("/api/mutate").status_code, 200)

    def test_browser_fetch_metadata_cannot_bypass_missing_origin(self):
        self.assertEqual(self.client.post("/api/mutate", headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403)

    def test_response_safety_headers(self):
        response = self.client.get("/health")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")

    def test_dns_rebinding_host_is_rejected(self):
        response = self.client.post("/api/mutate", headers={"Host": "untrusted.example", "Origin": "http://untrusted.example"})
        self.assertEqual(response.status_code, 400)

    def test_ipv6_loopback_host_is_supported(self):
        self.assertEqual(self.client.get("/health", headers={"Host": "[::1]:8999"}).status_code, 200)
