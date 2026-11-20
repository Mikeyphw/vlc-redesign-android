"""Exact official Maven source: bounded 429 retry and adversarial failures.

No network calls. These complement existing MediaLibrary ELF, AAR, POM, SHA and
four-ABI tests; no real Gradle or Android build is claimed by this test.
"""
from __future__ import annotations
import io
from pathlib import Path
import sys
import unittest
from unittest import mock
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ci'))
import medialibrary as ml

URL = 'https://repo.maven.apache.org/maven2/org/videolan/android/medialibrary-all/0.13.24/medialibrary-all-0.13.24.aar'

class Response(io.BytesIO):
    def __init__(self, value=b'official', url=URL):
        super().__init__(value)
        self.url = url
    def geturl(self):
        return self.url


def http_error(code, headers=None):
    return urllib.error.HTTPError(URL, code, 'simulated', headers or {}, io.BytesIO())


class OfficialMavenRateLimitTests(unittest.TestCase):
    def test_first_try_succeeds_without_sleep(self):
        with mock.patch.object(ml.urllib.request, 'urlopen', return_value=Response(b'valid')) as fetch, \
             mock.patch.object(ml.time, 'sleep') as sleep:
            self.assertEqual(ml.fetch_official(URL), b'valid')
        self.assertEqual(fetch.call_count, 1)
        sleep.assert_not_called()

    def test_429_then_verified_exact_origin_content(self):
        with mock.patch.object(ml.urllib.request, 'urlopen', side_effect=[
                http_error(429, {'Retry-After': '7'}), Response(b'recovered')]) as fetch, \
             mock.patch.object(ml.time, 'sleep') as sleep:
            self.assertEqual(ml.fetch_official(URL), b'recovered')
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once_with(7)

    def test_persistent_429_exhausts_five_requests_and_refuses(self):
        with mock.patch.object(ml.urllib.request, 'urlopen', side_effect=[http_error(429) for _ in range(5)]) as fetch, \
             mock.patch.object(ml.time, 'sleep') as sleep:
            with self.assertRaises(urllib.error.HTTPError) as context:
                ml.fetch_official(URL)
        self.assertEqual(context.exception.code, 429)
        self.assertIn(URL, str(context.exception))
        self.assertEqual(fetch.call_count, 5)
        self.assertEqual([x.args[0] for x in sleep.call_args_list], [5, 15, 30, 60])

    def test_retry_after_is_bounded_even_if_hostile(self):
        with mock.patch.object(ml.urllib.request, 'urlopen', side_effect=[
                http_error(429, {'Retry-After':'9999'}), Response()]), \
             mock.patch.object(ml.time, 'sleep') as sleep:
            self.assertEqual(ml.fetch_official(URL), b'official')
        sleep.assert_called_once_with(90)

    def test_unparseable_retry_after_does_not_extend_wait(self):
        with mock.patch.object(ml.urllib.request, 'urlopen', side_effect=[
                http_error(429, {'Retry-After':'Fri, 20 Nov 2026'}), Response()]), \
             mock.patch.object(ml.time, 'sleep') as sleep:
            self.assertEqual(ml.fetch_official(URL), b'official')
        sleep.assert_called_once_with(5)

    def test_403_404_and_server_error_never_retry(self):
        for code in (403, 404, 500, 503):
            with self.subTest(code=code), \
                 mock.patch.object(ml.urllib.request, 'urlopen', side_effect=http_error(code)) as fetch, \
                 mock.patch.object(ml.time, 'sleep') as sleep:
                with self.assertRaises(urllib.error.HTTPError) as context:
                    ml.fetch_official(URL)
                self.assertEqual(context.exception.code, code)
                self.assertEqual(fetch.call_count, 1)
                sleep.assert_not_called()

    def test_wrong_domain_or_version_rejected_without_network(self):
        for url in (URL.replace('repo.maven.apache.org', 'repo1.maven.org'),
                    URL.replace('/0.13.24/', '/0.13.25/'),
                    URL.replace('https://', 'http://')):
            with self.subTest(url=url), mock.patch.object(ml.urllib.request, 'urlopen') as fetch:
                with self.assertRaises(ml.MediaContractError):
                    ml.fetch_official(url)
                fetch.assert_not_called()

    def test_cross_origin_redirect_rejected(self):
        with mock.patch.object(ml.urllib.request, 'urlopen',
                               return_value=Response(url='https://evil.example/aar')):
            with self.assertRaisesRegex(ml.MediaContractError, 'redirected'):
                ml.fetch_official(URL)

    def test_empty_or_excess_payload_rejected(self):
        with mock.patch.object(ml.urllib.request, 'urlopen', return_value=Response(b'')):
            with self.assertRaisesRegex(ml.MediaContractError, 'empty or oversized'):
                ml.fetch_official(URL)
        with mock.patch.object(ml.urllib.request, 'urlopen', return_value=Response(b'x' * (80*1024*1024 + 1))):
            with self.assertRaisesRegex(ml.MediaContractError, 'empty or oversized'):
                ml.fetch_official(URL)


if __name__ == '__main__':
    unittest.main()
