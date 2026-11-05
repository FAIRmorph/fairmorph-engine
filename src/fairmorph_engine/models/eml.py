import re
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class LicenseEnum(StrEnum):
    CC0_1_0 = "https://creativecommons.org/publicdomain/zero/1.0/legalcode"
    CC_BY_4_0 = "https://creativecommons.org/licenses/by/4.0/legalcode"


class Agent(BaseModel):
    given_name: str = Field(..., min_length=1)
    surname: str = Field(..., min_length=1)
    organization: str | None = None
    email: str | None = None
    orcid: str | None = Field(None, description="Format: 0000-0000-0000-0000")

    @field_validator("orcid")
    @classmethod
    def validate_orcid(cls, v: str | None) -> str | None:
        if v is None:
            return None
        clean = v.strip().replace("https://orcid.org/", "")
        if not re.match(r"^\d{4}-\d{4}-\d{4}-\d{3}[0-9X]$", clean):
            raise ValueError("Ungültiges ORCID-Format (z. B. 0000-0002-1825-0097)")
        return f"https://orcid.org/{clean}"


class GeographicBoundingBox(BaseModel):
    west_bounding_coordinate: float = Field(..., ge=-180.0, le=180.0)
    east_bounding_coordinate: float = Field(..., ge=-180.0, le=180.0)
    north_bounding_coordinate: float = Field(..., ge=-90.0, le=90.0)
    south_bounding_coordinate: float = Field(..., ge=-90.0, le=90.0)
    description: str = Field(..., min_length=3)

    @field_validator("south_bounding_coordinate")
    @classmethod
    def validate_latitudes(cls, south: float, info) -> float:
        north = info.data.get("north_bounding_coordinate")
        if north is not None and south > north:
            raise ValueError(
                "south_bounding_coordinate darf nicht größer als north_bounding_coordinate sein"
            )
        return south


class ProjectMetadata(BaseModel):
    project_id: str = Field(..., pattern=r"^urn:uuid:[0-9a-fA-F-]{36}$")
    dataset_version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    title: str = Field(..., min_length=5, max_length=255)
    abstract: str = Field(..., min_length=20)
    language: str = Field("eng", min_length=3, max_length=3)
    license: LicenseEnum = LicenseEnum.CC_BY_4_0
    creators: list[Agent] = Field(..., min_length=1)
    contacts: list[Agent] = Field(..., min_length=1)
    geographic_coverage: GeographicBoundingBox
