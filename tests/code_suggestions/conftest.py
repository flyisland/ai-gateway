from pathlib import Path

import pytest


@pytest.fixture(name="tpl_assets_codegen_dir")
def tpl_assets_codegen_dir_fixture(assets_dir) -> Path:
    tpl_dir = assets_dir / "tpl"
    return tpl_dir / "codegen"
