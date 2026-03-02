"""CLI entry point for sip_engine (python -m sip_engine)."""

import argparse
import sys
import traceback
from pathlib import Path


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
    train_parser.add_argument(
        "--build-features",
        action="store_true",
        help="Run full feature pipeline (rcac → labels → features → iric) before training",
    )

    subparsers.add_parser("run-pipeline", help="Run the full SIP pipeline end to end")

    evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate trained models")
    evaluate_parser.add_argument(
        "--model",
        choices=["M1", "M2", "M3", "M4"],
        help="Evaluate a single model (default: all 4)",
    )
    evaluate_parser.add_argument(
        "--models-dir",
        type=Path,
        help="Override model artifacts directory (default: artifacts/models)",
    )
    evaluate_parser.add_argument(
        "--output-dir",
        type=Path,
        help="Override evaluation output directory (default: artifacts/evaluation)",
    )

    subparsers.add_parser("backup-v1", help="Backup current artifacts to v1_baseline/")

    # ---- download-data ----
    dl_parser = subparsers.add_parser(
        "download-data",
        help="Download SECOP databases from datos.gov.co",
    )
    dl_parser.add_argument(
        "--dataset",
        nargs="+",
        choices=[
            "contratos", "procesos", "ofertas", "proponentes",
            "proveedores", "ejecucion", "adiciones", "suspensiones",
        ],
        metavar="NAME",
        help="Download specific dataset(s) only (default: all 8)",
    )
    dl_parser.add_argument(
        "--output-dir",
        type=Path,
        help="Override output directory (default: secopDatabases/)",
    )
    dl_parser.add_argument(
        "--parallel",
        type=int,
        default=4,
        help="Max concurrent downloads (default: 4)",
    )
    dl_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show download URLs without actually downloading",
    )
    dl_parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip datasets whose target CSV already exists",
    )
    dl_parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume interrupted downloads from .part files",
    )
    dl_parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate existing CSVs against expected schemas (no download)",
    )

    compare_parser = subparsers.add_parser("compare-v1v2", help="Generate v1 vs v2 comparison report")
    compare_parser.add_argument(
        "--v1-dir",
        type=Path,
        help="Override v1 baseline directory (default: artifacts/v1_baseline)",
    )
    compare_parser.add_argument(
        "--v2-dir",
        type=Path,
        help="Override v2 artifacts directory (default: artifacts/)",
    )

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
            if args.build_features:
                from sip_engine.data.rcac_builder import build_rcac
                from sip_engine.data.label_builder import build_labels
                from sip_engine.features.pipeline import build_features
                from sip_engine.iric.pipeline import build_iric
                print("Building RCAC...")
                build_rcac(force=args.force)
                print("Building labels...")
                build_labels(force=args.force)
                print("Building features...")
                build_features(force=args.force)
                print("Building IRIC scores...")
                build_iric(force=args.force)
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
            traceback.print_exc()
            print(f"Error training models: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "evaluate":
        from sip_engine.evaluation.evaluator import evaluate_all, evaluate_model, MODEL_IDS

        models_to_eval = [args.model] if args.model else MODEL_IDS
        try:
            if len(models_to_eval) == 1:
                report_path = evaluate_model(
                    model_id=models_to_eval[0],
                    models_dir=args.models_dir,
                    output_dir=args.output_dir,
                )
                print(f"Evaluation complete: {report_path}")
            else:
                summary_path = evaluate_all(
                    models_dir=args.models_dir,
                    output_dir=args.output_dir,
                )
                print(f"Evaluation complete: {summary_path}")
            sys.exit(0)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error during evaluation: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "backup-v1":
        from sip_engine.evaluation.comparison import backup_v1_artifacts
        try:
            path = backup_v1_artifacts()
            print(f"V1 baseline backed up: {path}")
            sys.exit(0)
        except FileExistsError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error backing up v1: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "download-data":
        from sip_engine.data.downloader import (
            DATASET_BY_KEY,
            download_datasets,
            validate_downloads,
        )
        try:
            if args.validate_only:
                validate_downloads(output_dir=args.output_dir)
                sys.exit(0)

            selected = None
            if args.dataset:
                selected = [DATASET_BY_KEY[k] for k in args.dataset]

            paths = download_datasets(
                datasets=selected,
                output_dir=args.output_dir,
                parallel=args.parallel,
                dry_run=args.dry_run,
                skip_existing=args.skip_existing,
                resume=args.resume,
            )

            if paths and not args.dry_run:
                validate_downloads(output_dir=args.output_dir)

            sys.exit(0)
        except KeyboardInterrupt:
            print("\n  Download interrupted.")
            sys.exit(1)
        except Exception as e:
            print(f"Error downloading data: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "compare-v1v2":
        from sip_engine.evaluation.comparison import generate_comparison_report
        try:
            md_path, json_path = generate_comparison_report(
                v1_dir=getattr(args, 'v1_dir', None),
                v2_dir=getattr(args, 'v2_dir', None),
            )
            print(f"Comparison report generated:\n  {md_path}\n  {json_path}")
            sys.exit(0)
        except Exception as e:
            print(f"Error generating comparison: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        print(f"{args.command} not yet implemented.")
        sys.exit(0)


if __name__ == "__main__":
    main()
