"""daily-guidance — §6.3's "ranking engine, 17 modules", and §7.1's pipeline.

    00:30 local-region panchang pre-job → 15-minute Beat tick → 90–30 minute
    lead window (hashed by user_id) → priority queues → facts → ranking →
    template composition → batched LLM polish → grounding → store → notify

Read in this order: `windows` (when), `ranking` (what), `templates` (words),
`polish` (the model), `service` (the sequence and the degradation ladder).
"""

from sitara_api.daily_guidance.idempotency import briefing_key, local_date_for
from sitara_api.daily_guidance.ranking import RankingContext, core_cards, rank
from sitara_api.daily_guidance.service import DailyGuidanceService, run_wave
from sitara_api.daily_guidance.types import (
    Brief,
    BriefStatus,
    BriefSubject,
    Density,
    Tier,
)
from sitara_api.daily_guidance.windows import select_wave, wave_member

__all__ = [
    "Brief",
    "BriefStatus",
    "BriefSubject",
    "DailyGuidanceService",
    "Density",
    "RankingContext",
    "Tier",
    "briefing_key",
    "core_cards",
    "local_date_for",
    "rank",
    "run_wave",
    "select_wave",
    "wave_member",
]
