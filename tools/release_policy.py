"""Shared distribution allowlist: program assets and safe synthetic fixtures only."""

from pathlib import Path

TOP_FILES = {
    "README.md",
    "CHANGELOG.md",
    "VALIDATION.md",
    "DEPENDENCIES.md",
    "VERSION",
    "RELEASE.json",
    "HOME_VALIDATION.md",
    "REPORT_REQUIREMENTS.md",
    "run.py",
    "excel_intake.py",
    "Setup.cmd",
    "Start Workbench.cmd",
    "Start Demo.cmd",
    "Attribution.cmd",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-constraints.txt",
    "requirements-windows.txt",
    "wheelhouse-sha256.json",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    ".prettierrc.json",
    ".prettierignore",
    ".gitignore",
    ".gitattributes",
    "ARCHITECTURE.md",
    "DEVELOPMENT.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "SUPPORT.md",
}
FOLDERS = {
    "workbench",
    "docs",
    "static",
    "schemas",
    "components",
    "tests",
    "examples",
    "fonts",
    "resources",
    "tools",
    "wheelhouse",
    ".vscode",
}
IGNORED = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".git",
    ".venv",
    "build",
    "dist",
    "node_modules",
}
EXAMPLES = {
    "Sample_Notification.pdf",
    "Sample_Notification.docx",
    "qualified-lead.json",
    "intake_fixture.xlsx",
    "Multiple_CVE_Notification.pdf",
    "Multiple_CVE_Notification.docx",
}
# Only generated, documented synthetic source rows are distributable.
FIXTURES = {"intake_fixture.xlsx", "selection_policy_sample.csv", "http-contract-070.json"}
PRIVATE_NAMES = {"shadowserver_labeled_sample_2026-11-05.csv"}
DEVELOPMENT_ONLY = {"fonts/NotoSansSC-Variable.ttf"}


def distributable(relative: Path, *, installed=False) -> bool:
    parts = relative.parts
    if not parts or relative.is_absolute() or ".." in parts:
        return False
    if any(p in IGNORED or p.endswith(".egg-info") for p in parts):
        return False
    if relative.as_posix() in DEVELOPMENT_ONLY or relative.as_posix() in {
        "tools/windows_installer/requirements-cp314.txt",
        "tools/windows_installer/wheel-lock.json",
    }:
        return False
    if relative.name in PRIVATE_NAMES or relative.suffix.casefold() in {
        ".pyc",
        ".pyo",
        ".sqlite3",
        ".db",
        ".log",
    }:
        return False
    if len(parts) == 1:
        return relative.name in TOP_FILES
    if parts[0] not in FOLDERS:
        return False
    if parts[0] == "resources":
        return (
            len(parts) == 3
            and parts[1] == "timezones"
            and parts[2]
            in {"America_New_York.tzif", "LICENSE", "LICENSE_APACHE", "provenance.json"}
        )
    if parts[0] == ".vscode":
        return (
            not installed
            and len(parts) == 2
            and relative.name in {"launch.json", "tasks.json", "settings.json", "extensions.json"}
        )
    if parts[0] == "docs":
        return len(parts) == 2 and relative.name in {
            "components.json",
            "program-map.json",
            "program-map.html",
            "MODULE_GUIDE.md",
            "USER_GUIDE.md",
            "SOFTWARE_UPDATES.md",
            "INSTALL_SETTINGS_RELEASE_AUDIT.md",
            "APPENDIX_REVIEW.md",
            "DATA_MANAGEMENT.md",
            "RELEASE_095.md",
            "RELEASE_096.md",
            "RELEASE_097.md",
            "RELEASE_098.md",
            "RELEASE_0981.md",
            "RELEASE_0982.md",
            "RELEASE_0983.md",
            "RELEASE_0984.md",
            "RELEASE_0985.md",
            "AUDIT_0985.md",
            "RELEASE_0986.md",
            "PERFORMANCE_0986.md",
            "RELEASE_0987.md",
            "RELEASE_0988.md",
            "RELEASE_0989.md",
            "RELEASE_0990.md",
            "RELEASE_0991.md",
            "RELEASE_0992.md",
            "RELEASE_0993.md",
            "RELEASE_0994.md",
            "RELEASE_0995.md",
            "OBSERVATORY_ACCEPTANCE.md",
            "PROFESSIONAL_REVIEW.md",
            "NOTIFICATION_REVIEW.md",
            "INPUT_VALIDATION.md",
            "OBSERVATORY_FIELD_REVIEW_2026_11_13.md",
            "MAINTENANCE_AUDIT_0999.md",
            "OBSERVATORY_ENTITY_MAP_0100.md",
            "ANALYST_WORKFLOW_0101.md",
            "DATABASE_AUDIT_0101.md",
            "WORKSPACE_EVOLUTION_0110.md",
            "VALIDATION_0101.md",
            "VALIDATION_0110.md",
            "VALIDATION_0100.md",
            "VALIDATION_0981.md",
            "VALIDATION_098.md",
            "REQUIREMENTS_098.html",
            "VALIDATION_097.md",
            "VALIDATION_095.md",
            "VALIDATION_096.md",
            "VALIDATION_090.md",
        }
    if parts[0] == "examples":
        return len(parts) == 2 and relative.name in EXAMPLES
    if parts[:2] == ("components", "attribution") and "examples" in parts[2:]:
        # Legacy module export contains a real registration lookup; useful in
        # development but deliberately excluded from distributable fixtures.
        return False
    if parts[:2] == ("tests", "fixtures"):
        return len(parts) == 3 and relative.name in FIXTURES and not installed
    if installed and (parts[0] in {"tests", "wheelhouse"} or "tests" in parts):
        return False
    # Test attachments must be explicitly reviewed rather than automatically
    # swept into a release whenever someone adds them to a checkout.
    allowed_extensions = {
        "workbench": {".py"},
        "static": {".js", ".css", ".html", ".svg", ".json", ".txt"},
        "schemas": {".json"},
        "fonts": {".ttf", ".woff", ".json", ".txt"},
        "wheelhouse": {".whl"},
        "tests": {".py", ".cjs", ".js", ".md"},
        "tools": {".py", ".nsi", ".json", ".txt", ".md", ".ps1"},
        "components": {".py", ".toml", ".md", ".txt", ".json", ".whl", ".cmd"},
    }
    if relative.as_posix() in {
        "components/shadowserver_api/download.py.patch",
        "components/shadowserver_api/__init__.py.patch",
    }:
        return True
    if relative.as_posix() in {
        "static/cosmic-data-field.png",
        "static/favicon.png",
        "static/favicon.ico",
        "tools/windows_installer/assets/setup-sidebar.svg",
        "tools/windows_installer/assets/setup-sidebar.bmp",
        "tools/windows_installer/assets/setup-header.svg",
        "tools/windows_installer/assets/setup-header.bmp",
        "tools/windows_installer/assets/uninstall-sidebar.svg",
        "tools/windows_installer/assets/uninstall-sidebar.bmp",
    }:
        return True
    if relative.as_posix() == "tools/program_map_template.html":
        return True
    if relative.suffix.casefold() not in allowed_extensions.get(parts[0], set()):
        return False
    if parts[0] == "schemas" and relative.name not in {
        "shadowserver-reports.json",
        "shadowserver-reports.meta.json",
    }:
        return False
    return not any(p.startswith(".") for p in parts)
