import ast
import importlib
import importlib.util
from pathlib import Path

PACKAGE_ROOT = "api_manager_books"
LEGACY_IMPORT_ROOT = "s" + "rc"
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


def safe_find_spec(module_name: str):
    try:
        return importlib.util.find_spec(module_name)
    except ModuleNotFoundError:
        return None


def test_runtime_and_tests_do_not_import_legacy_src_namespace() -> None:
    project_root = Path(__file__).resolve().parents[1]
    scan_paths = [project_root / "main.py"]
    scan_paths.extend((project_root / "src").rglob("*.py"))
    scan_paths.extend((project_root / "tests").rglob("*.py"))
    offenders: list[str] = []

    for path in scan_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module_root = (node.module or "").split(".", maxsplit=1)[0]
                if module_root == LEGACY_IMPORT_ROOT:
                    offenders.append(f"{path.relative_to(project_root)}:{node.lineno}")

            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_root = alias.name.split(".", maxsplit=1)[0]
                    if module_root == LEGACY_IMPORT_ROOT:
                        offenders.append(f"{path.relative_to(project_root)}:{node.lineno}")

    assert offenders == []


def test_runtime_and_tests_do_not_reference_legacy_source_paths() -> None:
    project_root = Path(__file__).resolve().parents[1]
    scan_paths = [project_root / "main.py"]
    scan_paths.extend((project_root / "src").rglob("*.py"))
    scan_paths.extend((project_root / "tests").rglob("*.py"))
    legacy_roots = ("api", "DB", "core", "security", "application", "bootstrap", "schemas")
    forbidden_fragments = [
        separator.join((LEGACY_IMPORT_ROOT, root))
        for root in legacy_roots
        for separator in ("/", ".")
    ]
    offenders: list[str] = []

    for path in scan_paths:
        if not path.exists():
            continue

        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for fragment in forbidden_fragments:
                if fragment in line:
                    offenders.append(
                        f"{path.relative_to(project_root)}:{line_number} contains {fragment}"
                    )

    assert offenders == []


def test_typo_dependencices_module_is_forbidden() -> None:
    importlib.invalidate_caches()

    forbidden_module = ".".join(("src", "api", "Dependencices"))

    assert safe_find_spec(forbidden_module) is None


def test_pydantic_schemas_are_available_from_schemas_package() -> None:
    importlib.invalidate_caches()

    books = importlib.import_module("api_manager_books.schemas.books")
    users = importlib.import_module("api_manager_books.schemas.users")
    config = importlib.import_module("api_manager_books.schemas.config")
    enums = importlib.import_module("api_manager_books.schemas.enums")

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
        if safe_find_spec(module) is not None
    ]

    assert existing_files == []
    assert existing_modules == []


def test_legacy_user_role_enums_module_is_removed() -> None:
    importlib.invalidate_caches()

    project_root = Path(__file__).resolve().parents[1]
    legacy_file = project_root / "src" / "DB" / "Repository" / "UserRepository" / "Enums.py"

    assert not legacy_file.exists()
    assert safe_find_spec(LEGACY_USER_ROLE_MODULE) is None


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
                            module.startswith("api_manager_books.db.Repository.")
                            and module.endswith(".Shems")
                        )
                    )
                    imports_legacy_name = (
                        module.startswith("api_manager_books.db.Repository.")
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
                                module.startswith("api_manager_books.db.Repository.")
                                and module.endswith(".Shems")
                            )
                        )
                        if imports_legacy_module:
                            offenders.append(f"{path.relative_to(project_root)}:{node.lineno}")

    assert offenders == []


def test_favorite_service_does_not_import_concrete_repository_classes() -> None:
    project_root = Path(__file__).resolve().parents[1]
    path = project_root / "src" / PACKAGE_ROOT / "application" / "services" / "favorite_service.py"
    forbidden_names = {"BookRepository", "FavoriteBookRepository", "LogRepository"}
    offenders: list[str] = []

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue

        module = node.module or ""
        if not module.startswith("api_manager_books.db.Repository."):
            continue

        imported_names = {alias.name for alias in node.names}
        if forbidden_names & imported_names:
            offenders.append(f"{path.relative_to(project_root)}:{node.lineno}")

    assert offenders == []


def test_book_service_does_not_import_concrete_repository_classes() -> None:
    project_root = Path(__file__).resolve().parents[1]
    path = project_root / "src" / PACKAGE_ROOT / "application" / "services" / "book_service.py"
    forbidden_names = {"BookRepository", "FavoriteBookRepository", "LogRepository"}
    offenders: list[str] = []

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue

        module = node.module or ""
        if not module.startswith("api_manager_books.db.Repository."):
            continue

        imported_names = {alias.name for alias in node.names}
        if forbidden_names & imported_names:
            offenders.append(f"{path.relative_to(project_root)}:{node.lineno}")

    assert offenders == []


