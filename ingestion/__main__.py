"""Run the full extract-load: python -m ingestion [--target dev|prod] [--force]"""

import argparse

from . import conab, geo, ibge_pam, nasa_power, warehouse


def main() -> None:
    parser = argparse.ArgumentParser(description="Safra Risk Radar extract-load")
    parser.add_argument("--target", default="dev", choices=["dev", "prod"])
    # All-or-nothing across every source, so it also re-runs the 510 IBGE
    # centroid requests that were deliberately turned into a versioned input.
    # Refreshing weather alone is what --allow-stale's absence already does:
    # POWER cells that stop before the requested end date are re-fetched.
    parser.add_argument("--force", action="store_true", help="re-download cached raw files")
    parser.add_argument(
        "--allow-stale",
        action="store_true",
        help="keep cached NASA POWER cells that stop before the requested end "
             "date instead of re-downloading them (warns loudly)",
    )
    args = parser.parse_args()

    conab.run(force=args.force)
    ibge_pam.run(force=args.force)
    # Depends on the PAM output: hubs are ranked before their centroids are fetched.
    geo.run(force=args.force)
    # Depends on the hubs: one weather request per distinct grid cell.
    nasa_power.run(force=args.force, allow_stale=args.allow_stale)
    warehouse.run(target=args.target)


if __name__ == "__main__":
    main()
