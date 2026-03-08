"""CLI entry point for sip_engine (python -m sip_engine)."""

import argparse
import sys
import traceback
from pathlib import Path

from sip_engine.compat import ensure_utf8_console


def main() -> None:
    """SIP -- Sistema Inteligente de Prediccion CLI."""
    ensure_utf8_console()

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
    build_features_parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Skip interactive config screen, use defaults/CLI args directly",
    )
    build_features_parser.add_argument(
        "--n-jobs",
        type=int,
        default=-1,
        help="CPU cores to use (default: -1 = auto-detect physical cores)",
    )
    build_features_parser.add_argument(
        "--device",
        choices=["cpu", "cuda", "rocm"],
        default=None,
        help="Device (default: auto-detect)",
    )
    build_features_parser.add_argument(
        "--disable-rocm",
        action="store_true",
        help="Skip ROCm GPU even if detected",
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
        nargs="+",
        choices=["M1", "M2", "M3", "M4"],
        metavar="MODEL",
        help="Model(s) to train (e.g., --model M1 M3). Default: interactive picker or all 4.",
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
    train_parser.add_argument(
        "--device",
        choices=["cpu", "cuda", "rocm"],
        default=None,
        help="Force training device (default: auto-detect best available)",
    )
    train_parser.add_argument(
        "--disable-rocm",
        action="store_true",
        help="Skip ROCm GPU even if detected (use when ROCm is unstable)",
    )
    train_parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Skip interactive config screen, use defaults/CLI args directly",
    )
    train_parser.add_argument(
        "--no-stats",
        action="store_true",
        dest="no_stats",
        help="Disable live test-set metrics in the training display (metrics are shown by default)",
    )

    run_parser = subparsers.add_parser("run-pipeline", help="Run the full SIP pipeline end to end")
    run_parser.add_argument(
        "--model",
        nargs="+",
        choices=["M1", "M2", "M3", "M4"],
        metavar="MODEL",
        help="Model(s) to train and evaluate (e.g., --model M1 M3). Default: interactive picker or all 4.",
    )
    run_parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: reduced HP search (20 iters, 3-fold CV)",
    )
    run_parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild all stages from scratch even if artifacts exist",
    )
    run_parser.add_argument(
        "--n-iter",
        type=int,
        default=200,
        help="HP search iterations per model (default: 200)",
    )
    run_parser.add_argument(
        "--n-jobs",
        type=int,
        default=-1,
        help="Parallelism level (default: -1 = all cores)",
    )
    run_parser.add_argument(
        "--device",
        choices=["cpu", "cuda", "rocm"],
        default=None,
        help="Force training device (default: auto-detect best available)",
    )
    run_parser.add_argument(
        "--disable-rocm",
        action="store_true",
        help="Skip ROCm GPU even if detected (use when ROCm is unstable)",
    )
    run_parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Skip interactive config screen, use defaults/CLI args directly",
    )
    run_parser.add_argument(
        "--no-stats",
        action="store_true",
        dest="no_stats",
        help="Disable live test-set metrics in the training display (metrics are shown by default)",
    )
    run_parser.add_argument(
        "--start-from",
        choices=["rcac", "labels", "features", "iric", "train", "evaluate"],
        default=None,
        help="Resume pipeline from this step (e.g. --start-from train)",
    )

    evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate trained models")
    evaluate_parser.add_argument(
        "--model",
        nargs="+",
        choices=["M1", "M2", "M3", "M4"],
        metavar="MODEL",
        help="Model(s) to evaluate (e.g., --model M1 M3). Default: all 4.",
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
    evaluate_parser.add_argument(
        "--artifact",
        type=str,
        default=None,
        help="Load a specific model artifact (e.g., model_run001_auc_roc.pkl) instead of model.pkl",
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
            "rues",
        ],
        metavar="NAME",
        help="Download specific dataset(s) only (default: all 9)",
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
        from sip_engine.pipeline import PipelineConfig, run_rcac
        try:
            cfg = PipelineConfig(n_jobs=1, n_iter=0, cv_folds=0, max_ram_gb=0, device="cpu", force=args.force)
            path = run_rcac(cfg)
            print(f"RCAC built: {path}")
            sys.exit(0)
        except Exception as e:
            print(f"Error building RCAC: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "build-labels":
        from sip_engine.pipeline import PipelineConfig, run_labels
        try:
            cfg = PipelineConfig(n_jobs=1, n_iter=0, cv_folds=0, max_ram_gb=0, device="cpu", force=args.force)
            path = run_labels(cfg)
            print(f"Labels built: {path}")
            sys.exit(0)
        except Exception as e:
            print(f"Error building labels: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "build-features":
        from sip_engine.classifiers.features.pipeline import build_features
        from sip_engine.shared.hardware import detect_hardware
        try:
            interactive = not args.no_interactive
            n_jobs = args.n_jobs
            device = args.device
            if not interactive:
                # Non-interactive: resolve n_jobs from hardware if -1
                if n_jobs == -1:
                    hw = detect_hardware(disable_rocm=getattr(args, "disable_rocm", False))
                    n_jobs = hw.cpu_cores_physical
                if device is None:
                    hw = detect_hardware(disable_rocm=getattr(args, "disable_rocm", False))
                    device = hw.gpu_type if hw.gpu_available else "cpu"
            path = build_features(
                force=args.force,
                n_jobs=n_jobs if n_jobs > 0 else 1,
                device=device or "cpu",
                interactive=interactive,
                show_progress=True,
            )
            print(f"Features built: {path}")
            sys.exit(0)
        except KeyboardInterrupt:
            print("\nCancelled.")
            sys.exit(1)
        except Exception as e:
            print(f"Error building features: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "build-iric":
        from sip_engine.pipeline import PipelineConfig, run_iric
        try:
            cfg = PipelineConfig(n_jobs=1, n_iter=0, cv_folds=0, max_ram_gb=0, device="cpu", force=args.force)
            path = run_iric(cfg)
            print(f"IRIC scores built: {path}")
            sys.exit(0)
        except Exception as e:
            print(f"Error building IRIC scores: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "train":
        from sip_engine.classifiers.models.trainer import train_model, MODEL_IDS
        if args.model:
            models_to_train = args.model  # already a list from nargs='+'
        elif not args.no_interactive:
            from sip_engine.classifiers.ui.config_screen import show_model_picker
            models_to_train = show_model_picker()
        else:
            models_to_train = MODEL_IDS
        try:
            if args.build_features:
                from sip_engine.shared.data.rcac_builder import build_rcac
                from sip_engine.shared.data.label_builder import build_labels
                from sip_engine.classifiers.features.pipeline import build_features
                from sip_engine.classifiers.iric.pipeline import build_iric
                print("Building RCAC...")
                build_rcac(force=args.force)
                print("Building labels...")
                build_labels(force=args.force)
                print("Building features...")
                build_features(force=args.force, show_progress=True)
                print("Building IRIC scores...")
                build_iric(force=args.force)
            for i, mid in enumerate(models_to_train):
                model_dir = train_model(
                    model_id=mid,
                    force=args.force,
                    quick=args.quick,
                    n_iter=args.n_iter,
                    n_jobs=args.n_jobs,
                    device=args.device,
                    disable_rocm=args.disable_rocm,
                    interactive=(not args.no_interactive and i == 0),
                    show_stats=not args.no_stats,
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
        from sip_engine.classifiers.evaluation.evaluator import evaluate_all, evaluate_model, MODEL_IDS

        if getattr(args, 'artifact', None) and not args.model:
            print("Error: --artifact requires --model (specify which model)", file=sys.stderr)
            sys.exit(1)

        models_to_eval = args.model if args.model else MODEL_IDS
        try:
            if len(models_to_eval) == 1:
                report_path = evaluate_model(
                    model_id=models_to_eval[0],
                    models_dir=args.models_dir,
                    output_dir=args.output_dir,
                    artifact=getattr(args, 'artifact', None),
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
        from sip_engine.classifiers.evaluation.comparison import backup_v1_artifacts
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
        from sip_engine.shared.data.downloader import (
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

    elif args.command == "run-pipeline":
        from sip_engine.pipeline import PipelineConfig, run_pipeline
        from sip_engine.shared.hardware import detect_hardware
        from rich.console import Console as _Console
        from rich.panel import Panel as _Panel

        _con = _Console()

        try:
            # ------------------------------------------------------------------
            # Single upfront hardware config — shared by features AND trainer
            # ------------------------------------------------------------------
            hw = detect_hardware(disable_rocm=args.disable_rocm)
            pipeline_cfg: dict = {
                "n_jobs": args.n_jobs if args.n_jobs > 0 else hw.cpu_cores_physical,
                "n_iter": args.n_iter,
                "cv_folds": 5,
                "max_ram_gb": max(1, int(hw.ram_available_gb)),
                "device": args.device if args.device else (hw.gpu_type if hw.gpu_available else "cpu"),
            }

            if not args.no_interactive:
                from sip_engine.classifiers.ui.config_screen import show_pipeline_config_screen
                pipeline_cfg = show_pipeline_config_screen(
                    hw,
                    defaults={
                        "n_jobs": pipeline_cfg["n_jobs"],
                        "n_iter": pipeline_cfg["n_iter"],
                        "cv_folds": pipeline_cfg["cv_folds"],
                        "max_ram_gb": pipeline_cfg["max_ram_gb"],
                        "device": pipeline_cfg["device"],
                    },
                    header="Builds RCAC → labels → features → IRIC → trains models → evaluates",
                )
            else:
                _con.print()
                _con.print(
                    _Panel(
                        "  Builds RCAC → labels → features → IRIC → trains models → evaluates",
                        title="[bold cyan]SIP Pipeline — Full Run",
                        border_style="cyan",
                    )
                )

            # Model selection
            if args.model:
                selected_models = args.model  # list from nargs='+'
            elif not args.no_interactive:
                from sip_engine.classifiers.ui.config_screen import show_model_picker
                selected_models = show_model_picker()
            else:
                selected_models = None  # None = all models (PipelineConfig default)

            cfg = PipelineConfig(
                n_jobs=pipeline_cfg["n_jobs"],
                n_iter=pipeline_cfg["n_iter"],
                cv_folds=pipeline_cfg["cv_folds"],
                max_ram_gb=pipeline_cfg["max_ram_gb"],
                device=pipeline_cfg["device"],
                force=args.force,
                model=selected_models,
                quick=args.quick,
                disable_rocm=args.disable_rocm,
                show_stats=not args.no_stats,
            )
            run_pipeline(cfg, start_from=args.start_from)
            sys.exit(0)
        except KeyboardInterrupt:
            _con.print("\n[yellow]Pipeline cancelled.[/yellow]")
            sys.exit(1)
        except Exception as e:
            traceback.print_exc()
            print(f"Pipeline error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "compare-v1v2":
        from sip_engine.classifiers.evaluation.comparison import generate_comparison_report
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
