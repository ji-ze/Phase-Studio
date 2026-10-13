"""Standalone distribution entry point; scientific UI remains shared with Jana."""
import json
import sys
from pathlib import Path
from phase_studio.version import VERSION


def _catalog_check_output_path(argv):
    """Return the hidden release-diagnostic output path, when requested."""
    try:
        index = argv.index("--sharped-catalog-check")
    except ValueError:
        return None
    if index + 1 >= len(argv):
        raise ValueError("--sharped-catalog-check requires an output JSON path")
    return Path(argv[index + 1]).expanduser().resolve()


def _run_catalog_check(output_path):
    """Exercise the frozen HTTPS stack without exposing credentials."""
    from phase_studio.sharped_server_client import DEFAULT_SERVER_URL, SharpEDServerClient

    report = {
        "version": VERSION,
        "base_url": DEFAULT_SERVER_URL,
        "certificate_verification": True,
        "hostname_verification": True,
    }
    try:
        client = SharpEDServerClient(base_url=DEFAULT_SERVER_URL, timeout=30.0)
        result = client.get_models()
        report.update({
            "ok": True,
            "tls_provider": client.tls_fallback_message,
            "default_model": result.default_model,
            "models": result.models,
        })
        exit_code = 0
    except Exception as exc:
        report.update({
            "ok": False,
            "error_category": str(getattr(exc, "category", "unknown")),
            "error": str(exc),
        })
        exit_code = 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return exit_code


def main():
    if "--version" in sys.argv:
        print(VERSION)
        return 0
    catalog_output = _catalog_check_output_path(sys.argv)
    if catalog_output is not None:
        return _run_catalog_check(catalog_output)
    if "--brand-font-check" in sys.argv:
        index = sys.argv.index("--brand-font-check")
        if index + 1 >= len(sys.argv):
            raise ValueError("--brand-font-check requires an output JSON path")
        from PySide6.QtWidgets import QApplication
        from phase_studio.ui_branding import phase_studio_brand_runtime_report
        from phase_studio.ui_style import apply_phase_studio_style
        app = QApplication.instance() or QApplication([sys.argv[0]])
        apply_phase_studio_style(app)
        output = Path(sys.argv[index + 1]).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(phase_studio_brand_runtime_report("standalone"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return 0
    from phase_studio.app import main as run_application
    return run_application()


if __name__ == "__main__":
    raise SystemExit(main())
