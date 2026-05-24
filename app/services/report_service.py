from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from db.enums import AggregationType, TimeGranularity
from db.models.metric import Metric
from db.models.variant import Variant

from db.repositories.report_repo import ReportRepository, EventRow
from exceptions.app_exceptions import UnprocessableEntity, ExperimentNotFound

from schemas.report import (
    ReportRequest,
    ExperimentReport,
    ReportContext,
    VariantReport,
    MetricValue,
    VariantTimeseries,
    VariantMetricTimeseries,
    TimeseriesPoint,
)


@dataclass
class _AggResult:
    raw: float
    aux: Optional[dict[str, float]] = None


class ReportService:
    def __init__(self):
        self.repo = ReportRepository

    @staticmethod
    def _to_utc_naive(dt: datetime) -> datetime:
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    @staticmethod
    def _bucket_start(ts: datetime, gran: TimeGranularity) -> datetime:
        # ts is expected utc-naive
        if gran == TimeGranularity.MINUTE:
            return ts.replace(second=0, microsecond=0)
        if gran == TimeGranularity.HOUR:
            return ts.replace(minute=0, second=0, microsecond=0)
        if gran == TimeGranularity.DAY:
            return ts.replace(hour=0, minute=0, second=0, microsecond=0)
        return ts

    @staticmethod
    def _next_bucket(ts: datetime, gran: TimeGranularity) -> datetime:
        if gran == TimeGranularity.MINUTE:
            return ts + timedelta(minutes=1)
        if gran == TimeGranularity.HOUR:
            return ts + timedelta(hours=1)
        if gran == TimeGranularity.DAY:
            return ts + timedelta(days=1)
        return ts + timedelta(days=1)

    @staticmethod
    def _get_prop(props: dict, field_path: str) -> Any:
        # dot path: "perf.latency_ms"
        cur: Any = props
        for part in field_path.split("."):
            if isinstance(cur, dict):
                if part not in cur:
                    return None

                cur = cur[part]

            elif isinstance(cur, list):
                if not part.isdigit() or len(part) >= len(cur):
                    return None

                cur = cur[int(part)]

            else:
                return None

        return cur

    @staticmethod
    def _p95(values: list[float]) -> float:
        if not values:
            return 0.0
        s = sorted(values)
        k = int((0.95 * (len(s) - 1)))
        return float(s[k])

    def _aggregate_metric(
        self,
        metric: Metric,
        events: list[EventRow],
        *,
        exposure_decisions: Optional[set[UUID]] = None,
        exposure_event_name: str = "exposure",
    ) -> _AggResult:
        agg = metric.aggregation_type

        def _exposure_ok(ev: EventRow) -> bool:
            if not metric.requires_exposure:
                return True

            if ev.event_name == exposure_event_name:
                return True

            if exposure_decisions is None:
                return True

            return ev.decision_id in exposure_decisions

        if agg in (AggregationType.COUNT, AggregationType.UNIQUE_COUNT):
            if not metric.numerator_event:
                return _AggResult(raw=0.0)

            filtered = [e for e in events if e.event_name ==
                        metric.numerator_event and _exposure_ok(e)]

            if agg == AggregationType.COUNT:
                return _AggResult(raw=float(len(filtered)))

            subjects = {e.subject_id for e in filtered}
            return _AggResult(raw=float(len(subjects)))

        if agg == AggregationType.RATE:
            if not metric.numerator_event or not metric.denominator_event:
                return _AggResult(raw=0.0, aux={"numerator": 0.0, "denominator": 0.0})

            nums = [e for e in events if e.event_name == metric.numerator_event and _exposure_ok(e)]
            dens = [e for e in events if e.event_name ==
                    metric.denominator_event and _exposure_ok(e)]

            n = float(len(nums))
            d = float(len(dens))
            raw = (n / d) if d > 0 else 0.0
            return _AggResult(raw=float(raw), aux={"numerator": n, "denominator": d})

        if agg in (AggregationType.AVG, AggregationType.P95):
            if not metric.field_path:
                return _AggResult(raw=0.0)

            vals: list[float] = []
            for e in events:
                if not _exposure_ok(e):
                    continue
                v = self._get_prop(e.props or {}, metric.field_path)
                if isinstance(v, bool):
                    continue
                if isinstance(v, (int, float)):
                    vals.append(float(v))
                elif isinstance(v, str):
                    try:
                        vals.append(float(v))
                    except Exception:
                        pass

            if not vals:
                return _AggResult(raw=0.0)

            if agg == AggregationType.AVG:
                return _AggResult(raw=float(sum(vals) / len(vals)))

            return _AggResult(raw=float(self._p95(vals)))

        return _AggResult(raw=0.0)

    async def generate_experiment_report(
        self,
        session: AsyncSession,
        experiment_id: UUID,
        req: ReportRequest,
    ) -> ExperimentReport:
        from_ts = self._to_utc_naive(req.from_ts)
        to_ts = self._to_utc_naive(req.to_ts)

        exp = await self.repo.get_experiment_with_variants(session, experiment_id)
        if exp is None:
            raise ExperimentNotFound()

        # metrics selection
        if req.metric_keys is None:
            metrics = list(await self.repo.get_metrics_for_experiment(session, experiment_id))
        else:
            metrics = list(await self.repo.get_metrics_by_keys(session, list(req.metric_keys)))

        if not metrics:
            raise UnprocessableEntity("no metrics selected for report")

        need_all_events = any(
            m.aggregation_type in (AggregationType.AVG, AggregationType.P95)
            for m in metrics
        )

        event_names: set[str] = set()
        if not need_all_events:
            for m in metrics:
                if m.aggregation_type in (AggregationType.COUNT, AggregationType.UNIQUE_COUNT):
                    if m.numerator_event:
                        event_names.add(m.numerator_event)
                elif m.aggregation_type == AggregationType.RATE:
                    if m.numerator_event:
                        event_names.add(m.numerator_event)
                    if m.denominator_event:
                        event_names.add(m.denominator_event)

        exposure_needed = any(
            bool(m.requires_exposure)
            for m in metrics
        ) or ("exposure" in event_names)

        if exposure_needed:
            event_names.add("exposure")

        rows = await self.repo.fetch_events(
            session,
            experiment_id=experiment_id,
            from_ts=from_ts,
            to_ts=to_ts,
            event_names=None if need_all_events else event_names,
        )

        exposure_decisions: Optional[set[UUID]] = None
        if exposure_needed:
            exposure_decisions = await self.repo.fetch_exposures_decision_ids(
                session,
                experiment_id=experiment_id,
                from_ts=from_ts,
                to_ts=to_ts,
                exposure_event_name="exposure",
            )

        by_variant: dict[UUID, list[EventRow]] = {}
        for e in rows:
            by_variant.setdefault(e.variant_id, []).append(e)

        variants: list[Variant] = list(exp.variants or [])

        variants_out: list[VariantReport] = []
        for v in variants:
            v_events = by_variant.get(v.id, [])
            metrics_out: dict[str, MetricValue] = {}

            for m in metrics:
                res = self._aggregate_metric(
                    m,
                    v_events,
                    exposure_decisions=exposure_decisions,
                    exposure_event_name="exposure",
                )
                metrics_out[m.key] = MetricValue(raw=float(res.raw), aux=res.aux)

            variants_out.append(
                VariantReport(
                    variant_id=v.id,
                    variant_name=v.name,
                    is_control=bool(v.is_control),
                    metrics=metrics_out,
                )
            )

        timeseries_out: Optional[list[VariantTimeseries]] = []
        if req.include_timeseries:
            gran = req.granularity or TimeGranularity.DAY

            buckets: list[datetime] = []
            cur = self._bucket_start(from_ts, gran)
            end = to_ts
            while cur < end:
                buckets.append(cur)
                cur = self._next_bucket(cur, gran)

            # pre-bucket events by variant -> bucket -> list[EventRow]
            v_bucket_events: dict[UUID, dict[datetime, list[EventRow]]] = {}
            for e in rows:
                b = self._bucket_start(e.occurred_at, gran)
                v_bucket_events.setdefault(e.variant_id, {}).setdefault(b, []).append(e)

            for v in variants:
                series: list[VariantMetricTimeseries] = []
                for m in metrics:
                    points: list[TimeseriesPoint] = []
                    for b in buckets:
                        evs = v_bucket_events.get(v.id, {}).get(b, [])
                        r = self._aggregate_metric(
                            m,
                            evs,
                            exposure_decisions=exposure_decisions,
                            exposure_event_name="exposure",
                        )
                        points.append(TimeseriesPoint(ts=b, value=float(r.raw)))

                    series.append(
                        VariantMetricTimeseries(
                            metric_key=m.key,
                            points=points,
                        )
                    )

                timeseries_out.append(
                    VariantTimeseries(
                        variant_id=v.id,
                        variant_name=v.name,
                        series=series,
                    )
                )

        ctx = ReportContext(
            from_ts=from_ts,
            to_ts=to_ts,
            unit="event",
            include_timeseries=bool(req.include_timeseries),
            granularity=req.granularity.value if req.granularity is not None else None,
        )

        return ExperimentReport(
            experiment_id=exp.id,
            generated_at=datetime.utcnow(),
            context=ctx,
            variants=variants_out,
            timeseries=timeseries_out,
        )
