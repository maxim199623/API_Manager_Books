import importlib
import importlib.util
import ast
from pathlib import Path

LEGACY_API_MODULE = ".".join(("src", "api", "Shems"))
LEGACY_CORE_MODULE = ".".join(("src", "core", "Shems"))


def test_typo_dependencices_module_is_forbidden() -> None:
    importlib.invalidate_caches()

    forbidden_module = ".".join(("src", "api", "Dependencices"))

    assert importlib.util.find_spec(forbidden_module) is None


def test_pydantic_schemas_are_available_from_schemas_package() -> None:
    importlib.invalidate_caches()

    books = importlib.import_module("src.schemas.books")
    users = importlib.import_module("src.schemas.users")
    config = importlib.import_module("src.schemas.config")

    assert books.BookCreate
    assert users.UserRead
    assert config.DatabaseSettings


def test_runtime_modules_do_not_import_legacy_shems_modules() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src"
    offenders: list[str] = []

    for path in source_root.rglob("*.py"):
        if path.name == "Shems.py":
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports_legacy_module = (
                    module in {LEGACY_API_MODULE, LEGACY_CORE_MODULE}
                    or (
                        module.startswith("src.DB.Repository.")
                        and module.endswith(".Shems")
                    )
                )
                imports_legacy_name = (
                    module.startswith("src.DB.Repository.")
                    and any(alias.name == "Shems" for alias in node.names)
                )
                if imports_legacy_module or imports_legacy_name:
                    offenders.append(f"{path.relative_to(source_root.parent)}:{node.lineno}")

            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    imports_legacy_module = (
                        module in {LEGACY_API_MODULE, LEGACY_CORE_MODULE}
                        or (
                            module.startswith("src.DB.Repository.")
                            and module.endswith(".Shems")
                        )
                    )
                    if imports_legacy_module:
                        offenders.append(f"{path.relative_to(source_root.parent)}:{node.lineno}")

    assert offenders == []
