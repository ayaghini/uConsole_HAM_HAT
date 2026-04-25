# Rev04 Implementation Notes

Last updated: 2026-04-24

This document captures the Rev04 work completed during the latest EMI, library, and BOM normalization pass.

## 1. Scope of Changes

- Promoted Rev04 as active hardware baseline for ongoing edits.
- Added and validated EMI filter options for USB input and SA818 supply hardening.
- Normalized symbol/footprint/3D library handling for project portability.
- Regenerated and cleaned project BOM from schematic fields.

## 2. EMI Network Decisions (Rev04)

### USB input filtering

- Common-mode choke and bead/cap network were reviewed and corrected around pin mapping and return path intent.
- Intermediate net `GND_FLTR` was discussed as filtered return domain and must not be left floating.
- Final implementation direction:
  - preserve a controlled return path to system GND,
  - avoid accidental bypass paths that defeat the choke/bead effect,
  - keep shunt capacitors physically close to the corresponding filter element and connector boundary.

### SA818 supply hardening

- Space-constrained acceptable minimal path:
  - `+5V -> FB16 -> +5V_SA818`
  - local bulk decoupling (`C113`) to GND near SA818 VCC.
- If FL7 is DNP:
  - do not leave supply path open,
  - short FL7 path (or 0R) if required by schematic topology.
- Recommended enhancement if space allows:
  - add small local HF decoupler (e.g., 100nF) directly at SA818 VCC/GND.

## 3. Library Normalization (Project-Local)

Rev04 now uses project-local custom libraries for repeatability across machines.

### Footprints

- Active custom footprint library:
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/libs/project_footprints.pretty/`
- Footprint refs in schematic and PCB were remapped to:
  - `project_footprints:<name>`

### Symbols

- Local symbol libraries created under:
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/libs/symbols/`
- Project symbol table added:
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/sym-lib-table`
- Non-power symbols used by the project were verified to resolve from local symbol libs.
- Power symbols (`+5V`, `+3V3`, `GND`) are intentionally sourced from KiCad `power.kicad_sym`.

### 3D models

- Active local 3D model directory:
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/libs/3dmodels/`
- Project variable in `.kicad_pro`:
  - `COMPONENTS_3D = ${KIPRJMOD}/libs/3dmodels`
- Custom model refs in PCB now resolve using `${COMPONENTS_3D}/...`.

## 4. BOM Normalization

- Project BOM file refreshed from schematic fields:
  - `PCB/Rev04/uC_HAM_HAT_2M_rev04/BOM_rev02_from_pcbway.csv`
- Metadata pass included:
  - footprint consistency checks,
  - MPN/manufacturer fill where available,
  - DNP marking for non-placement mechanical/jumper items.

## 5. How To Add New Parts (Rev04 Process)

### Add symbol

1. Put symbol library file in:
   - `PCB/Rev04/uC_HAM_HAT_2M_rev04/libs/symbols/<lib>.kicad_sym`
2. Add `<lib>` to:
   - `PCB/Rev04/uC_HAM_HAT_2M_rev04/sym-lib-table`
3. Reopen schematic editor and place symbol.

### Add footprint

1. Put footprint in:
   - `PCB/Rev04/uC_HAM_HAT_2M_rev04/libs/project_footprints.pretty/<name>.kicad_mod`
2. Use footprint reference:
   - `project_footprints:<name>`

### Add 3D model

1. Put model file in:
   - `PCB/Rev04/uC_HAM_HAT_2M_rev04/libs/3dmodels/`
2. Reference model in footprint/PCB as:
   - `${COMPONENTS_3D}/<file.step>`

## 6. Verification Checklist

- Schematic loads without missing symbol errors.
- PCB loads without missing footprint warnings.
- 3D viewer resolves all custom models from `${KIPRJMOD}/libs/3dmodels`.
- BOM regenerates without missing footprint entries.
- EMI hardening population options are clearly marked (fitted vs DNP).
