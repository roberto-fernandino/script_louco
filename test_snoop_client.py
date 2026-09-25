import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/test")

import httpx

from app.main import rate_limit_delay, snoop_request, snoop_score_results, snoop_scores, snoop_throttle


class SnoopClientTests(unittest.TestCase):
    def test_extracts_both_scores_and_ignores_nulls(self):
        data = {"body": {"resultados": [{"score_csb8": 742, "score_csba": None}]}}
        self.assertEqual(snoop_scores(data), {"SCORE_CSB8": 742.0})

    def test_extracts_score_from_multiple_results(self):
        data = {"body": {"resultados": [{"score_csb8": 700}, {"score_csba": 812}]}}
        self.assertEqual(snoop_scores(data), {"SCORE_CSB8": 700.0, "SCORE_CSBA": 812.0})

    def test_parses_batched_results_by_normalized_cpf(self):
        data = {"body": {"resultados": [{"cpf": "123.456.789-00", "score_csb8": 742}]}}
        self.assertEqual(snoop_score_results(data)["12345678900"]["score_csb8"], 742)

    def test_rate_limit_headers_take_precedence(self):
        response = httpx.Response(429, headers={"Retry-After": "3"})
        self.assertEqual(rate_limit_delay(response, 0), 3.0)

    def test_throttle_is_configurable_and_serialized(self):
        async def run():
            with patch("app.main.settings.snoop_rate_limit_per_second", 1000.0):
                with patch("app.main._snoop_next_request_at", 0.0):
                    with patch("app.main.asyncio.sleep", new_callable=AsyncMock) as sleep:
                        await snoop_throttle()
                        await snoop_throttle()
                        self.assertGreaterEqual(sleep.await_count, 1)

        asyncio.run(run())

    def test_request_sends_api_key_and_maps_client_error(self):
        async def run():
            seen = {}

            def handler(request):
                seen["key"] = request.headers.get("x-api-key")
                return httpx.Response(401, json={"error": "invalid key"}, request=request)

            transport = httpx.MockTransport(handler)
            with patch("app.main.settings.snoop_api_key", "test-only-key"):
                with patch("app.main.settings.snoop_max_retries", 0):
                    async with httpx.AsyncClient(transport=transport) as client:
                        with self.assertRaises(Exception) as raised:
                            await snoop_request(client, "GET", "/api/query/bin", params={"bin": "453211"})
            self.assertEqual(seen["key"], "test-only-key")
            self.assertEqual(raised.exception.status_code, 401)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
