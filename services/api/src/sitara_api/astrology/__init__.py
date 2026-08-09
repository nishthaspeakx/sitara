"""astrology — §6.3's "facade over sitara-astro + PanchangProvider".

§13's single door to birth details: "reachable only via the astrology facade
(no generic query path)". Everything that wants a chart fact comes through
`AstrologyFacade`; the adapters underneath speak HTTP to the internal engine
and nothing else.

    AstroChartAdapter   transport + §8 breaker over /v1/facts/{natal,dasha,transits}
    AstrologyFacade     birth-row decryption, the §6.4 `charts` cache, the §5.3 declines
"""

from sitara_api.astrology.chart_adapter import (
    AstroChartAdapter,
    BirthInput,
    ChartEngineUnavailable,
    InsufficientBirthData,
)
from sitara_api.astrology.service import AstrologyFacade, ChartBundle

__all__ = [
    "AstroChartAdapter",
    "AstrologyFacade",
    "BirthInput",
    "ChartBundle",
    "ChartEngineUnavailable",
    "InsufficientBirthData",
]
