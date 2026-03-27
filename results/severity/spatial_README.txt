SECTION 1 — How to run
Run the script with analysis_type = spatial or temporal.

SECTION 2 — How to read metrics
Frequency = how often defects happen
Coverage = how much of the session is affected
Persistence = how long defects last
Instability = how often defects switch

SECTION 3 — Severity thresholds
The thresholds are heuristic and are not from literature.
They can be modified in the script.
Changing the thresholds changes classification.

Current Thresholds
MINOR_MAX_LENGTH = 2
MODERATE_MAX_LENGTH = 5
SEVERE_MIN_LENGTH = 6
COVERAGE_SEVERE_THRESHOLD = 0.30
INSTABILITY_THRESHOLD = 0.15
PERSISTENCE_RATIO_THRESHOLD = 0.20
Changing these values changes how games are classified in the report.

SECTION 4 — What the report shows
The report summarizes defect severity per game.
It highlights minor, unstable, and severe patterns.
