"""Run one isolated Scrapy reactor for the local CDP tests."""

import json
import sys

from scrapy import signals
from scrapy.crawler import CrawlerProcess

sys.path.insert(0, sys.argv[1])
from stealth_scraper.spiders.books import BooksSpider
from stealth_scraper.spiders.quotes import QuotesSpider

base_class = {"books": BooksSpider, "quotes": QuotesSpider}[sys.argv[2]]


class LocalSpider(base_class):
    custom_settings = {}

    def parse(self, response):
        if response.url.endswith("/bad"):
            raise ValueError("intentional callback failure")
        yield from super().parse(response)


settings = {
    "DOWNLOAD_HANDLERS": {
        "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    },
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    "PLAYWRIGHT_CDP_URL": sys.argv[3],
    "PLAYWRIGHT_MAX_PAGES_PER_CONTEXT": 1,
    "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 1000,
    "CONCURRENT_REQUESTS": 1,
    "ROBOTSTXT_OBEY": False,
    "RETRY_ENABLED": False,
    "DOWNLOAD_TIMEOUT": 3,
    "LOG_LEVEL": "ERROR",
    "TELNETCONSOLE_ENABLED": False,
}
process = CrawlerProcess(settings)
crawler = process.create_crawler(LocalSpider)
items = []


def collect_item(item, **kwargs):
    items.append(dict(item))


crawler.signals.connect(collect_item, signal=signals.item_scraped)
process.crawl(
    crawler,
    start_urls=[sys.argv[4] + path for path in ["/bad", "/stall", "/one"]],
)
process.start(install_signal_handlers=False)
print("RESULT:" + json.dumps({"items": items, "stats": crawler.stats.get_stats()}, default=str))
