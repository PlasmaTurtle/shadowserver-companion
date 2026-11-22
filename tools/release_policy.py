"""Shared distribution allowlist: module program assets and reviewed test fixtures."""

from pathlib import Path

INSTALLED_TOP_FILES = (
    "run.py",
    "VERSION",
    "RELEASE.json",
    "README.md",
    "CHANGELOG.md",
    "SECURITY.md",
)
TOP_FILES = {
    *INSTALLED_TOP_FILES,
    "AGENTS.md",
    "requirements-constraints.txt",
    "requirements-windows.txt",
    "pyproject.toml",
    "package.json",
    "Setup.cmd",
    ".gitattributes",
    "Start Workbench.cmd",
    "conftest.py",
    ".prettierignore",
    "package-lock.json",
    ".gitignore",
    "Start Demo.cmd",
    "requirements.txt",
    "requirements-dev.txt",
}
DOCS = {
    "history/releases/CHANGELOG_PRE_0.11.md",
    "ARCHITECTURE.md",
    "ISSUES.md",
    "DEVELOPMENT.md",
    "DEPENDENCIES.md",
    "WINDOWS_ACCEPTANCE.md",
    "history/validation/VALIDATION_0120.md",
    "history/releases/RELEASE_0985.md",
    "history/design/WORKSPACE_EVOLUTION_0110.md",
    "history/reviews/MAINTENANCE_AUDIT_0999.md",
    "components.json",
    "history/design/OBSERVATORY_ENTITY_MAP_0100.md",
    "history/validation/VALIDATION_097.md",
    "history/releases/RELEASE_0981.md",
    "history/validation/module-reorganization-validation.md",
    "history/validation/maintenance-2026-11-21.md",
    "history/validation/full-build-2026-11-21.md",
    "history/validation/intake-review-2026-11-22.md",
    "program-map.json",
    "history/releases/RELEASE_0992.md",
    "history/design/ANALYST_WORKFLOW_0101.md",
    "GITHUB_MAINTENANCE.md",
    "history/releases/RELEASE_0990.md",
    "history/README.md",
    "history/releases/RELEASE_0988.md",
    "history/releases/RELEASE_095.md",
    "history/releases/RELEASE_0989.md",
    "history/releases/RELEASE_096.md",
    "history/releases/RELEASE_098.md",
    "history/validation/VALIDATION_0981.md",
    "history/releases/RELEASE_0993.md",
    "history/reviews/OBSERVATORY_FIELD_REVIEW_2026_11_13.md",
    "history/releases/RELEASE_097.md",
    "history/reviews/APPENDIX_REVIEW.md",
    "history/reviews/PROFESSIONAL_REVIEW.md",
    "INPUT_VALIDATION.md",
    "history/validation/VALIDATION_096.md",
    "history/design/REQUIREMENTS_098.html",
    "history/releases/RELEASE_0983.md",
    "history/releases/RELEASE_0982.md",
    "history/releases/RELEASE_0986.md",
    "history/releases/RELEASE_0987.md",
    "history/releases/RELEASE_0995.md",
    "history/reviews/INSTALL_SETTINGS_RELEASE_AUDIT.md",
    "program-map.html",
    "history/design/REPORT_REQUIREMENTS_070.md",
    "history/reviews/AUDIT_0985.md",
    "history/validation/VALIDATION_098.md",
    "history/validation/VALIDATION_0101.md",
    "history/releases/RELEASE_0994.md",
    "history/releases/RELEASE_0984.md",
    "README.md",
    "history/reviews/PERFORMANCE_0986.md",
    "history/reviews/DATABASE_AUDIT_0101.md",
    "history/reviews/GITHUB_REPOSITORY_AUDIT_2026_11_14.md",
    "history/validation/VALIDATION_090.md",
    "history/validation/VALIDATION_0100.md",
    "history/validation/VALIDATION_095.md",
    "history/validation/VALIDATION_0110.md",
    "history/reviews/NOTIFICATION_REVIEW.md",
    "history/releases/RELEASE_0991.md",
    "USER_GUIDE.md",
}
MODULES = {
    "investigations",
    "leads",
    "settings",
    "attribution",
    "workspace",
    "observatory",
    "entities",
    "accretion",
    "ui",
    "activity",
    "library",
    "tools",
}
IGNORED = {
    "node_modules",
    "__pycache__",
    ".ruff_cache",
    "dist",
    "build",
    ".venv",
    ".git",
    ".pytest_cache",
}
FIXTURES = {"intake_fixture.xlsx", "http-contract.json", "selection_policy_sample.csv"}
MODULE_FIXTURES = {
    "modules/accretion/tests/fixtures/windows_schedule_normalization.json",
    "modules/tools/tests/fixtures/website_capture_live_urls.json",
    "modules/tools/tests/fixtures/website_capture_green.webm",
}
PRIVATE_NAMES = {"shadowserver_labeled_sample_2026-11-05.csv"}
DEVELOPMENT_ONLY = {
    "modules/ui/fonts/NotoSansSC-Variable.ttf",
    "tools/windows_installer/requirements-cp314.txt",
    "tools/windows_installer/wheel-lock.json",
}
SOURCE_ONLY = {
    "tools/ensure_environment.cmd",
    "modules/attribution/tools/Attribution.cmd",
}
MODULE_FOLDERS = {
    "components",
    "tools",
    "helpers",
    "databases",
    "static",
    "tests",
    "docs",
    "fonts",
    "schemas",
    "resources",
}
ASSETS = {
    "modules/library/resources/defaults.py",
    "modules/library/resources/report_explainer_data.py",
    "modules/library/resources/finding_explainer_data.py",
    "modules/ui/static/cosmic-data-field.png",
    "modules/ui/static/favicon.png",
    "modules/ui/static/favicon.ico",
    "tools/windows_installer/assets/setup-sidebar.svg",
    "tools/windows_installer/assets/setup-sidebar.bmp",
    "tools/windows_installer/assets/setup-header.svg",
    "tools/windows_installer/assets/setup-header.bmp",
    "tools/windows_installer/assets/uninstall-sidebar.svg",
    "tools/windows_installer/assets/uninstall-sidebar.bmp",
}
PATCHES = {
    "modules/accretion/components/shadowserver_api/credentials.py.patch",
    "modules/accretion/components/shadowserver_api/download.py.patch",
    "modules/accretion/components/shadowserver_api/__init__.py.patch",
}
SYNTHETIC_EXAMPLES = {
    "modules/accretion/resources/examples/intake_fixture.xlsx",
    "modules/leads/resources/examples/qualified-lead.json",
    "modules/investigations/resources/examples/Sample_Notification.pdf",
    "modules/investigations/resources/examples/Sample_Notification.docx",
    "modules/investigations/resources/examples/Multiple_CVE_Notification.pdf",
    "modules/investigations/resources/examples/Multiple_CVE_Notification.docx",
}


