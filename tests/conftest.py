import os
from pathlib import Path
import pytest

@pytest.fixture
def temp_workspace(tmp_path: Path):
    return tmp_path / "workspace"
