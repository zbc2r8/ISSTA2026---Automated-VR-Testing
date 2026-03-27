# Issue Severity Reports

The generated reports are available in this folder:

- Spatial Defect Severity Report.pdf
- Temporal Defect Severity Report.pdf

These reports summarize defect severity per application.

---

# How to Read the Reports

Each report uses the following metrics:

- Frequency – how often defects occur  
- Coverage – how much of the session is affected  
- Persistence – how long defects last  
- Instability – how often defects switch on/off  

## How to Interpret the Reports 

- High frequency / coverage → defects are common and affect large parts of the session  
- High persistence → defects last for long periods  
- High instability → defects appear and disappear frequently  
- Low values → mostly stable interaction  

The reports help identify short, unstable, and severe defect patterns.

---

# How to Generate New Reports

To generate new summary reports:

1. Generate detailed evaluation data:
   python code/compute_severity_metrics.py

2. Generate the summarized reports:
   python code/generate_defect_severity_report.py

Assumption:
The required data files are available in the data/ folder.
