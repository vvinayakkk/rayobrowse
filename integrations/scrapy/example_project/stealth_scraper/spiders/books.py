"""
Example spider: scrape books from https://books.toscrape.com

Demonstrates scraping a multi-page catalog site through a
stealth-fingerprinted browser via rayobrowse.

Usage:
    cd example_project
    scrapy crawl books -o books.json
"""

import scrapy


class BooksSpider(scrapy.Spider):
    name = "books"
    start_urls = ["https://books.toscrape.com/"]

    custom_settings = {
        "FEEDS": {
            "books.json": {"format": "json", "overwrite": True},
        },
        "CLOSESPIDER_ITEMCOUNT": 50,
    }

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(url, meta={"playwright": True})

    async def start(self):
        for request in self.start_requests():
            yield request

    def parse(self, response):
        for book in response.css("article.product_pod"):
            yield {
                "title": book.css("h3 a::attr(title)").get(),
                "price": book.css("p.price_color::text").get(),
                "in_stock": bool(book.css("p.instock")),
                "rating": book.css("p.star-rating::attr(class)").re_first(
                    r"star-rating (\w+)"
                ),
                "url": response.urljoin(book.css("h3 a::attr(href)").get()),
            }

        next_page = response.css("li.next a::attr(href)").get()
        if next_page:
            yield response.follow(
                next_page,
                self.parse,
                meta={"playwright": True},
            )
