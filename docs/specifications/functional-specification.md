# Functional Specification

Document owner: uConsole HAM HAT project
Document version: 1.1
Last updated: 2026-04-23
Status: archived in this repository

## 1. Purpose

This document marks the scope boundary after the repository split.

- Hardware design and hardware process docs remain in this repository.
- Application functional specification moved to the software repository:
  - `https://github.com/ayaghini/Ham-Radio-Hat-Software`

## 2. Scope in This Repository

In scope:
- Hardware architecture/source-of-truth mapping.
- Bring-up and validation process for hardware revisions.
- Manufacturing readiness and release process documentation.

Out of scope:
- Windows and Raspberry Pi Control Center application behavior.
- APRS/comms application features and UI workflows.
- Software runtime dependency and package launch instructions.

## 3. Canonical References

- Hardware source of truth: `docs/architecture/source-of-truth.md`
- Hardware bring-up: `docs/operations/bring-up.md`
- Software functional behavior (moved): `https://github.com/ayaghini/Ham-Radio-Hat-Software`

## 4. Change Control

When repository ownership boundaries change again, update this document and `readme.md` on the same day so users do not follow stale paths.