def test_book_file_service_does_not_import_concrete_repository_classes() -> None:
    project_root = Path(__file__).resolve().parents[1]
    path = project_root / "src" / PACKAGE_ROOT / "application" / "services" / "book_file_service.py"
    forbidden_names = {"BookRepository", "LogRepository"}
    offenders: list[str] = []

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue

        module = node.module or ""
        if not module.startswith("api_manager_books.db.Repository."):
            continue

        imported_names = {alias.name for alias in node.names}
        if forbidden_names & imported_names:
            offenders.append(f"{path.relative_to(project_root)}:{node.lineno}")

    assert offenders == []


def test_chapter_service_does_not_import_concrete_repository_classes() -> None:
    project_root = Path(__file__).resolve().parents[1]
    path = project_root / "src" / PACKAGE_ROOT / "application" / "services" / "chapter_service.py"
    forbidden_names = {"BookRepository", "BookChapterRepository", "LogRepository"}
    offenders: list[str] = []

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue

        module = node.module or ""
        if not module.startswith("api_manager_books.db.Repository."):
            continue

        imported_names = {alias.name for alias in node.names}
        if forbidden_names & imported_names:
            offenders.append(f"{path.relative_to(project_root)}:{node.lineno}")

    assert offenders == []


def test_reading_history_service_does_not_import_concrete_repository_classes() -> None:
    project_root = Path(__file__).resolve().parents[1]
    path = project_root / "src" / PACKAGE_ROOT / "application" / "services" / "reading_history_service.py"
    forbidden_names = {"BookRepository", "BookChapterRepository", "LogRepository"}
    offenders: list[str] = []

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue

        module = node.module or ""
        if not module.startswith("api_manager_books.db.Repository."):
            continue

        imported_names = {alias.name for alias in node.names}
        if forbidden_names & imported_names:
            offenders.append(f"{path.relative_to(project_root)}:{node.lineno}")

    assert offenders == []


def test_user_service_does_not_import_concrete_repository_classes() -> None:
    project_root = Path(__file__).resolve().parents[1]
    path = project_root / "src" / PACKAGE_ROOT / "application" / "services" / "user_service.py"
    forbidden_names = {"UserRepository", "LogRepository"}
    offenders: list[str] = []

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue

        module = node.module or ""
        if not module.startswith("api_manager_books.db.Repository."):
            continue

        imported_names = {alias.name for alias in node.names}
        if forbidden_names & imported_names:
            offenders.append(f"{path.relative_to(project_root)}:{node.lineno}")

    assert offenders == []


def test_settings_service_does_not_import_concrete_settings_infrastructure() -> None:
    project_root = Path(__file__).resolve().parents[1]
    path = project_root / "src" / PACKAGE_ROOT / "application" / "services" / "settings_service.py"
    forbidden_modules = {
        "api_manager_books.db.Manager.manager",
        "api_manager_books.db.base",
        "api_manager_books.config.config",
    }
    forbidden_from_imports = {
        "api_manager_books.config.config": {"SettingsManager"},
    }
    forbidden_from_modules = {"api_manager_books.db.Manager.manager", "api_manager_books.db.base"}
    offenders: list[str] = []

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_modules:
                    offenders.append(
                        f"{path.relative_to(project_root)}:{node.lineno} imports "
                        f"forbidden module {alias.name}"
                    )

        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported_names = {alias.name for alias in node.names}
            if module in forbidden_from_modules:
                offenders.append(
                    f"{path.relative_to(project_root)}:{node.lineno} imports "
                    f"{', '.join(sorted(imported_names))} from forbidden module "
                    f"{module}"
                )

            for forbidden_module, forbidden_names in forbidden_from_imports.items():
                forbidden_direct_names = forbidden_names & imported_names
                if module == forbidden_module and forbidden_direct_names:
                    offenders.append(
                        f"{path.relative_to(project_root)}:{node.lineno} imports "
                        f"{', '.join(sorted(forbidden_direct_names))} from "
                        f"{forbidden_module}"
                    )

            for alias in node.names:
                imported_module = f"{module}.{alias.name}" if module else alias.name
                if imported_module in forbidden_modules:
                    offenders.append(
                        f"{path.relative_to(project_root)}:{node.lineno} imports "
                        f"forbidden module {imported_module} via {module}"
                    )

            if module in forbidden_modules and "*" in imported_names:
                offenders.append(
                    f"{path.relative_to(project_root)}:{node.lineno} imports "
                    f"everything from forbidden module {module}"
                )

    assert offenders == []
