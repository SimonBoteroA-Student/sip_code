"""CLI entry point for sip_engine (python -m sip_engine)."""

import argparse
import sys


def main() -> None:
    """SIP -- Sistema Inteligente de Prediccion CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m sip_engine",
        description="SIP -- Sistema Inteligente de Prediccion",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    subparsers.add_parser("build-rcac", help="Build RCAC corruption antecedent corpus")
    subparsers.add_parser("train", help="Train XGBoost prediction models")
    subparsers.add_parser("evaluate", help="Evaluate trained models")
    subparsers.add_parser("run-pipeline", help="Run the full SIP pipeline end to end")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    print(f"{args.command} not yet implemented.")
    sys.exit(0)


if __name__ == "__main__":
    main()
