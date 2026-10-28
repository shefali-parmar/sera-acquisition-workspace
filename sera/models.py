"""The shared contract for records, search, and local storage."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

# Keep every U.S. state selectable, independent of the sample records.
STATES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}

SPECIALTIES = [
    "Dermatology",
    "General dentistry",
    "Orthodontics",
    "Pediatrics",
    "Family medicine",
    "Ophthalmology",
    "Endodontics",
    "Internal medicine",
]
Status = Literal["Listed for sale", "Open to succession", "Availability unknown"]
STATUSES = ["Listed for sale", "Open to succession", "Availability unknown"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Filters(StrictModel):
    """Only these constraints can be applied by deterministic search."""

    specialties: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)
    city: str = ""
    max_price: int | None = Field(default=None, ge=0)
    max_price_inclusive: bool = True
    statuses: list[Status] = Field(default_factory=lambda: STATUSES[:2])
    min_patients: int = Field(default=0, ge=0)
    min_years: int = Field(default=0, ge=0)
    min_sqft: int = Field(default=0, ge=0)
    min_operatories: int = Field(default=0, ge=0)
    keyword: str = ""
    include_undisclosed: bool = False
    distance_origin: str = Field(
        default="",
        max_length=120,
        description="U.S. ZIP code, city and state, or state area center for approximate distance.",
    )
    max_distance_miles: float | None = Field(
        default=None,
        ge=1,
        le=10000,
        allow_inf_nan=False,
        description="Optional straight-line radius of 1 to 10,000 miles. Replaces exact city/state matching; other filters still apply.",
    )

    @field_validator("states")
    @classmethod
    def valid_states(cls, values: list[str]) -> list[str]:
        if any(v not in STATES for v in values):
            raise ValueError("Use U.S. state abbreviations.")
        return values

    @field_validator("specialties")
    @classmethod
    def valid_specialties(cls, values: list[str]) -> list[str]:
        if any(v not in SPECIALTIES for v in values):
            raise ValueError("Unsupported specialty; ask for clarification.")
        return values


class SearchSuggestion(StrictModel):
    """Keep preferences and unsupported requirements visible instead of ignoring them."""

    filters: Filters
    preferences: list[str] = Field(default_factory=list)
    unverifiable: list[str] = Field(default_factory=list)
    clarification: str = ""


class Source(StrictModel):
    @field_validator("id", "label", "date", "kind")
    @classmethod
    def nonblank_source_fields(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Source fields must not be blank.")
        return value.strip()

    id: str
    label: str
    date: str
    kind: str


class Financials(StrictModel):
    """Illustrative operating earnings, distinct from take-home profit and financing."""

    source: str = Field(min_length=1)
    reporting_period: str = Field(min_length=1)
    accounting_basis: str = Field(min_length=1)
    normalized_ebitda: int = Field(ge=0)
    normalization_notes: str = Field(min_length=1)
    payroll_expense: int = Field(ge=0)
    supplies_expense: int = Field(ge=0)
    occupancy_expense: int = Field(ge=0)
    other_operating_expense: int = Field(ge=0)
    owner_compensation_included: Literal[True] = True


class PayerMix(StrictModel):
    commercial: int = Field(ge=0, le=100)
    medicare: int = Field(ge=0, le=100)
    medicaid: int = Field(ge=0, le=100)
    self_pay: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def complete_mix(self):
        if sum(self.model_dump().values()) != 100:
            raise ValueError("Payer mix percentages must total 100.")
        return self


class Operations(StrictModel):
    source: str = Field(min_length=1)
    providers: int = Field(ge=1)
    staff_fte: float = Field(gt=0)
    exam_rooms: int | None = Field(default=None, ge=1)
    weekly_open_hours: int = Field(ge=1, le=168)
    annual_visits: int = Field(ge=1)
    payer_mix: PayerMix
    equipment: list[str] = Field(min_length=1)
    transition_support: str = Field(min_length=1)


class Premises(StrictModel):
    """Practice and property prices are separate; inapplicable lease fields stay null."""

    source: str = Field(min_length=1)
    address: str = Field(min_length=1)
    occupancy: Literal["Leased", "Owned"]
    property_type: str = Field(min_length=1)
    annual_base_rent: int | None = Field(default=None, ge=0)
    annual_cam: int | None = Field(default=None, ge=0)
    lease_expires: str | None = None
    renewal_options: str = Field(min_length=1)
    annual_escalation_percent: float | None = Field(default=None, ge=0, le=100)
    assignment_terms: str = Field(min_length=1)
    landlord_consent_required: bool | None = None
    property_asking_price: int | None = Field(default=None, gt=0)
    property_included_in_practice_price: Literal[False] = False
    parking_spaces: int = Field(ge=0)
    accessibility: str = Field(min_length=1)
    permitted_use: str = Field(min_length=1)
    review_date: str = Field(min_length=1)
    review_status: str = Field(min_length=1)

    @model_validator(mode="after")
    def applicable_occupancy_terms(self):
        date.fromisoformat(self.review_date)
        if self.occupancy == "Leased":
            if any(
                value is None
                for value in (
                    self.annual_base_rent,
                    self.annual_cam,
                    self.lease_expires,
                    self.annual_escalation_percent,
                    self.landlord_consent_required,
                )
            ):
                raise ValueError("Leased premises require complete lease terms.")
            date.fromisoformat(self.lease_expires)
            if self.property_asking_price is not None:
                raise ValueError("Leased premises cannot advertise an owned property price.")
        elif any(
            value is not None
            for value in (
                self.annual_base_rent,
                self.annual_cam,
                self.lease_expires,
                self.annual_escalation_percent,
                self.landlord_consent_required,
            )
        ):
            raise ValueError("Owned premises must not carry inapplicable lease terms.")
        return self


class Practice(StrictModel):
    """None means unknown; seller reports and statistical provenance stay explicit."""

    id: str
    name: str
    specialty: str
    city: str
    state: str
    status: Status
    description: str
    founding_year: int | None = Field(default=None, ge=1800, le=date.today().year)
    history: list[str]
    availability_evidence: str
    availability_source: str
    availability_date: str
    asking_price: int | None = Field(default=None, ge=0)
    annual_revenue: int | None = Field(default=None, ge=0)
    revenue_period: str | None
    active_patients: int | None = Field(default=None, ge=0)
    patient_period: str | None
    sqft: int | None = Field(default=None, ge=0)
    operatories: int | None = Field(default=None, ge=0)
    legal_disclosures: str
    legal_research_status: str
    crime: dict | None
    patient_household_income: dict | None
    area_household_income: dict | None
    sources: list[Source]
    fictional: Literal[True] = True
    financials: Financials | None = None
    operations: Operations | None = None
    premises: Premises | None = None

    @field_validator(
        "id",
        "name",
        "city",
        "description",
        "availability_evidence",
        "availability_source",
        "availability_date",
    )
    @classmethod
    def nonblank_record_fields(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Practice identity and availability fields must not be blank.")
        return value.strip()

    @field_validator("state")
    @classmethod
    def valid_state(cls, value: str) -> str:
        if value not in STATES:
            raise ValueError("Practice state must be a supported U.S. abbreviation.")
        return value

    @field_validator("specialty")
    @classmethod
    def valid_specialty(cls, value: str) -> str:
        if value not in SPECIALTIES:
            raise ValueError("Practice specialty must be supported by the filters.")
        return value

    @model_validator(mode="after")
    def validate_evidence_ownership(self):
        source_ids = [source.id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Duplicate source IDs within a practice.")
        if any(not source_id.startswith(self.id + "-S") for source_id in source_ids):
            raise ValueError("Sources must belong to this practice.")
        if self.availability_source not in source_ids:
            raise ValueError("Availability source must reference this practice's sources.")
        for evidence in (self.crime, self.patient_household_income, self.area_household_income):
            if evidence is not None and evidence.get("source") not in source_ids:
                raise ValueError("Statistical evidence must reference this practice's sources.")
        for profile in (self.financials, self.operations, self.premises):
            if profile is not None and profile.source not in source_ids:
                raise ValueError("Profile evidence must reference this practice's sources.")
        if self.financials is not None:
            financials = self.financials
            operating_total = sum(
                (
                    financials.normalized_ebitda,
                    financials.payroll_expense,
                    financials.supplies_expense,
                    financials.occupancy_expense,
                    financials.other_operating_expense,
                )
            )
            if self.annual_revenue is None or operating_total != self.annual_revenue:
                raise ValueError(
                    "Operating expenses plus normalized EBITDA must equal annual revenue."
                )
            if self.premises is not None and self.premises.occupancy == "Leased":
                if financials.occupancy_expense != (
                    self.premises.annual_base_rent + self.premises.annual_cam
                ):
                    raise ValueError("Annual occupancy expense must equal base rent plus CAM.")
        return self


class SavedList(StrictModel):
    id: str
    name: str = Field(min_length=1, max_length=80)
    practice_ids: list[str] = Field(default_factory=list)

    @field_validator("id", "name", mode="before")
    @classmethod
    def normalize_identity(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("List ID and name must not be blank.")
        return value

    @field_validator("practice_ids")
    @classmethod
    def valid_memberships(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or value != value.strip() for value in values):
            raise ValueError("Practice IDs must not be blank or padded with whitespace.")
        if len(values) != len(set(values)):
            raise ValueError("Duplicate practice IDs in a saved list.")
        return values


class SavedStore(StrictModel):
    _storage_revision: str = PrivateAttr(default="missing")
    version: Literal[1] = 1
    lists: list[SavedList] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_lists(self):
        if len({item.id for item in self.lists}) != len(self.lists):
            raise ValueError("Duplicate saved list IDs.")
        if len({item.name.casefold() for item in self.lists}) != len(self.lists):
            raise ValueError("List names must be unique, ignoring capitalization.")
        return self
