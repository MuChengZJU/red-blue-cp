"""0.6 backward-compat: the old ``app.service.*`` import paths must keep
resolving (to the same objects) after the rename to ``app.extract.*``.

These shims exist for 0.5.x users; they are slated for removal in 0.7.
"""
import importlib

import pytest

# Public modules that moved service/ -> extract/.
MODULES = [
    "batch", "comments", "discover", "errors", "extractor",
    "fetcher", "markdown", "model", "pipeline", "pricing",
    "storage", "urls",
]


@pytest.mark.parametrize("mod", MODULES)
def test_old_module_path_imports(mod):
    old = importlib.import_module(f"app.service.{mod}")
    new = importlib.import_module(f"app.extract.{mod}")
    assert old is not None and new is not None


def test_public_names_are_identical_objects():
    # A representative slice of the public API used across cli/web/tests.
    from app.service.extractor import ExtractResult as OldER, extract_url as old_extract
    from app.extract.extractor import ExtractResult as NewER, extract_url as new_extract
    assert OldER is NewER
    assert old_extract is new_extract

    from app.service.errors import RbcpError as OldErr
    from app.extract.errors import RbcpError as NewErr
    assert OldErr is NewErr

    from app.service.storage import Storage as OldStorage
    from app.extract.storage import Storage as NewStorage
    assert OldStorage is NewStorage


def test_private_names_forward_through_shim():
    # The shim's __getattr__ must forward underscore-prefixed names that
    # `import *` skips but the old test suite / external code relied on.
    from app.service.extractor import _download_file as old_dl
    from app.extract.extractor import _download_file as new_dl
    assert old_dl is new_dl

    from app.service.model import _format_transcription as old_ft
    from app.extract.model import _format_transcription as new_ft
    assert old_ft is new_ft


def test_submodule_attribute_access():
    # `from app.service import batch as batch_mod; batch_mod.run_batch`
    from app.service import batch as old_batch
    from app.extract import batch as new_batch
    assert old_batch.run_batch is new_batch.run_batch
