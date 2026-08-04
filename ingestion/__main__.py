"""Run the full extract-load: python -m ingestion [--target dev|prod] [--force]"""

import argparse

from . import conab, geo, ibge_pam, nasa_power, warehouse


def main() -> None:
    parser = argparse.ArgumentParser(description="Safra Risk Radar extract-load")
    parser.add_argument("--target", default="dev", choices=["dev", "prod"])
    parser.add_argument("--force", action="store_true", help="re-download cached raw files")
    args = parser.parse_args()

    conab.run(force=args.force)
    ibge_pam.run(force=args.force)
    # Depends on the PAM output: hubs are ranked before their centroids are fetched.
    geo.run(force=args.force)
    # Depends on the hubs: one weather request per distinct grid cell.
    nasa_power.run(force=args.force)
    warehouse.run(target=args.target)


if __name__ == "__main__":
    main()
