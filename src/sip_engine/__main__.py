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

    build_iric_parser = subparsers.add_parser(
        "build-iric", help="Build IRIC irregularity risk index scores"
    )
    build_iric_parser.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild even if iric_scores.parquet exists",
    )

    train_parser = subparsers.add_parser("train", help="Train XGBoost prediction models")
    train_parser.add_argument(
        "--model",
        choices=["M1", "M2", "M3", "M4"],
        help="Train a single model (default: all 4)",
    )
    train_parser.add_argument(
        "--force",
        action="store_true",
        help="Retrain even if model artifacts already exist",
    )
    train_parser.add_argument(
        "--quick",
        action="store_true",
        help="Fast mode: ~20 iterations, 3-fold CV",
    )
    train_parser.add_argument(
        "--n-iter",
        type=int,
        default=200,
        help="Number of HP search iterations (default: 200)",
    )
    train_parser.add_argument(
        "--n-jobs",
        type=int,
        default=-1,
        help="Parallelism level (default: -1 = all cores)",
    )

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

    elif args.command == "build-iric":
        from sip_engine.iric.pipeline import build_iric
        try:
            path = build_iric(force=args.force)
            print(f"IRIC scores built: {path}")
            sys.exit(0)
        except Exception as e:
            print(f"Error building IRIC scores: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "train":
        from sip_engine.models.trainer import train_model, MODEL_IDS
        models_to_train = [args.model] if args.model else MODEL_IDS
        try:
            for mid in models_to_train:
                model_dir = train_model(
                    model_id=mid,
                    force=args.force,
                    quick=args.quick,
                    n_iter=args.n_iter,
                    n_jobs=args.n_jobs,
                )
                print(f"Model {mid} trained: {model_dir}")
            sys.exit(0)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error training models: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        print(f"{args.command} not yet implemented.")
        sys.exit(0)


if __name__ == "__main__":
    main()
