"""HTTP client behaviour with a fake session (no network). Run:  python -m unittest discover tests"""
import sys, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wfm import client


class Resp:
    def __init__(self, status, body=None, ct="application/json", headers=None):
        self.status_code, self._body, self.text = status, body, "" if body is None else str(body)
        self.headers = {"content-type": ct, **(headers or {})}
    def json(self):
        if self._body is None: raise ValueError("no body")
        return self._body


class Session:
    def __init__(self, *responses): self.queue, self.calls = list(responses), []
    def request(self, method, url, **kw):
        self.calls.append(method)
        item = self.queue.pop(0)
        if isinstance(item, Exception): raise item
        return item


class ClientTests(unittest.TestCase):
    def setUp(self):
        self._sleep, self._interval = time.sleep, client.MIN_INTERVAL
        time.sleep = lambda s: None
        client.MIN_INTERVAL = 0

    def tearDown(self):
        time.sleep, client.MIN_INTERVAL, client._session = self._sleep, self._interval, None

    def use(self, *responses):
        client._session = Session(*responses)
        return client._session

    def test_get_is_retried_on_5xx_and_network_errors(self):
        s = self.use(Resp(503), RuntimeError("reset"), Resp(200, {"ok": 1}))
        self.assertEqual(client.request("GET", "u"), {"ok": 1})
        self.assertEqual(s.calls, ["GET", "GET", "GET"])

    def test_patch_is_retried_on_5xx(self):
        s = self.use(Resp(502), Resp(200, {"ok": 1}))
        self.assertEqual(client.patch("u", "tok", {"platinum": 5}), {"ok": 1})
        self.assertEqual(len(s.calls), 2)

    def test_post_is_never_repeated_after_a_5xx(self):
        s = self.use(Resp(500), Resp(200, {"data": {"id": "dup"}}))
        with self.assertRaises(client.WfmError) as ctx: client.request("POST", "u", json={})
        self.assertEqual(s.calls, ["POST"])
        self.assertIn("check your orders", str(ctx.exception))

    def test_post_is_never_repeated_after_a_network_error(self):
        s = self.use(TimeoutError("slow"), Resp(200, {"data": {}}))
        with self.assertRaises(client.WfmError) as ctx: client.request("POST", "u", json={})
        self.assertEqual(s.calls, ["POST"])
        self.assertIn("check your orders", str(ctx.exception))

    def test_post_is_still_retried_on_429_because_nothing_was_processed(self):
        s = self.use(Resp(429, headers={"Retry-After": "0"}), Resp(200, {"ok": 1}))
        self.assertEqual(client.request("POST", "u", json={}), {"ok": 1})
        self.assertEqual(s.calls, ["POST", "POST"])

    def test_empty_success_body_is_not_an_error(self):
        self.use(Resp(204))
        self.assertEqual(client.delete("u", "tok"), {})

    def test_errors_and_cloudflare_pages(self):
        self.use(Resp(404, '{"error":"x"}'))
        with self.assertRaises(client.WfmError) as ctx: client.get("u")
        self.assertEqual(ctx.exception.status, 404)
        self.use(Resp(403, "<html>", ct="text/html"))
        with self.assertRaises(client.WfmError) as ctx: client.get("u")
        self.assertIn("Cloudflare", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
