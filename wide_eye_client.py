"""Wide Eye API client (mock).

Wide Eye exposes no API yet, so this client serves canned JSON responses that
mirror the agreed response contract. When the real API exists, replace the body
of `fetch` with a `requests.get(...)`; nothing else in the project changes.
"""
import json
from pathlib import Path

SAMPLE_FILE = Path(__file__).with_name("wide_eye_sample.json")


class WideEyeClient:
    """Returns Wide Eye recommendation payloads for a given sample input."""

    def __init__(self, sample_file: Path = SAMPLE_FILE):
        """Load the canned responses once; keys are scenario ids (S1, S2, S3)."""
        self._responses = json.loads(Path(sample_file).read_text(encoding="utf-8"))

    def list_scenarios(self) -> list[dict]:
        """Return `[{id, query}]` so a UI can offer the available inputs."""
        return [{"id": sid, "query": body["query"]} for sid, body in self._responses.items()]

    def fetch(self, scenario_id: str) -> dict:
        """Return the full Wide Eye response for one scenario.

        Real implementation sketch:
            requests.get(f"{BASE_URL}/recommendations", params={...}, headers={...}).json()
        """
        if scenario_id not in self._responses:
            raise KeyError(f"Unknown Wide Eye scenario: {scenario_id}")
        return self._responses[scenario_id]
