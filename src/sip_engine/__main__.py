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

    build_rcac_parser = subparsers.add_parser(
        "build-rcac", help="Build RCAC corruption antecedent corpus"
    )
    build_rcac_parser.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild even if rcac.pkl exists",
    )

    build_labels_parser = subparsers.add_parser(
        "build-labels", help="Build M1/M2/M3/M4 target labels and save to parquet"
    )
    build_labels_parser.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild even if labels.parquet exists",
    )

    build_features_parser = subparsers.add_parser(
        "build-features", help="Build feature matrix from contratos/procesos/proveedores"
    )
    build_features_parser.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild even if features.parquet exists",
    )

    subparsers.add_parser("train", help="Train XGBoost prediction models")
    subparsers.add_parser("evaluate", help="Evaluate trained models")
    subparsers.add_parser("run-pipeline", help="Run the full SIP pipeline end to end")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "build-rcac":
        from sip_engine.data.rcac_builder import build_rcac
        try:
            path = build_rcac(force=args.force)
            print(f"RCAC built: {path}")
            sys.exit(0)
        except Exception as e:
            print(f"Error building RCAC: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "build-labels":
        from sip_engine.data.label_builder import build_labels
        try:
            path = build_labels(force=args.force)
            print(f"Labels built: {path}")
            sys.exit(0)
        except Exception as e:
            print(f"Error building labels: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "build-features":
        from sip_engine.features.pipeline import build_features
        try:
            path = build_features(force=args.force)
            print(f"Features built: {path}")
            sys.exit(0)
        except Exception as e:
            print(f"Error building features: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        print(f"{args.command} not yet implemented.")
        sys.exit(0)


if __name__ == "__main__":
    main()
