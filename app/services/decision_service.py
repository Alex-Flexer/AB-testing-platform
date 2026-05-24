from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from db.models.decision import Decision
from db.models.variant import Variant

from db.repositories.decision_repo import DecisionRepository
from db.repositories.feature_flags_repo import FeatureFlagRepository
from db.repositories.experiments_repo import ExperimentRepository

from exceptions import AppException, FeatureFlagNotFound

from schemas.decision import DecideRequest, DecideResponse, FlagDecision, DecisionMeta


class DecisionService:
    def __init__(self) -> None:
        self.repo = DecisionRepository

    @staticmethod
    def _sha_to_bucket_0_100(value: str) -> float:
        h = hashlib.sha256(value.encode("utf-8")).digest()
        n = int.from_bytes(h[:8], "big", signed=False)
        u = n / float(1 << 64)

        return u * 100.0

    @staticmethod
    def _default_decision_id(flag_key: str, subject_id: str) -> UUID:
        ns = uuid.UUID("00000000-0000-0000-0000-000000000001")
        return uuid.uuid5(ns, f"default:{flag_key}:{subject_id}")

    @staticmethod
    def _passes_targeting(targeting_rule: str | None, attributes: dict | None) -> bool:
        # Заглушка
        return True

    @staticmethod
    def _pick_variant_by_bucket(
        bucket: float,
        variants: list[Variant],
    ) -> Variant:
        acc = 0.0
        for v in variants:
            acc += float(v.weight)
            if bucket < acc:
                return v

        return variants[-1]

    async def decide(self, session: AsyncSession, req: DecideRequest) -> DecideResponse:
        if req.attributes is None:
            attributes = {}
        else:
            attributes = dict(req.attributes)

        decisions_out: list[FlagDecision] = []

        for flag_key in req.flags:
            flag = await FeatureFlagRepository.get_by_key(session, flag_key)

            if flag is None:
                raise FeatureFlagNotFound()

            exp = await FeatureFlagRepository.get_active_experiment(session, flag.id)

            if exp is None:
                print("no exp")
                decisions_out.append(
                    FlagDecision(
                        flag_key=flag_key,
                        value=str(flag.default_value),
                        meta=DecisionMeta(
                            decision_id=self._default_decision_id(flag_key, req.subject_id),
                            experiment_id=None,
                            variant_id=None,
                            variant_name=None,
                            is_default=True,
                        ),
                    )
                )
                continue

            # targeting
            if not self._passes_targeting(exp.targeting_rule, attributes):
                print("targeting")
                decisions_out.append(
                    FlagDecision(
                        flag_key=flag_key,
                        value=str(flag.default_value),
                        meta=DecisionMeta(
                            decision_id=self._default_decision_id(flag_key, req.subject_id),
                            experiment_id=None,
                            variant_id=None,
                            variant_name=None,
                            is_default=True,
                        ),
                    )
                )
                continue

            existing = await self.repo.get_by_experiment_subject(session, exp.id, req.subject_id)

            if existing is not None:
                print("no existing")
                variant = await session.get(Variant, existing.variant_id)

                decisions_out.append(
                    FlagDecision(
                        flag_key=flag_key,
                        value=str(variant.value) if variant else str(flag.default_value),
                        meta=DecisionMeta(
                            decision_id=existing.id,
                            experiment_id=existing.experiment_id,
                            variant_id=existing.variant_id,
                            variant_name=variant.name if variant else None,
                            is_default=False,
                        ),
                    )
                )
                continue

            traffic = float(exp.traffic_percentage)
            if traffic <= 0 or traffic > 100:
                raise AppException("invalid experiment traffic_percentage")

            bucket = self._sha_to_bucket_0_100(f"{exp.id}:{req.subject_id}:{exp.current_version}")

            if bucket >= traffic:
                print("not in traffic")
                decisions_out.append(
                    FlagDecision(
                        flag_key=flag_key,
                        value=str(flag.default_value),
                        meta=DecisionMeta(
                            decision_id=self._default_decision_id(flag_key, req.subject_id),
                            experiment_id=None,
                            variant_id=None,
                            variant_name=None,
                            is_default=True,
                        ),
                    )
                )
                continue

            variants = await ExperimentRepository.get_variants(session, exp.id)
            if not variants:
                raise AppException("experiment has no variants")

            chosen = self._pick_variant_by_bucket(bucket, variants)

            decision = Decision(
                experiment_id=exp.id,
                variant_id=chosen.id,
                subject_id=req.subject_id,
                assigned_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            await self.repo.create(session, decision)
            await session.commit()

            decisions_out.append(
                FlagDecision(
                    flag_key=flag_key,
                    value=str(chosen.value),
                    meta=DecisionMeta(
                        decision_id=decision.id,
                        experiment_id=exp.id,
                        variant_id=chosen.id,
                        variant_name=chosen.name,
                        is_default=False,
                    ),
                )
            )

        return DecideResponse(
            subject_id=req.subject_id,
            decisions=decisions_out,
            decided_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
