# Northwind Group FY2024 Consolidation Engine

**Bundle ID:** `NWG-D0BC`  
**Candidate:** Lakshit Sehdev (`ls`)

Deterministic, audit-traceable multi-currency consolidation pipeline for Northwind Group (Northwind Inc. USD parent, Northwind UK Ltd 100% GBP subsidiary, and Northwind India Pvt Ltd 80% INR subsidiary acquired 1 July 2024).

## 1. Setup

Requires Python 3.10+ and `pandas`.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt