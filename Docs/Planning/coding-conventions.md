# Coding Conventions

## General

- Keep source adapters separate from normalized map records.
- Preserve data provenance and avoid silent inference.
- Label approximations and unknown values explicitly.
- Prefer deterministic, repeatable transformations.
- Do not overwrite verified data in automated workflows.
- Keep source-to-target category mappings in the versioned machine-readable crosswalk; adapters must call the shared resolver instead of copying mapping tables into code.

## Code comments and documentation

- Begin each maintained Python module and major browser entry point with a summary of its responsibility, boundaries, and important data flow.
- Give public Python functions and classes docstrings that describe their contract, returned values, side effects, and non-obvious fallback behavior.
- Comment the reason for precedence rules, cache invalidation, safety checks, approximation, and external-service boundaries; do not merely restate the next line of code.
- Use short section comments in HTML and CSS to document structural and layout intent without annotating every element or declaration.
- Keep comments synchronized with implementation changes. A misleading comment is treated as a defect.
- Do not add comments to strict data formats such as JSON or GeoJSON, because standard parsers do not support them; document those contracts in `Docs/Planning` instead.

## Python

- Use type hints for public functions.
- Use `pathlib` for filesystem paths.
- Stream large CSV files instead of loading the nationwide source set into memory.
- Keep transformation functions independently testable.
- Use the standard library unless a dependency provides clear, documented value.

## Frontend

- Use semantic HTML and accessible labels.
- Keep design tokens in CSS custom properties.
- Do not couple UI logic to raw IRS column names.
- Bound large DOM lists and let the map engine manage point rendering.
- Respect reduced-motion preferences.
