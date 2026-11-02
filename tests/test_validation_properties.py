from pathlib import Path

import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from silicondraft import validate_scenario


def _write_scenario(path: Path, die_size_mm: tuple[float, float], edge_exclusion_mm: float) -> Path:
    document = {
        "schema_version": 1,
        "product": {"name": "GEN55LOGIC"},
        "wafer": {
            "diameter_mm": 300,
            "die_size_mm": list(die_size_mm),
            "edge_exclusion_mm": edge_exclusion_mm,
        },
        "seed": 1,
    }
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


@settings(
    max_examples=50,
    deadline=None,
    # tmp_path is reused, but each example overwrites the same two files.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    die_width=st.floats(min_value=5.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    die_height=st.floats(min_value=5.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    edge_exclusion=st.floats(min_value=0.0, max_value=25.0, allow_nan=False, allow_infinity=False),
    extra_exclusion=st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
)
def test_increasing_edge_exclusion_never_increases_die_count(
    tmp_path: Path,
    die_width: float,
    die_height: float,
    edge_exclusion: float,
    extra_exclusion: float,
) -> None:
    narrower = validate_scenario(
        _write_scenario(tmp_path / "narrower.yaml", (die_width, die_height), edge_exclusion)
    )
    wider = validate_scenario(
        _write_scenario(
            tmp_path / "wider.yaml",
            (die_width, die_height),
            edge_exclusion + extra_exclusion,
        )
    )

    assert narrower.ok is True
    assert wider.ok is True
    assert narrower.summary is not None
    assert wider.summary is not None
    assert narrower.summary.dies_per_wafer >= wider.summary.dies_per_wafer
