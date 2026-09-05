"""Offline contracts for keyword search, SDK pagination and bounded workers."""
import asyncio
import threading
import unittest
from unittest.mock import Mock, mock_open, patch

import requests

from backend.services.search_providers.local_provider import LocalSearchProvider

MODULE = "backend.services.search_providers.local_provider"


def youtube_video(index):
    return {
        "title": f"Python lesson {index}",
        "url": f"https://www.youtube.com/watch?v=fixture{index}",
        "duration": 65, "uploader": "Example author", "view_count": 42,
        "thumbnails": [{"url": "https://example.com/cover.jpg"}],
    }


def bilibili_response(start=0, count=20):
    response = Mock(status_code=200)
    response.json.return_value = {"code": 0, "data": {"result": [
        {"bvid": f"BVfixture{index}", "title": f"<em>Python</em> &amp; {index}",
         "pic": "//example.com/cover.jpg", "author": "Example author", "duration": "1:05", "play": 42}
        for index in range(start, start + count)
    ]}}
    return response


class VideoSearchSdkTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.real_cookie_method = LocalSearchProvider._get_bilibili_search_cookies
        self.cookie_patch = patch.object(LocalSearchProvider, "_get_bilibili_search_cookies", return_value={})
        self.cookie_patch.start()
        self.addCleanup(self.cookie_patch.stop)

    async def test_initialization_does_not_run_a_cli_or_load_browser_cookies(self):
        with patch(MODULE + ".LocalSearchProvider._load_bilibili_cookies", return_value={}), patch(
            "asyncio.create_subprocess_exec", side_effect=AssertionError("CLI should not run"),
        ):
            provider = LocalSearchProvider()
            self.assertTrue(await provider.initialize())
            self.assertTrue(provider.is_available())

    async def test_youtube_uses_sdk_and_returns_real_page_windows(self):
        options_seen = []
        inputs_seen = []

        def sdk(options):
            options_seen.append(options)
            client = Mock()
            client.__enter__ = Mock(return_value=client)
            client.__exit__ = Mock(return_value=False)

            def extract(url, download):
                self.assertFalse(download)
                inputs_seen.append(url)
                return {"entries": [youtube_video(index) for index in range(
                    options["playliststart"] - 1, options["playlistend"],
                )]}

            client.extract_info.side_effect = extract
            return client

        with patch(MODULE + ".YoutubeDL", side_effect=sdk):
            provider = LocalSearchProvider()
            first = await provider.search("Python", platform="youtube", page=1, max_results=2)
            second = await provider.search("Python", platform="youtube", page=2, max_results=2)
        self.assertTrue(first["success"])
        self.assertTrue(second["success"])
        self.assertEqual(inputs_seen, ["ytsearch2:Python", "ytsearch4:Python"])
        self.assertEqual([video["title"] for video in second["results"]], ["Python lesson 2", "Python lesson 3"])
        self.assertFalse({v["url"] for v in first["results"]} & {v["url"] for v in second["results"]})
        self.assertEqual(first["results"][0]["duration"], "1:05")
        self.assertEqual(first["results"][0]["thumbnail"], "https://example.com/cover.jpg")
        for options in options_seen:
            self.assertIsNone(options["cookiefile"])
            self.assertIsNone(options["cookiesfrombrowser"])
            self.assertFalse(options["usenetrc"])
            self.assertFalse(options["cachedir"])
            self.assertFalse(options["ignoreerrors"])
            self.assertEqual(options["socket_timeout"], 10)

    async def test_sdk_exception_is_failure_and_does_not_expose_details(self):
        secret = "https://user:synthetic-password@example.com/private"
        with patch(MODULE + ".YoutubeDL", side_effect=RuntimeError(secret)), self.assertLogs(MODULE) as logs:
            result = await LocalSearchProvider().search("Python", platform="youtube")
        self.assertFalse(result["success"])
        self.assertEqual(result["count"], 0)
        self.assertNotIn(secret, str(result) + str(logs.output))

    async def test_sdk_malformed_result_is_not_a_successful_empty_search(self):
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        for malformed in (None, {}, {"entries": None}, {"entries": [None]}):
            with self.subTest(malformed=malformed), patch(MODULE + ".YoutubeDL", return_value=client):
                client.extract_info.return_value = malformed
                result = await LocalSearchProvider().search("Python", platform="youtube")
            self.assertFalse(result["success"])

    async def test_sdk_genuine_empty_search_is_successful(self):
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        client.extract_info.return_value = {"entries": []}
        with patch(MODULE + ".YoutubeDL", return_value=client):
            result = await LocalSearchProvider().search("no matches", platform="youtube")
        self.assertTrue(result["success"])
        self.assertEqual(result["results"], [])

    async def test_youtube_never_relabels_a_different_host_as_youtube(self):
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        client.extract_info.return_value = {"entries": [
            {"title": "Not YouTube", "url": "https://example.com/video"},
            {"title": "Credentials", "url": "https://user:password@youtube.com/watch?v=fixture"},
        ]}
        with patch(MODULE + ".YoutubeDL", return_value=client):
            result = await LocalSearchProvider().search("Python", platform="youtube")
        self.assertFalse(result["success"])
        self.assertEqual(result["count"], 0)

    async def test_unknown_platform_and_invalid_parameters_never_make_requests(self):
        invalid = [
            ({"platform": "dailymotion"}, "Python", "unsupported_platform"),
            ({"platform": "unknown"}, "Python", "unsupported_platform"),
            ({"platform": []}, "Python", "unsupported_platform"),
            ({}, "", "invalid_query"), ({}, None, "invalid_query"),
            ({}, "x" * 201, "invalid_query"),
            ({}, "https://example.com/video", "invalid_query"),
            ({}, "看看 youtube.com/watch?v=video", "invalid_query"),
            ({}, "file:///etc/passwd", "invalid_query"),
            ({}, "www.youtube.com", "invalid_query"),
            ({}, "Python\nvideo", "invalid_query"),
            ({"page": 0}, "Python", "invalid_page"),
            ({"page": 21}, "Python", "invalid_page"),
            ({"page": True}, "Python", "invalid_page"),
            ({"page": "2"}, "Python", "invalid_page"),
            ({"max_results": 0}, "Python", "invalid_limit"),
            ({"max_results": 21}, "Python", "invalid_limit"),
            ({"max_results": False}, "Python", "invalid_limit"),
        ]
        with patch(MODULE + ".requests.get", side_effect=AssertionError("network call")), patch(
            MODULE + ".YoutubeDL", side_effect=AssertionError("SDK call"),
        ):
            provider = LocalSearchProvider()
            for arguments, query, error_code in invalid:
                with self.subTest(arguments=arguments, query=query):
                    result = await provider.search(query, **arguments)
                    self.assertFalse(result["success"])
                    self.assertEqual(result["error_code"], error_code)

    async def test_bilibili_is_independent_of_youtube_sdk(self):
        with patch(MODULE + ".YoutubeDL", None), patch(MODULE + ".requests.get", return_value=bilibili_response(0, 2)):
            provider = LocalSearchProvider()
            result = await provider.search("Python", platform="bilibili", max_results=2)
            missing_sdk = await provider.search("Python", platform="youtube")
        self.assertTrue(result["success"])
        self.assertFalse(missing_sdk["success"])
        self.assertEqual(missing_sdk["error_code"], "dependency_unavailable")

    async def test_bilibili_window_within_one_upstream_page(self):
        with patch(MODULE + ".requests.get", return_value=bilibili_response()) as request:
            result = await LocalSearchProvider().search("Python", platform="bilibili", page=2, max_results=2)
        self.assertTrue(result["success"])
        self.assertEqual([video["title"] for video in result["results"]], ["Python & 2", "Python & 3"])
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.kwargs["params"]["page"], 1)
        self.assertEqual(request.call_args.kwargs["params"]["page_size"], 20)
        self.assertIsNone(request.call_args.kwargs["cookies"])
        self.assertIn("Chrome/", request.call_args.kwargs["headers"]["User-Agent"])
        self.assertTrue(request.call_args.kwargs["headers"]["User-Agent"].endswith("Safari/537.36"))
        self.assertEqual(request.call_args.kwargs["headers"]["Referer"], "https://www.bilibili.com/")

    async def test_bilibili_window_crosses_upstream_pages_without_overlap(self):
        with patch(MODULE + ".requests.get", side_effect=[bilibili_response(0), bilibili_response(20)]) as request:
            result = await LocalSearchProvider().search("Python", platform="bilibili", page=2, max_results=15)
        self.assertEqual(result["count"], 15)
        self.assertEqual(result["results"][0]["title"], "Python & 15")
        self.assertEqual(result["results"][-1]["title"], "Python & 29")
        self.assertEqual([call.kwargs["params"]["page"] for call in request.call_args_list], [1, 2])

    async def test_bilibili_restriction_and_network_error_are_not_empty_success(self):
        for status in (401, 403, 412, 429):
            with self.subTest(status=status), patch(MODULE + ".requests.get", return_value=Mock(status_code=status)):
                result = await LocalSearchProvider().search("Python", platform="bilibili")
                self.assertFalse(result["success"])
                self.assertEqual(result["error_code"], "platform_restricted")
        with patch(MODULE + ".requests.get", side_effect=requests.Timeout("private detail")):
            result = await LocalSearchProvider().search("Python", platform="bilibili")
        self.assertFalse(result["success"])
        self.assertNotIn("private detail", result["error"])

    async def test_bilibili_empty_result_is_success(self):
        with patch(MODULE + ".requests.get", return_value=bilibili_response(0, 0)):
            result = await LocalSearchProvider().search("no matches", platform="bilibili")
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 0)

    async def test_bilibili_html_or_malformed_entries_are_visible_failures(self):
        html_response = Mock(status_code=200)
        html_response.json.side_effect = ValueError("private response body")
        malformed_response = Mock(status_code=200)
        malformed_response.json.return_value = {"code": 0, "data": {"result": [{"unexpected": True}]}}
        for response in (html_response, malformed_response):
            with self.subTest(response=response), patch(MODULE + ".requests.get", return_value=response):
                result = await LocalSearchProvider().search("Python", platform="bilibili")
            self.assertFalse(result["success"])
            self.assertEqual(result["error_code"], "invalid_response")
            self.assertNotIn("private response body", str(result))

    async def test_timed_out_workers_remain_bounded_and_do_not_block_event_loop(self):
        provider = LocalSearchProvider()
        provider.SEARCH_TIMEOUT = 0.1
        release = threading.Event()
        started = threading.Event()
        lock = threading.Lock()
        calls = 0

        def blocking():
            nonlocal calls
            with lock:
                calls += 1
                if calls == 2:
                    started.set()
            release.wait(5)
            return []

        tasks = [asyncio.create_task(provider._run_blocking(blocking)) for _ in range(5)]
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            # This coroutine can still run while both synchronous workers wait.
            await asyncio.wait_for(asyncio.sleep(0), timeout=1)
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            self.assertTrue(all(isinstance(result, asyncio.TimeoutError) for result in outcomes))
            self.assertEqual(calls, 2)
        finally:
            release.set()
            await asyncio.gather(*tasks, return_exceptions=True)

    def test_cookie_loader_accepts_httponly_and_filters_other_domains(self):
        content = (
            "# Netscape HTTP Cookie File\n"
            "#HttpOnly_.bilibili.com\tTRUE\t/\tTRUE\t0\tSESSDATA\tsynthetic-session\n"
            ".example.com\tTRUE\t/\tTRUE\t0\tunrelated\tsynthetic-other\n"
        )
        with patch(MODULE + ".BILIBILI_COOKIES") as path:
            path.exists.return_value = True
            path.open = mock_open(read_data=content)
            self.assertEqual(LocalSearchProvider._load_bilibili_cookies(), {"SESSDATA": "synthetic-session"})

    def test_anonymous_search_initializes_only_a_public_bilibili_session(self):
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        client.get.return_value = Mock(status_code=200)
        client.cookies = requests.cookies.RequestsCookieJar()
        client.cookies.set("buvid3", "synthetic-public-visitor", domain=".bilibili.com")
        client.cookies.set("unrelated", "synthetic-other", domain=".example.com")
        with patch(MODULE + ".requests.Session", return_value=client):
            cookies = self.real_cookie_method(LocalSearchProvider())
        self.assertEqual(cookies, {"buvid3": "synthetic-public-visitor"})
        client.get.assert_called_once_with(
            "https://www.bilibili.com/", headers=LocalSearchProvider.BILIBILI_HEADERS, timeout=5,
        )

    def test_configured_cookies_do_not_require_anonymous_bootstrap(self):
        provider = LocalSearchProvider()
        provider._bilibili_cookies = {"SESSDATA": "synthetic-configured-session"}
        with patch(MODULE + ".requests.Session", side_effect=AssertionError("unexpected homepage request")):
            cookies = self.real_cookie_method(provider)
        self.assertEqual(cookies, provider._bilibili_cookies)
        self.assertIsNot(cookies, provider._bilibili_cookies)

    async def test_failed_anonymous_bootstrap_does_not_retry_around_restrictions(self):
        self.cookie_patch.stop()
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        client.get.return_value = Mock(status_code=412)
        with patch(MODULE + ".requests.Session", return_value=client), patch(
            MODULE + ".requests.get", side_effect=AssertionError("must stop after restriction"),
        ):
            result = await LocalSearchProvider().search("机器学习入门", platform="bilibili", max_results=2)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "platform_restricted")
        client.get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
