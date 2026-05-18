import asyncio

from actions import browser_control as browser_module


def test_close_action_does_not_create_new_browser_session(monkeypatch):
    class FakeRegistry:
        def __init__(self):
            self._active_browser = ""
            self.get_called = False
            self.closed_target = None

        def get(self, browser_name=None):
            self.get_called = True
            raise AssertionError("close should not create a new session")

        def close_one(self, browser_name):
            self.closed_target = browser_name
            return "Browser closed."

    fake_registry = FakeRegistry()
    monkeypatch.setattr(browser_module, "_registry", fake_registry)

    result = browser_module.browser_control({"action": "close", "browser": "chrome"})

    assert result == "Browser closed."
    assert fake_registry.closed_target == "chrome"
    assert fake_registry.get_called is False


def test_get_page_recovers_closed_context_and_restores_last_url(monkeypatch):
    class FakePage:
        def __init__(self):
            self.url = "about:blank"
            self.restored_urls = []

        def is_closed(self):
            return False

        async def goto(self, url, wait_until=None, timeout=None):
            self.url = url
            self.restored_urls.append(url)

    class BrokenContext:
        def __init__(self):
            self.closed = False

        async def new_page(self):
            raise RuntimeError(
                "BrowserContext.new_page: Target page, context or browser has been closed"
            )

        async def close(self):
            self.closed = True

    class HealthyContext:
        def __init__(self, page):
            self.page = page

        async def new_page(self):
            return self.page

        async def close(self):
            return None

    session = browser_module._BrowserSession("chrome")
    session._last_url = "https://www.aviasales.ru/search/MOW0106BRU15061"

    broken_context = BrokenContext()
    healthy_page = FakePage()
    healthy_context = HealthyContext(healthy_page)
    launch_count = {"value": 0}

    async def fake_launch():
        if session._context is not None:
            return
        if launch_count["value"] == 0:
            session._context = broken_context
        else:
            session._context = healthy_context
        launch_count["value"] += 1

    monkeypatch.setattr(session, "_launch", fake_launch)

    page = asyncio.run(session._get_page())

    assert page is healthy_page
    assert broken_context.closed is True
    assert healthy_page.restored_urls == ["https://www.aviasales.ru/search/MOW0106BRU15061"]
    assert launch_count["value"] == 2
