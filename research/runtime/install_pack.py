from __future__ import annotations

import argparse

from research.runtime.pack_manager import PackManager, RemotePackSpec


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install a research pack from a local archive or remote URL.")
    parser.add_argument("source", help="Path to a .zip pack or an https URL")
    parser.add_argument("--sha256", default=None, help="Optional SHA256 for remote download verification")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manager = PackManager()
    if args.source.startswith("http://") or args.source.startswith("https://"):
        installed = manager.install_from_url(RemotePackSpec(url=args.source, sha256=args.sha256))
    else:
        installed = manager.install_from_archive(args.source)
    print(f"installed {installed.conference} {installed.year} {installed.version} -> {installed.install_dir}")


if __name__ == "__main__":
    main()
