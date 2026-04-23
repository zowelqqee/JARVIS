import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


class TestBrowserControlEngineResolution(unittest.TestCase):

    def test_find_browser_executable_maps_chrome_family_to_chromium(self):
        with patch("actions.browser_control.platform.system", return_value="Windows"):
            from actions.browser_control import _find_browser_executable

            self.assertEqual(
                _find_browser_executable("mseDGEhtm".lower()),
                ("chromium", None, "msedge"),
            )
            self.assertEqual(
                _find_browser_executable("chromehtml".lower()),
                ("chromium", None, "chrome"),
            )
            self.assertEqual(
                _find_browser_executable(""),
                ("chromium", None, "chrome"),
            )


class TestBrowserControlLaunch(unittest.IsolatedAsyncioTestCase):

    async def test_launch_uses_playwright_chromium_for_cdp(self):
        from actions.browser_control import _BrowserThread, _CDP_URL

        page = AsyncMock()
        context = AsyncMock()
        context.pages = []
        context.new_page = AsyncMock(return_value=page)

        browser = MagicMock()
        browser.contexts = []
        browser.new_context = AsyncMock(return_value=context)

        chromium = MagicMock()
        chromium.connect_over_cdp = AsyncMock(return_value=browser)

        bt = _BrowserThread()
        bt._playwright = SimpleNamespace(chromium=chromium)

        await bt._launch()

        chromium.connect_over_cdp.assert_awaited_once_with(_CDP_URL)
        browser.new_context.assert_awaited_once()
        context.new_page.assert_awaited_once()
        self.assertIs(bt._browser, browser)
        self.assertIs(bt._context, context)
        self.assertIs(bt._page, page)
