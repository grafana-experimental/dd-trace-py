import pytest


@pytest.mark.subprocess(
    env=dict(
        DD_PROFILING_OUTPUT_PPROF="/tmp/test_copy_memory_error_count",
        DD_PROFILING_UPLOAD_INTERVAL="1",
    ),
    err=None,
)
def test_copy_memory_error_count_present() -> None:
    """copy_memory_error_count is always emitted (even when 0) and is non-negative."""
    import json
    import os
    import time

    from ddtrace.profiling import profiler
    from ddtrace.trace import tracer
    from tests.profiling.collector import pprof_utils

    p = profiler.Profiler(tracer=tracer)
    p.start()
    time.sleep(3)
    p.stop()

    output_filename = os.environ["DD_PROFILING_OUTPUT_PPROF"] + "." + str(os.getpid())
    files = pprof_utils.get_internal_metadata_files(output_filename)
    assert files, "Expected at least one internal_metadata.json file"

    for f in files:
        with open(f) as fp:
            metadata = json.load(fp)
        assert "copy_memory_error_count" in metadata, f"Missing copy_memory_error_count in {f}: {metadata}"
        assert metadata["copy_memory_error_count"] >= 0, f"copy_memory_error_count must be non-negative: {metadata}"
        assert "fast_copy_memory_user_disabled" in metadata, (
            f"Missing fast_copy_memory_user_disabled in {f}: {metadata}"
        )
        assert "fast_copy_memory_capable" in metadata, f"Missing fast_copy_memory_capable in {f}: {metadata}"
        assert "fast_copy_memory_syscall_fallback" in metadata, (
            f"Missing fast_copy_memory_syscall_fallback in {f}: {metadata}"
        )


@pytest.mark.subprocess(
    env=dict(
        DD_PROFILING_OUTPUT_PPROF="/tmp/test_fast_copy_memory_disabled",
        DD_PROFILING_UPLOAD_INTERVAL="1",
        _DD_PROFILING_STACK_FAST_COPY="false",
    ),
    err=None,
)
def test_fast_copy_memory_disabled() -> None:
    """fast_copy_memory_enabled is False when _DD_PROFILING_STACK_FAST_COPY=false."""
    import json
    import os
    import time

    from ddtrace.profiling import profiler
    from ddtrace.trace import tracer
    from tests.profiling.collector import pprof_utils

    p = profiler.Profiler(tracer=tracer)
    p.start()
    time.sleep(3)
    p.stop()

    output_filename = os.environ["DD_PROFILING_OUTPUT_PPROF"] + "." + str(os.getpid())
    files = pprof_utils.get_internal_metadata_files(output_filename)
    assert files, "Expected at least one internal_metadata.json file"

    for i, f in enumerate(files):
        is_last_file = i == len(files) - 1
        with open(f) as fp:
            metadata = json.load(fp)

        if not is_last_file:
            assert "fast_copy_memory_enabled" in metadata, f"Missing fast_copy_memory_enabled in {f}: {metadata}"
            assert metadata["fast_copy_memory_enabled"] is False, (
                f"Expected fast_copy_memory_enabled=false when _DD_PROFILING_STACK_FAST_COPY=false: {metadata}"
            )
            assert metadata["fast_copy_memory_user_disabled"] is True, metadata
            assert metadata["fast_copy_memory_syscall_fallback"] is False, metadata


@pytest.mark.subprocess(
    env=dict(
        DD_PROFILING_OUTPUT_PPROF="/tmp/test_fast_copy_memory_enabled",
        DD_PROFILING_UPLOAD_INTERVAL="1",
        _DD_PROFILING_STACK_FAST_COPY="1",
    ),
    err=None,
)
def test_fast_copy_memory_enabled() -> None:
    """The sampler uses safe_memcpy as soon as it starts."""
    import json
    import os
    import time
    from typing import Any
    from typing import Optional

    from ddtrace.internal.datadog.profiling.stack import _stack
    from ddtrace.profiling import profiler
    from ddtrace.trace import tracer
    from tests.profiling.collector import pprof_utils

    p: profiler.Profiler = profiler.Profiler(tracer=tracer)
    p.start()

    assert _stack.fast_copy_memory_active() is True

    # Wait for a completed sampling cycle and an upload interval so the
    # metadata reflects the running sampler.
    time.sleep(2)
    p.stop()

    output_filename = os.environ["DD_PROFILING_OUTPUT_PPROF"] + "." + str(os.getpid())
    files = pprof_utils.get_internal_metadata_files(output_filename)
    assert files, "Expected at least one internal_metadata.json file"

    # A window with no completed sampling cycle inherits the previous window's fast-copy
    # state, so it says nothing about what the sampler is running on.
    metadata: Optional[dict[str, Any]] = None
    for f in reversed(files):
        with open(f) as fp:
            candidate = json.load(fp)

        if candidate["sampling_event_count"] > 0:
            metadata = candidate
            break

    assert metadata is not None, f"Expected an upload window with at least one sampling cycle: {files}"

    assert metadata["fast_copy_memory_user_disabled"] is False, metadata
    assert metadata["fast_copy_memory_capable"] is True, metadata
    assert metadata["fast_copy_memory_syscall_fallback"] is False, metadata
    assert metadata["fast_copy_memory_enabled"] is True, metadata
