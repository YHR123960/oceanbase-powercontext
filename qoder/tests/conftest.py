import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from fake_powercontext import FakePowerContext  # noqa: E402
from yanxi.store import Workbench  # noqa: E402


@pytest.fixture
def fake() -> FakePowerContext:
    return FakePowerContext()


@pytest.fixture
def wb(fake: FakePowerContext) -> Workbench:
    return Workbench(fake, workspace="unit")


@pytest.fixture
def live_url() -> str:
    """URL of a real PowerContext Server, or skip when it is not running."""
    from yanxi.pc import PCClient, PCError

    url = "http://127.0.0.1:2893"
    try:
        PCClient(base_url=url).server_info()
    except PCError as exc:
        pytest.skip(f"PowerContext Server not reachable at {url}: {exc.message}. "
                    "Start it with: bash scripts/start_pc.sh")
    return url
