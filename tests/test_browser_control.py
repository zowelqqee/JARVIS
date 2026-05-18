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
