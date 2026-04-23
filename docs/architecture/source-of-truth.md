# Source of Truth Map

Last updated: 2026-04-23

This file defines what is canonical in this repository and what is reference material.

## Canonical Design Baseline

- Electrical + PCB source of truth (active):
  - `PCB/Rev03/uC_HAM_HAT_2M_rev03/uC_HAM_HAT_2M_rev03.kicad_sch`
  - `PCB/Rev03/uC_HAM_HAT_2M_rev03/uC_HAM_HAT_2M_rev03.kicad_pcb`
  - `PCB/Rev03/uC_HAM_HAT_2M_rev03/uC_HAM_HAT_2M_rev03.kicad_pro`
- Previous baseline kept for reference:
  - `PCB/Rev02/uC_HAM_HAT_2M_rev02/`
- Mechanical baseline:
  - `CAD/rev01/`

## Manufacturing Outputs (Derived From Canonical)

- Rev03 production outputs:
  - `PCB/Rev03/uC_HAM_HAT_2M_rev03/production/bom.csv`
  - `PCB/Rev03/uC_HAM_HAT_2M_rev03/production/positions.csv`
  - `PCB/Rev03/uC_HAM_HAT_2M_rev03/production/netlist.ipc`
  - `PCB/Rev03/uC_HAM_HAT_2M_rev03/production/`
- Rule: regenerate these from KiCad source when schematic/PCB changes.

## Local Libraries and Part Data

- Rev03 project-scoped libraries:
  - `PCB/Rev03/uC_HAM_HAT_2M_rev03/libs/project_footprints.pretty/`
- Shared libraries in repo:
  - `Components/HAm_Extension_Footprints.pretty/`
  - `Components/HAM_Extension_symbols/`
  - `Components/uconsole.kicad_sym`
- Rule: changes to footprints/symbols must be reviewed against active board revision impact.

## Software Boundary

- This repository is hardware-focused.
- Software moved to a dedicated repository:
  - `https://github.com/ayaghini/Ham-Radio-Hat-Software`
- Rule: software launch, runtime, and application behavior docs should live in the software repo.

## Reference Material (Not Source of Truth)

- Third-party reference projects:
  - `Resources/digirig/`
  - `Resources/SA818 Designs/`
  - `Resources/uEther/`
  - `Resources/SRFRS/`
  - `Resources/SA818 programmer/`
- Rule: do not treat these as active product design files.

## Historical Revisions

- Kept for traceability and comparison:
  - `PCB/Rev00/`
  - `PCB/Rev01/`
  - `PCB/Rev02/`
- Rule: no new edits there unless explicitly doing historical backport work.

## Working Conventions

- New board edits:
  - `PCB/Rev03/uC_HAM_HAT_2M_rev03/`
- Production exports:
  - `PCB/Rev03/uC_HAM_HAT_2M_rev03/production/`
- Process docs:
  - `docs/operations/`
  - `docs/manufacturing/`
  - `docs/architecture/`

## Known Repo Risk

- Current `.gitignore` excludes `PCB/`, `CAD/`, `Components/`, `Resources/`, and `design.md`.
- Result: only docs/images are tracked today; core design assets are not versioned in git.
- Recommendation: migrate to a tracked-design branch strategy and remove broad ignores for source assets.