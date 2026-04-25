# Source of Truth Map

Last updated: 2026-04-24

This file defines what is canonical in this repository and what is reference material.

## Canonical Design Baseline

- Electrical + PCB source of truth (active):
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/uC_HAM_HAT_2M_rev04.kicad_sch`
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/uC_HAM_HAT_2M_rev04.kicad_pcb`
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/uC_HAM_HAT_2M_rev04.kicad_pro`
- Previous baselines kept for reference:
  - `PCB/Rev03/uC_HAM_HAT_2M_rev03/`
  - `PCB/Rev02/uC_HAM_HAT_2M_rev02/`
- Mechanical baseline:
  - `CAD/rev01/`

## Manufacturing Outputs (Derived From Canonical)

- Rev04 production outputs:
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/production/bom.csv`
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/production/positions.csv`
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/production/netlist.ipc`
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/production/`
- Rev04 project BOM variant:
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/BOM_rev02_from_pcbway.csv`
- Rule: regenerate these from KiCad source when schematic/PCB changes.

## Local Libraries and Part Data

- Rev04 project-scoped libraries:
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/libs/project_footprints.pretty/`
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/libs/symbols/`
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/libs/3dmodels/`
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/fp-lib-table`
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/sym-lib-table`
- Shared libraries in repo:
  - `Components/HAm_Extension_Footprints.pretty/`
  - `Components/HAM_Extension_symbols/`
  - `Components/uconsole.kicad_sym`
- Rule:
  - Copy custom symbols/footprints/3D models into the active project `libs/` paths.
  - Prefer `${KIPRJMOD}`-based references in all project files.
  - Keep shared `Components/` as source material, not runtime dependency for active project.

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
  - `PCB/Rev03/`
- Rule: no new edits there unless explicitly doing historical backport work.

## Working Conventions

- New board edits:
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/`
- Production exports:
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/production/`
- Process docs:
  - `docs/operations/`
  - `docs/manufacturing/`
  - `docs/architecture/`

## Known Repo Risk

- Current `.gitignore` excludes `PCB/`, `CAD/`, `Components/`, `Resources/`, and `design.md`.
- Result: only docs/images are tracked today; core design assets are not versioned in git.
- Recommendation: migrate to a tracked-design branch strategy and remove broad ignores for source assets.
