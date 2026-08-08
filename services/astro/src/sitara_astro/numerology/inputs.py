"""Numerology engine options — every convention explicit and recorded."""

from pydantic import BaseModel, ConfigDict, Field
from sitara_schemas.facts import MasterNumberPolicy, NumerologySystem


class NumerologyOptions(BaseModel):
    """Chaldean is primary and Pythagorean secondary (§5.5); both are computed
    so the secondary is always available for comparison, never invented later.
    """

    model_config = ConfigDict(frozen=True)

    master_numbers: MasterNumberPolicy = MasterNumberPolicy.REDUCE
    systems: tuple[NumerologySystem, ...] = Field(
        default=(NumerologySystem.CHALDEAN, NumerologySystem.PYTHAGOREAN), min_length=1
    )

    @property
    def primary(self) -> NumerologySystem:
        return self.systems[0]
