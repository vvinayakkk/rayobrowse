"""
Example spider: scrape quotes from https://quotes.toscrape.com

This site is purpose-built for scraping practice. It renders quotes
with JavaScript, making it a good test case for browser-based scraping.

Usage:
    cd example_project
    scrapy crawl quotes -o quotes.json
"""

import scrapy


class QuotesSpider(scrapy.Spider):
    name = "quotes"
    start_urls = ["https://quotes.toscrape.com/js/"]

    custom_settings = {
        "FEEDS": {
            "quotes.json": {"format": "json", "overwrite": True},
        },
    }

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(url, meta={"playwright": True})

    async def start(self):
        for request in self.start_requests():
            yield request

    def parse(self, response):
        for quote_el in response.css("div.quote"):
            yield {
                "text": quote_el.css("span.text::text").get(),
                "author": quote_el.css("small.author::text").get(),
                "tags": quote_el.css("div.tags a.tag::text").getall(),
            }

        next_page = response.css("li.next a::attr(href)").get()
        if next_page:
            yield response.follow(
                next_page,
                self.parse,
                meta={"playwright": True},
            )
