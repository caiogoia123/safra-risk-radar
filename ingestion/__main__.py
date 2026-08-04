"""Run the full extract-load: python -m ingestion [--target dev|prod] [--force]"""

import argparse

from . import conab, warehouse


def main() -> None:
    parser = argparse.ArgumentParser(description="Safra Risk Radar extract-load")
    parser.add_argument("--target", default="dev", choices=["dev", "prod"])
    parser.add_argument("--force", action="store_true", help="re-download cached raw files")
    args = parser.parse_args()

    conab.run(force=args.force)
    warehouse.run(target=args.target)


if __name__ == "__main__":
    main()
