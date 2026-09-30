"""OpenTelemetry tracing wired to Google Cloud — no third-party observability SDK.

Google ADK already emits OpenTelemetry GenAI spans for every agent run, model call and tool
call, and ships the Google Cloud exporters to send them. All that was missing is somebody calling
the bootstrap. `setup()` is that call, plus two things ADK can't do on its own:

  * instrument the raw `google.genai` calls that live outside ADK (pipeline.rewrite, the eval
    judges), via opentelemetry-instrumentation-google-genai, and
  * give the pipeline's own stages (fetch, curate, enrich, rewrite, compose, TTS, email) spans,
    so a run reads as one tree instead of four disconnected agent invocations.

There are two Google backends, chosen by TRACE_BACKEND:

  * `cloudtrace` (default) — the classic cloudtrace.googleapis.com BatchWriteSpans path, plus
    Cloud Monitoring for metrics. Spans are immediately queryable in Cloud Trace.
  * `telemetry` — ADK's own default, OTLP to telemetry.googleapis.com. This is the newer
    Cloud Observability ingest and needs the project to have a trace bucket provisioned; without
    one it returns HTTP 200 and the spans are silently unqueryable ("_Trace bucket not found in
    project" when you try to read them back). Use it once the project is onboarded.

Two rules this module lives by:

  * Tracing must never break the briefing. Every entry point here swallows its own failures and
    degrades to a no-op, the same way archive_to_gcs and the curator fallback do.
  * `flush()` before the process exits. The Cloud exporter batches spans in the background, and
    a Cloud Run Job (or a CLI run) exits long before the batch interval elapses — without an
    explicit flush the traces are simply never sent.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

log = logging.getLogger("daily-news.observability")

# Set once setup() has actually installed providers, so the span helpers know whether there is
# anything listening and repeat calls (several entry points construct Config) stay cheap.
_READY = False
_ATTEMPTED = False

_TRACER = None

# The env vars ADK reads for span content. google/adk/telemetry/context.py resolves every env
# fallback once, at TelemetryConfig construction, so these have to be set before the first
# agent run — not lazily, or half a run's telemetry silently disagrees with the other half.
_CONTENT_ENV = "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS"
_OTEL_CONTENT_ENV = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"


def setup(cfg: Any) -> bool:
    """Point ADK + google-genai telemetry at Google Cloud. Returns True if tracing is live.

    Must be called *after* Config(), which is what populates GOOGLE_CLOUD_PROJECT /
    GOOGLE_CLOUD_LOCATION / GOOGLE_GENAI_USE_VERTEXAI (config.py's os.environ.setdefault block).
    Safe to call more than once; only the first call installs anything.
    """
    global _READY, _ATTEMPTED, _TRACER

    if _ATTEMPTED:
        return _READY
    _ATTEMPTED = True

    if not getattr(cfg, "trace_enabled", False):
        log.info("Tracing disabled (TRACE_ENABLED=0).")
        return False
    if not getattr(cfg, "gcp_project", ""):
        log.warning("Tracing skipped: no GOOGLE_CLOUD_PROJECT to export to.")
        return False

    os.environ.setdefault("OTEL_SERVICE_NAME", cfg.trace_service_name)
    _set_content_capture(bool(cfg.trace_content))

    backend = getattr(cfg, "trace_backend", "cloudtrace")
    try:
        from google.adk.telemetry.google_cloud import get_gcp_resource
        from google.adk.telemetry.setup import maybe_set_otel_providers
        from opentelemetry import trace

        hooks = (
            _telemetry_hooks(cfg) if backend == "telemetry" else _cloud_trace_hooks(cfg)
        )
        # get_gcp_resource is not optional: the OTLP backend rejects a payload without
        # gcp.project_id with a bare 400, and it is what stamps the resource either way.
        maybe_set_otel_providers([hooks], otel_resource=get_gcp_resource(cfg.gcp_project))
        _TRACER = trace.get_tracer("daily-news")
    except Exception as exc:  # noqa: BLE001
        log.warning("Tracing setup failed (continuing untraced): %s", exc)
        return False

    _instrument_genai()
    _READY = True
    log.info(
        "Tracing -> %s (project %s, service %s, content=%s)",
        "telemetry.googleapis.com" if backend == "telemetry" else "Cloud Trace",
        cfg.gcp_project,
        os.environ.get("OTEL_SERVICE_NAME"),
        "on" if cfg.trace_content else "off",
    )
    return True


def _cloud_trace_hooks(cfg: Any) -> Any:
    """Classic Cloud Trace + Cloud Monitoring exporters (the default)."""
    from google.adk.telemetry.setup import OTelHooks
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    hooks = OTelHooks(
        span_processors=[
            BatchSpanProcessor(CloudTraceSpanExporter(project_id=cfg.gcp_project))
        ]
    )
    if cfg.trace_metrics:
        try:
            from opentelemetry.exporter.cloud_monitoring import CloudMonitoringMetricsExporter
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

            hooks.metric_readers.append(
                PeriodicExportingMetricReader(
                    CloudMonitoringMetricsExporter(project_id=cfg.gcp_project),
                    export_interval_millis=60_000,
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Cloud Monitoring metrics unavailable (%s); traces only.", exc)
    return hooks


def _telemetry_hooks(cfg: Any) -> Any:
    """ADK's own OTLP exporters, aimed at telemetry.googleapis.com."""
    from google.adk.telemetry.google_cloud import get_gcp_exporters

    return get_gcp_exporters(
        enable_cloud_tracing=True,
        enable_cloud_metrics=bool(cfg.trace_metrics),
        enable_cloud_logging=bool(cfg.trace_logs),
    )


def _set_content_capture(enabled: bool) -> None:
    """Decide up front whether prompts/responses ride along on spans."""
    os.environ[_CONTENT_ENV] = "true" if enabled else "false"
    # The OTel-spec knob is four-state; SPAN_AND_EVENT is the only value that puts content where
    # Trace Explorer will show it. Empty string is the documented "no content" value.
    os.environ[_OTEL_CONTENT_ENV] = "SPAN_AND_EVENT" if enabled else ""


def _instrument_genai() -> None:
    """Wrap google.genai so the non-ADK model calls get spans too.

    pipeline.rewrite (gemini-2.5-pro) is the single biggest token spend in a run and does not go
    through ADK, so without this the most expensive call in the pipeline is invisible.
    """
    try:
        from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor

        instrumentor = GoogleGenAiSdkInstrumentor()
        if not instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.instrument()
    except Exception as exc:  # noqa: BLE001
        log.warning("google-genai instrumentation unavailable (%s); ADK spans only.", exc)


# --------------------------------------------------------------------------- #
# Span helpers. Each is a no-op when tracing never came up, so call sites stay
# free of `if tracing:` noise.
# --------------------------------------------------------------------------- #
@contextmanager
def span(span_name: str, /, **attrs: Any) -> Iterator[Any]:
    """Run a block inside a span, recording any exception on it before re-raising.

    The span name is positional-only so that every keyword is free to be an attribute — `name`
    and `source` are attributes call sites genuinely want to set.
    """
    if not _READY or _TRACER is None:
        yield None
        return
    with _TRACER.start_as_current_span(span_name) as sp:
        _apply(sp, attrs)
        try:
            yield sp
        except Exception as exc:  # noqa: BLE001
            _record_exception(sp, exc)
            raise


def set_attrs(**attrs: Any) -> None:
    """Add attributes to whatever span is currently active."""
    if not _READY:
        return
    from opentelemetry import trace

    _apply(trace.get_current_span(), attrs)


def record_exception(exc: BaseException, **attrs: Any) -> None:
    """Attach a handled exception to the current span without failing the run.

    For the paths that deliberately swallow errors — a dead source, the curator falling back to
    deterministic — so a degraded run is queryable instead of just a log line.
    """
    if not _READY:
        return
    from opentelemetry import trace

    sp = trace.get_current_span()
    _apply(sp, attrs)
    _record_exception(sp, exc, set_error_status=False)


def record_tokens(usage: Any) -> None:
    """Put a google-genai usage_metadata on the current span, in GenAI semconv names.

    Token counts are otherwise discarded at every call site, which is why there has never been
    cost data for a run.
    """
    if not _READY or usage is None:
        return
    set_attrs(
        **{
            "gen_ai.usage.input_tokens": getattr(usage, "prompt_token_count", None),
            "gen_ai.usage.output_tokens": getattr(usage, "candidates_token_count", None),
            "gen_ai.usage.total_tokens": getattr(usage, "total_token_count", None),
            "gen_ai.usage.thoughts_tokens": getattr(usage, "thoughts_token_count", None),
        }
    )


def flush(timeout_millis: int = 30_000) -> None:
    """Drain batched spans/metrics. Required before exit or the export never happens."""
    if not _READY:
        return
    from opentelemetry import metrics, trace

    for provider in (trace.get_tracer_provider(), metrics.get_meter_provider()):
        force_flush = getattr(provider, "force_flush", None)
        if force_flush is None:
            continue
        try:
            force_flush(timeout_millis)
        except Exception as exc:  # noqa: BLE001
            log.warning("Telemetry flush failed: %s", exc)


def _apply(sp: Any, attrs: dict[str, Any]) -> None:
    """Set attributes, skipping Nones (OTel rejects them) and normalizing dotted keys."""
    if sp is None or not attrs:
        return
    try:
        for key, value in attrs.items():
            if value is None:
                continue
            sp.set_attribute(key.replace("__", "."), value)
    except Exception as exc:  # noqa: BLE001
        log.debug("Could not set span attributes: %s", exc)


def _record_exception(sp: Any, exc: BaseException, set_error_status: bool = True) -> None:
    try:
        from opentelemetry.trace import Status, StatusCode

        sp.record_exception(exc)
        if set_error_status:
            sp.set_status(Status(StatusCode.ERROR, str(exc)))
    except Exception as inner:  # noqa: BLE001
        log.debug("Could not record exception on span: %s", inner)
