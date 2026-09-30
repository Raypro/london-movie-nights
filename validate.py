"""Reject an empty refresh so the last useful published page stays up."""

import json
import sys
from pathlib import Path


def validate(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["timeZone"] == "America/Toronto"
    assert len(data["dates"]) == 14
    assert len(data["cinemas"]) == 5
    assert any(cinema["status"] in {"ok", "partial"} for cinema in data["cinemas"]), "No cinema source worked"
    assert data["screenings"], "No showtimes were collected"
    assert data["picks"], "Horror picks are empty"
    print(f"Valid snapshot: {len(data['screenings'])} showtimes, {len(data['picks'])} horror picks")


if __name__ == "__main__":
    validate(Path(sys.argv[1]))
