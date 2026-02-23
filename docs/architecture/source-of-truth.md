# Source of Truth Map

This file defines what is canonical in this repository and what is reference material.

## Canonical Design Baseline

- Electrical + PCB source of truth:
  - `PCB/Rev02/uC_HAM_HAT_2M_rev02/uC_HAM_HAT_2M_rev02.kicad_sch`
  - `PCB/Rev02/uC_HAM_HAT_2M_rev02/uC_HAM_HAT_2M_rev02.kicad_pcb`
  - `PCB/Rev02/uC_HAM_HAT_2M_rev02/uC_HAM_HAT_2M_rev02.kicad_pro`
- Mechanical baseline:
  - `CAD/rev01/` (latest complete enclosure set currently stored in-repo)

## Manufacturing Outputs (Derived From Canonical)

- Fabrication and assembly outputs for Rev02:
  - `PCB/Rev02/uC_HAM_HAT_2M_rev02/production/bom.csv`
  - `PCB/Rev02/uC_HAM_HAT_2M_rev02/production/positions.csv`
  - `PCB/Rev02/uC_HAM_HAT_2M_rev02/production/netlist.ipc`
  - `PCB/Rev02/uC_HAM_HAT_2M_rev02/production/` (zip bundles)
- Rule: regenerate these from KiCad source when schematic/PCB changes.

## Local Libraries and Part Data

- Project part libraries:
  - `Components/HAm_Extension_Footprints.pretty/`
  - `Components/HAM_Extension_symbols/`
  - `Components/uconsole.kicad_sym`
- Rule: changes to footprints/symbols must be reviewed with Rev02 board impact.

## Reference Material (Not Source of Truth)

- Third-party reference projects:
  - `Resources/digirig/`
  - `Resources/SA818 Designs/`
  - `Resources/uEther/`
  - `Resources/SRFRS/`
  - `Resources/SA818 programmer/`
- Rule: do not treat these as your active product design files.

## Historical Revisions

- Kept for traceability and comparison:
  - `PCB/Rev00/`
  - `PCB/Rev01/`
- Rule: no new edits there unless explicitly doing historical backport work.

## Working Conventions

- Create new design edits in:
  - `PCB/Rev02/uC_HAM_HAT_2M_rev02/`
- Export manufacturing files to:
  - `PCB/Rev02/uC_HAM_HAT_2M_rev02/production/`
- Keep bring-up and process docs in:
  - `docs/operations/`
  - `docs/manufacturing/`
  - `docs/architecture/`

## Known Repo Risk

- Current `.gitignore` excludes `PCB/`, `CAD/`, `Components/`, `Resources/`, and `design.md`.
- Result: only docs/images are tracked today; core design assets are not versioned in git.
- Recommendation: migrate to a tracked-design branch strategy and remove broad ignores for source assets.
