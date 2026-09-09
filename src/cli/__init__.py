"""
src/cli package.
Provides headless CLI pipeline and argument parsing for Live2D model generation.
"""

from src.cli.main import (
    main,
    run_pipeline,
    parse_args,
    build_parser,
    PipelineConfig,
    PipelineRunner,
    EXIT_SUCCESS,
    EXIT_ERR_INPUT,
    EXIT_ERR_INVALID_ARGS,
    EXIT_ERR_INPUT_NOT_FOUND,
    EXIT_ERR_MESH,
    EXIT_ERR_DEFORMATION,
    EXIT_ERR_PROCESSING_FAILED,
    EXIT_ERR_EXPORT,
    EXIT_ERR_EXPORT_FAILED,
    EXIT_ERR_VALIDATION,
    EXIT_ERR_VALIDATION_FAILED,
)

__all__ = [
    "main",
    "run_pipeline",
    "parse_args",
    "build_parser",
    "PipelineConfig",
    "PipelineRunner",
    "EXIT_SUCCESS",
    "EXIT_ERR_INPUT",
    "EXIT_ERR_INVALID_ARGS",
    "EXIT_ERR_INPUT_NOT_FOUND",
    "EXIT_ERR_MESH",
    "EXIT_ERR_DEFORMATION",
    "EXIT_ERR_PROCESSING_FAILED",
    "EXIT_ERR_EXPORT",
    "EXIT_ERR_EXPORT_FAILED",
    "EXIT_ERR_VALIDATION",
    "EXIT_ERR_VALIDATION_FAILED",
]
