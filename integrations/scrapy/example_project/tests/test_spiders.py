"""Run with: python -m unittest discover -s tests -v.

Set CHROMIUM_EXECUTABLE to enable local CDP lifecycle coverage. No rayobrowse
service, remote site, proxy, or downloaded browser is required.
"""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import scrapy
from scrapy.http import HtmlResponse

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from stealth_scraper.spiders.books import BooksSpider
from stealth_scraper.spiders.quotes import QuotesSpider


class SpiderTests(unittest.TestCase):
    def test_both_start_interfaces_render_every_seed(self):
        async def collect(spider):
            return [request async for request in spider.start()]

        for spider_class in (BooksSpider, QuotesSpider):
            with self.subTest(spider=spider_class.name):
                spider = spider_class(
                    start_urls=["https://example.test/one", "https://example.test/two"]
                )
                old = list(spider.start_requests())
                new = asyncio.run(collect(spider))
                self.assertEqual([r.url for r in old], spider.start_urls)
                self.assertEqual([r.url for r in new], spider.start_urls)
                for request in old + new:
                    self.assertEqual(request.meta, {"playwright": True})

    def test_pagination_retains_rendering_without_retaining_a_page(self):
        for spider_class in (BooksSpider, QuotesSpider):
            with self.subTest(spider=spider_class.name):
                spider = spider_class()
                request = scrapy.Request(
                    "https://example.test/one", meta={"playwright": True}
                )
                response = HtmlResponse(
                    request.url,
                    request=request,
                    body=b'<li class="next"><a href="/two">Next</a></li>',
                    encoding="utf-8",
                )
                output = list(spider.parse(response))
                self.assertEqual(len(output), 1)
                self.assertEqual(output[0].url, "https://example.test/two")
                self.assertEqual(output[0].meta, {"playwright": True})
                self.assertEqual(output[0].callback, spider.parse)


@unittest.skipUnless(
    os.environ.get("CHROMIUM_EXECUTABLE"), "set CHROMIUM_EXECUTABLE for CDP tests"
)
class LocalCdpTests(unittest.TestCase):
    def test_one_page_slot_survives_callback_and_navigation_failures(self):
        for spider in ("books", "quotes"):
            with self.subTest(spider=spider):
                self.run_crawl(spider)

    def run_crawl(self, spider):
        visited = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path in ('/bad', '/stall', '/one', '/two'):
                    visited.append(self.path)
                if self.path == '/stall':
                    time.sleep(2)
                content = ("<article class='product_pod'><h3><a title='Local book' href='/book'>Book</a></h3>"
                    "<p class='price_color'>12</p><p class='instock'>In stock</p><p class='star-rating Three'></p></article>")
                if spider == 'quotes':
                    # The content only exists after JavaScript runs.
                    content = "<div id='content'></div><script>document.getElementById('content').innerHTML=" + json.dumps(
                        "<div class='quote'><span class='text'>Rendered quote</span><small class='author'>Local author</small>"
                        "<div class='tags'><a class='tag'>test</a></div></div>") + ";</script>"
                if self.path == '/one':
                    content += "<li class='next'><a href='/two'>Next</a></li>"
                body = ('<!doctype html><body>' + content + '</body>').encode()
                try:
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as profile:
                browser = subprocess.Popen(
                    [
                        os.environ['CHROMIUM_EXECUTABLE'], '--headless', '--no-first-run',
                        '--remote-debugging-port=0', '--user-data-dir=' + profile,
                        'about:blank',
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                try:
                    port_file = Path(profile) / 'DevToolsActivePort'
                    deadline = time.monotonic() + 15
                    while not port_file.exists():
                        if browser.poll() is not None or time.monotonic() > deadline:
                            self.fail('Chromium did not start')
                        time.sleep(0.05)
                    port, path = port_file.read_text().splitlines()[:2]
                    cdp = 'ws://127.0.0.1:' + port + path
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(Path(__file__).with_name('crawl_fixture.py')),
                            str(PROJECT), spider, cdp,
                            'http://127.0.0.1:' + str(server.server_port),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    output = json.loads(next(
                        line[7:] for line in result.stdout.splitlines()
                        if line.startswith('RESULT:')
                    ))
                    self.assertEqual(visited, ['/bad', '/stall', '/one', '/two'])
                    self.assertEqual(len(output['items']), 2, result.stderr)
                    if spider == 'quotes':
                        self.assertEqual([item['text'] for item in output['items']], ['Rendered quote'] * 2)
                    else:
                        self.assertEqual([item['title'] for item in output['items']], ['Local book'] * 2)
                    stats = output['stats']
                    self.assertEqual(stats.get('spider_exceptions/ValueError'), 1, stats)
                    self.assertEqual(stats.get('downloader/exception_count'), 1, stats)
                    self.assertGreaterEqual(stats.get('playwright/page_count/closed', 0), 4, stats)
                finally:
                    browser.terminate()
                    browser.wait(timeout=10)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
