import importlib
import importlib.util


def test_typo_dependencices_module_is_forbidden() -> None:
    importlib.invalidate_caches()

    forbidden_module = ".".join(("src", "api", "Dependencices"))

    assert importlib.util.find_spec(forbidden_module) is None
