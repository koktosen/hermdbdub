"""Crypto Fear & Greed index (alternative.me, no key) → data/fng.json."""
import requests

from common import write_json


def main() -> None:
    r = requests.get("https://api.alternative.me/fng/", params={"limit": 8}, timeout=15)
    r.raise_for_status()
    rows = r.json()["data"]
    write_json("fng", {"value": int(rows[0]["value"]), "label": rows[0]["value_classification"],
                       "history": [int(x["value"]) for x in reversed(rows)]})


if __name__ == "__main__":
    main()
