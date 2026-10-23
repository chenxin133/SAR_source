"""Generate a reproducible dat fixture without starting the desktop application."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.echo_service import sha256_file, simulate_echo  # noqa: E402
from app.schemas.echoes import EchoSimulation  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Generate uint16 offset-binary SAR echo demo data")
    parser.add_argument("output", type=Path)
    parser.add_argument("--band", choices=["C", "X", "Ku", "Ka"], default="X")
    parser.add_argument("--na", type=int, default=256)
    parser.add_argument("--nr", type=int, default=512)
    parser.add_argument("--seed", type=int, default=20261023)
    parser.add_argument("--noise-std", type=float, default=300)
    parser.add_argument("--gate-start", type=int, default=1000)
    args = parser.parse_args()
    parameters = EchoSimulation(na=args.na, nr=args.nr, seed=args.seed, frequency_band=args.band,
                                noise_std=args.noise_std, gate_start=args.gate_start)
    if args.output.exists():
        parser.error(f"Output already exists: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    simulate_echo(args.output, **parameters.model_dump(exclude={"name", "remark"}))
    print(f"{args.output.resolve()} | {args.output.stat().st_size} bytes | SHA256 {sha256_file(args.output)}")


if __name__ == "__main__":
    main()
