"""Data models for Northwind Group consolidation with mandatory source-row lineage."""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class AccountBalance:
    """Represents a balance on a Group COA account with complete source-row audit trail."""
    group_code: str
    amount_local: float = 0.0
    amount_gbp: float = 0.0
    source_rows: List[str] = field(default_factory=list)

    def add(self, local_delta: float, gbp_delta: float, sources: List[str]) -> None:
        self.amount_local += local_delta
        self.amount_gbp += gbp_delta
        for s in sources:
            if s not in self.source_rows:
                self.source_rows.append(s)


@dataclass
class EliminationEntry:
    """Represents a consolidation elimination or adjustment journal line."""
    elim_id: str
    category: str
    group_code: str
    account_name: str
    debit_gbp: float
    credit_gbp: float
    source_rows: List[str]
    description: str


@dataclass
class AuditIssue:
    """Represents a data defect, policy violation, or anomaly logged to issues.json."""
    issue_id: str
    file: str
    line: str
    entity: str
    category: str
    amount_affected: Optional[float]
    currency: str
    amount_affected_gbp: Optional[float]
    system_action: str  # "blocked", "assumed", or "flagged"
    description: str
    resolution: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "file": self.file,
            "line": self.line,
            "entity": self.entity,
            "category": self.category,
            "amount_affected": round(self.amount_affected, 2) if self.amount_affected is not None else None,
            "currency": self.currency,
            "amount_affected_gbp": round(self.amount_affected_gbp, 2) if self.amount_affected_gbp is not None else None,
            "system_action": self.system_action,
            "description": self.description,
            "resolution": self.resolution,
        }