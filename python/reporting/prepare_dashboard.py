from __future__ import annotations

import shutil
from pathlib import Path

from ..common.config import PROCESSED_DIR, PROJECT_ROOT
from ..common.io_utils import publish_output_bundle

FRONTEND_DIR = PROJECT_ROOT / "frontend"
SITE_DIR = FRONTEND_DIR / "site"
DATA_FILES = (
    "metrics_summary.csv",
    "metrics_timeseries.csv",
    "monitoring_alerts.csv",
    "validation_results.csv",
    "pipeline_metadata.json",
    "series_freshness.csv",
    "source_health.csv",
)
RESEARCH_FILES = (
    "credit_regime_uncertainty.csv",
    "credit_regime_sensitivity.csv",
    "credit_lagged_correlations.csv",
    "credit_hac_regression.csv",
)
DOCUMENT_FILES = ("methodology.md", "research_memo.md")


def build() -> Path:
    """Assemble the standalone static dashboard and its generated data bundle."""
    source_files = [PROCESSED_DIR / name for name in DATA_FILES]
    research_files = [PROJECT_ROOT / "reports" / name for name in RESEARCH_FILES]
    document_sources = [
        PROJECT_ROOT / "documentation" / "methodology.md",
        PROJECT_ROOT / "reports" / "research_memo.md",
    ]
    missing = [path.name for path in source_files if not path.is_file()]
    missing.extend(path.name for path in research_files if not path.is_file())
    missing.extend(path.name for path in document_sources if not path.is_file())
    if missing:
        raise FileNotFoundError(f"Missing dashboard data files: {', '.join(missing)}")

    data_dir = SITE_DIR / "data" / "processed"
    writers = {
        SITE_DIR / "index.html": lambda path: shutil.copy2(FRONTEND_DIR / "index.html", path),
        SITE_DIR / "interest_cost_engine.js": lambda path: shutil.copy2(
            FRONTEND_DIR / "interest_cost_engine.js", path
        ),
    }
    writers.update({
        data_dir / source.name: (lambda path, src=source: shutil.copy2(src, path))
        for source in [*source_files, *research_files]
    })
    writers.update({
        SITE_DIR / name: (lambda path, src=source: shutil.copy2(src, path))
        for name, source in zip(DOCUMENT_FILES, document_sources)
    })
    publish_output_bundle(writers)
    return SITE_DIR


def main() -> int:
    site_dir = build()
    print(f"Static dashboard prepared at {site_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
