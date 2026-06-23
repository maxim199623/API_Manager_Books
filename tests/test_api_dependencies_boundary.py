import importlib
import importlib.util
import ast
from pathlib import Path

LEGACY_API_MODULE = ".".join(("src", "api", "Shems"))
LEGACY_CORE_MODULE = ".".join(("src", "core", "Shems"))
LEGACY_USER_ROLE_MODULE = ".".join(("src", "DB", "Repository", "UserRepository", "Enums"))
LEGACY_SHEMS_MODULES = (
    LEGACY_API_MODULE,
    LEGACY_CORE_MODULE,
    ".".join(("src", "DB", "Repository", "BookRepository", "Shems")),
    ".".join(("src", "DB", "Repository", "BookChapterRepository", "Shems")),
    ".".join(("src", "DB", "Repository", "LogRepository", "Shems")),
    ".".join(("src", "DB", "Repository", "UserRepository", "Shems")),
)


def test_typo_dependencices_module_is_forbidden() -> None:
    importlib.invalidate_caches()

    forbidden_module = ".".join(("src", "api", "Dependencices"))

    assert importlib.util.find_spec(forbidden_module) is None


def test_pydantic_schemas_are_available_from_schemas_package() -> None:
    importlib.invalidate_caches()

    books = importlib.import_module("src.schemas.books")
    users = importlib.import_module("src.schemas.users")
    config = importlib.import_module("src.schemas.config")
    enums = importlib.import_module("src.schemas.enums")

    assert books.BookCreate
    assert users.UserRead
    assert config.DatabaseSettings
    assert enums.UserRole


def test_legacy_shems_modules_are_removed() -> None:
    importlib.invalidate_caches()

    source_root = Path(__file__).resolve().parents[1] / "src"
    existing_files = sorted(
        str(path.relative_to(source_root.parent))
        for path in source_root.rglob("Shems.py")
    )
    existing_modules = [
        module
        for module in LEGACY_SHEMS_MODULES
        if importlib.util.find_spec(module) is not None
    ]

    assert existing_files == []
    assert existing_modules == []


def test_legacy_user_role_enums_module_is_removed() -> None:
    importlib.invalidate_caches()

    project_root = Path(__file__).resolve().parents[1]
    legacy_file = project_root / "src" / "DB" / "Repository" / "UserRepository" / "Enums.py"

    assert not legacy_file.exists()
    assert importlib.util.find_spec(LEGACY_USER_ROLE_MODULE) is None


def test_runtime_modules_do_not_import_legacy_shems_modules() -> None:
    project_root = Path(__file__).resolve().parents[1]
    scan_roots = (project_root / "src", project_root / "tests")
    offenders: list[str] = []

    for scan_root in scan_roots:
        for path in scan_root.rglob("*.py"):
            if path.name == "Shems.py" or path == Path(__file__).resolve():
                continue

            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    imports_legacy_module = (
                        module in LEGACY_SHEMS_MODULES
                        or module == LEGACY_USER_ROLE_MODULE
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
                        offenders.append(f"{path.relative_to(project_root)}:{node.lineno}")

                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name
                        imports_legacy_module = (
                            module in LEGACY_SHEMS_MODULES
                            or module == LEGACY_USER_ROLE_MODULE
                            or (
                                module.startswith("src.DB.Repository.")
                                and module.endswith(".Shems")
                            )
                        )
                        if imports_legacy_module:
                            offenders.append(f"{path.relative_to(project_root)}:{node.lineno}")

    assert offenders == []


def test_favorite_service_does_not_import_concrete_repository_classes() -> None:
    project_root = Path(__file__).resolve().parents[1]
    path = project_root / "src" / "application" / "services" / "favorite_service.py"
    forbidden_names = {"BookRepository", "FavoriteBookRepository", "LogRepository"}
    offenders: list[str] = []

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue

        module = node.module or ""
        if not module.startswith("src.DB.Repository."):
            continue

        imported_names = {alias.name for alias in node.names}
        if forbidden_names & imported_names:
            offenders.append(f"{path.relative_to(project_root)}:{node.lineno}")

    assert offenders == []