def distributable(relative: Path, *, installed=False) -> bool:
    """Admit source by ownership/category; user data never becomes a program asset."""
    parts = relative.parts
    if not parts or relative.is_absolute() or ".." in parts:
        return False
    if any(p in IGNORED or p.endswith(".egg-info") for p in parts):
        return False
    name = relative.as_posix()
    if name in DEVELOPMENT_ONLY or relative.name in PRIVATE_NAMES:
        return False
    if relative.suffix.casefold() in {".pyc", ".pyo", ".sqlite3", ".db", ".log"}:
        return False
    if installed and ("tests" in parts or "wheelhouse" in parts or name in SOURCE_ONLY):
        return False
    if len(parts) == 1:
        return relative.name in (INSTALLED_TOP_FILES if installed else TOP_FILES)
    if parts[0] == ".vscode":
        return (
            not installed
            and len(parts) == 2
            and relative.name
            in {
                "launch.json",
                "tasks.json",
                "settings.json",
                "extensions.json",
            }
        )
    if parts[0] == "docs":
        return Path(*parts[1:]).as_posix() in DOCS
    if parts[:2] == ("tests", "fixtures"):
        return len(parts) == 3 and relative.name in FIXTURES and not installed
    if (
        name in ASSETS
        or name in PATCHES
        or name in MODULE_FIXTURES
        or name in SYNTHETIC_EXAMPLES
        or name == "tools/program_map_template.html"
    ):
        return True
    category = parts[0]
    if category == "modules":
        if name == "modules/__init__.py":
            return True
        if len(parts) < 3 or parts[1] not in MODULES:
            return False
        if len(parts) == 3:
            return parts[2] == "__init__.py"
        category = parts[2]
        if category not in MODULE_FOLDERS:
            return False
        if relative.name == ".gitkeep":
            return not installed and len(parts) == 4
        if "tests" in parts[2:]:
            category = "tests"
        if (
            parts[:4] == ("modules", "attribution", "components", "engine")
            and "examples" in parts[4:]
        ):
            # These standalone lookup exports are not synthetic fixtures.
            return False
        if category == "resources":
            return (
                parts[:4] == ("modules", "investigations", "resources", "timezones")
                and len(parts) == 5
                and relative.name
                in {
                    "America_New_York.tzif",
                    "LICENSE",
                    "LICENSE_APACHE",
                    "provenance.json",
                }
            )
        if category == "schemas":
            return (
                parts[:3] == ("modules", "accretion", "schemas")
                and len(parts) == 4
                and relative.name
                in {
                    "shadowserver-reports.json",
                    "shadowserver-reports.meta.json",
                }
            )
    allowed_extensions = {
        "static": {".js", ".css", ".html", ".svg", ".json", ".txt"},
        "fonts": {".ttf", ".woff", ".json", ".txt"},
        "wheelhouse": {".whl"},
        "tests": {".py", ".cjs", ".js", ".md"},
        "tools": {".py", ".nsi", ".json", ".txt", ".md", ".ps1", ".cmd"},
        "components": {".py", ".toml", ".md", ".txt", ".json", ".whl", ".cmd"},
        "helpers": {".py"},
        "databases": {".py", ".sql", ".md"},
        "docs": {".md", ".html"},
    }
    # Legacy loose application folders have no ownership in the current distribution.
    if parts[0] not in {"modules", "tests", "tools", "wheelhouse"}:
        return False
    if relative.suffix.casefold() not in allowed_extensions.get(category, set()):
        return False
    return not any(p.startswith(".") for p in parts)
