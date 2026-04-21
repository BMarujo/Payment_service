"""
OpenTelemetry setup — tracing, metrics, and auto-instrumentation.

Initialises the OTel SDK once at startup and instruments:
  • FastAPI (HTTP spans)
  • SQLAlchemy (DB spans)
  • Redis (cache spans)
  • httpx (outgoing HTTP spans — EGS Auth calls)
"""

import logging
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

# Module-level references so we can shut down cleanly
_tracer_provider = None
_meter_provider = None


def setup_telemetry(app) -> None:
    """Configure OpenTelemetry and attach auto-instrumentation to the app."""
    global _tracer_provider, _meter_provider

    settings = get_settings()

    if not settings.otel_enabled:
        logger.info("OpenTelemetry disabled (OTEL_ENABLED=false)")
        return

    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

        # ── Resource (identifies this service in all telemetry) ──
        resource = Resource.create({
            SERVICE_NAME: settings.otel_service_name,
            SERVICE_VERSION: settings.app_version,
            "deployment.environment": settings.environment,
        })

        # ── Tracing ──
        _tracer_provider = TracerProvider(resource=resource)
        span_exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
        _tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(_tracer_provider)

        # ── Metrics ──
        metric_exporter = OTLPMetricExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
        metric_reader = PeriodicExportingMetricReader(
            metric_exporter,
            export_interval_millis=settings.otel_metric_export_interval_ms,
        )
        _meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(_meter_provider)

        # ── Auto-instrumentation ──
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)

        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()

        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            from app.database import engine
            SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        except Exception as e:
            logger.warning(f"SQLAlchemy instrumentation skipped: {e}")

        try:
            from opentelemetry.instrumentation.redis import RedisInstrumentor
            RedisInstrumentor().instrument()
        except Exception as e:
            logger.warning(f"Redis instrumentation skipped: {e}")

        logger.info(
            "OpenTelemetry initialised — exporting to %s (metrics every %sms)",
            settings.otel_exporter_otlp_endpoint,
            settings.otel_metric_export_interval_ms,
        )

    except ImportError as e:
        logger.warning(f"OpenTelemetry packages not installed, skipping: {e}")
    except Exception as e:
        logger.error(f"Failed to initialise OpenTelemetry: {e}")


def shutdown_telemetry() -> None:
    """Flush and shut down OTel providers."""
    global _tracer_provider, _meter_provider
    if _tracer_provider:
        _tracer_provider.shutdown()
    if _meter_provider:
        _meter_provider.shutdown()
    logger.info("OpenTelemetry shut down")
