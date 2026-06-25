"""Value objects (enums) for the ClauseIQ domain.

Value objects are immutable, identity-less types defined entirely by their
value. Enums are the natural representation for the small, closed vocabularies
the domain reasons about: how severe a risk is, what kind of clause we are
looking at, which jurisdiction applies, and which statute a citation points to.
"""

from __future__ import annotations

from enum import Enum, IntEnum


class Severity(IntEnum):
    """Severity of a flagged clause, ordered from least to most serious.

    Modelled as an :class:`~enum.IntEnum` deliberately: severity is inherently
    *ordered*, so we want ``Severity.HIGH > Severity.LOW`` and the ability to
    sort risk flags by severity for free, without a separate ranking table.

    The integer values are an internal ordering, **not** a public score. Use
    :attr:`normalized_score` when a 0..1 number is needed (e.g. for a gauge in
    the UI) and :attr:`label` for human-facing text.
    """

    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        """Lower-case, human-facing name (e.g. ``"critical"``)."""
        return self.name.lower()

    @property
    def normalized_score(self) -> float:
        """Severity mapped deterministically onto the inclusive range 0.0-1.0."""
        return self.value / max(member.value for member in Severity)


class ClauseType(str, Enum):
    """Categories of contract clause ClauseIQ recognises and reasons about.

    A ``str`` enum so members serialise to readable, stable strings across the
    API/MCP boundary. The vocabulary is oriented at the contracts our target
    users sign: residential leases, employment letters, and freelance/service
    agreements under Indian law.
    """

    # Money & exit
    SECURITY_DEPOSIT = "security_deposit"
    LATE_FEE = "late_fee"
    PENALTY = "penalty"
    LOCK_IN = "lock_in"
    NOTICE_PERIOD = "notice_period"
    TERMINATION = "termination"
    AUTO_RENEWAL = "auto_renewal"
    RENT_ESCALATION = "rent_escalation"

    # Risk allocation
    INDEMNITY = "indemnity"
    LIABILITY_LIMITATION = "liability_limitation"
    UNILATERAL_AMENDMENT = "unilateral_amendment"
    FORCE_MAJEURE = "force_majeure"

    # Restraints & IP
    NON_COMPETE = "non_compete"
    NON_SOLICIT = "non_solicit"
    CONFIDENTIALITY = "confidentiality"
    IP_ASSIGNMENT = "ip_assignment"

    # Dispute resolution
    ARBITRATION = "arbitration"
    JURISDICTION = "jurisdiction"
    GOVERNING_LAW = "governing_law"

    # Fallback
    OTHER = "other"


class Jurisdiction(str, Enum):
    """Supported Indian jurisdictions, matching the API's accepted values.

    Values follow the ``IN-<state>`` ISO-3166-2 style used at the API boundary
    (``Literal["IN-MH", "IN-DL", "IN-KA"]``).
    """

    IN_MH = "IN-MH"  # Maharashtra
    IN_DL = "IN-DL"  # Delhi
    IN_KA = "IN-KA"  # Karnataka

    @property
    def state_name(self) -> str:
        """Human-facing state name for display."""
        return _JURISDICTION_NAMES[self]


_JURISDICTION_NAMES: dict[Jurisdiction, str] = {
    Jurisdiction.IN_MH: "Maharashtra",
    Jurisdiction.IN_DL: "Delhi",
    Jurisdiction.IN_KA: "Karnataka",
}


class LawCode(str, Enum):
    """Statutes and codes a :class:`Citation` can point to.

    Central (apply nationwide) and state-specific rent-control acts are listed
    together; the ``title`` property gives the canonical long form used in
    citations and disclaimers.
    """

    # Central statutes
    ICA_1872 = "ICA_1872"  # Indian Contract Act, 1872
    SRA_1963 = "SRA_1963"  # Specific Relief Act, 1963
    CPA_2019 = "CPA_2019"  # Consumer Protection Act, 2019

    # State rent-control acts
    MH_RENT_1999 = "MH_RENT_1999"  # Maharashtra Rent Control Act, 1999
    DL_RENT_1958 = "DL_RENT_1958"  # Delhi Rent Control Act, 1958
    KA_RENT_2001 = "KA_RENT_2001"  # Karnataka Rent Act, 2001

    OTHER = "OTHER"

    @property
    def full_title(self) -> str:
        """Canonical long-form title of the statute.

        Named ``full_title`` (not ``title``) deliberately: ``LawCode`` subclasses
        ``str``, and ``str.title()`` already exists — overriding it would change
        the meaning of an inherited method.
        """
        return _LAW_TITLES[self]


_LAW_TITLES: dict[LawCode, str] = {
    LawCode.ICA_1872: "Indian Contract Act, 1872",
    LawCode.SRA_1963: "Specific Relief Act, 1963",
    LawCode.CPA_2019: "Consumer Protection Act, 2019",
    LawCode.MH_RENT_1999: "Maharashtra Rent Control Act, 1999",
    LawCode.DL_RENT_1958: "Delhi Rent Control Act, 1958",
    LawCode.KA_RENT_2001: "Karnataka Rent Act, 2001",
    LawCode.OTHER: "Other / uncodified",
}


__all__ = ["ClauseType", "Jurisdiction", "LawCode", "Severity"]
