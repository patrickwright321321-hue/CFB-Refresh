"""
Highlightly compatibility-test scaffold.

This file intentionally does NOT write to the production Google Sheet.
The API key is read only from the HIGHLIGHTLY_API_KEY environment variable.
"""

import os


def main() -> None:
    api_key = os.environ.get("HIGHLIGHTLY_API_KEY")
    if not api_key:
        raise SystemExit("HIGHLIGHTLY_API_KEY is missing")

    # Never print or persist the key.
    print("Highlightly test environment is ready.")
    print("Production workbook writes are disabled in this test scaffold.")


if __name__ == "__main__":
    main()
