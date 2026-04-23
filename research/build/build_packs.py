from __future__ import annotations

import argparse

from research.build.packager import Packager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build downloadable research packs.")
    parser.add_argument("--conferences", nargs="*", default=None, help="Conference codes such as iclr nips icml")
    parser.add_argument("--years", nargs="*", type=int, default=None, help="Years such as 2025 2026")
    parser.add_argument("--version", default="v1", help="Pack version label")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    packager = Packager()
    results = packager.build_many(
        conferences=args.conferences,
        years=args.years,
        version=args.version,
    )
    for item in results:
        print(f"{item.pack_name} -> {item.pack_path} ({item.pack_size_bytes} bytes)")


if __name__ == "__main__":
    main()
