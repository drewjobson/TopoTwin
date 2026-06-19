# Specification: TopoTwin 3D Property Topology Exporter

This specification defines the behavior, interface, and validation rules for the TopoTwin 3D Property Exporter. It serves as the single source of truth (blueprint) for the agent.

```yaml
specification:
  name: TopoTwin
  version: 2.0.0
  parameters:
    resolution:
      type: integer
      default: 40
      min: 10
      max: 100
    model_width_mm:
      type: number
      default: 100.0
      min: 50.0
      max: 300.0
    base_thickness_mm:
      type: number
      default: 2.0
      min: 1.0
    z_exaggeration:
      type: number
      default: 2.0
      min: 1.0
      max: 10.0
    border_thickness_mm:
      type: number
      default: 0.8
  security:
    enforce_policies: true
    default_role: viewer
    environment: production
  api:
    usgs_elevation_url: "[[USGS_URL]]"
    ct_parcel_url: "[[CT_PARCEL_URL]]"
```

---

## Behavior-Driven Scenarios (Gherkin Syntax)

### Feature: Property Topology Model Generation

  As a Developer or Property Planner,
  I want to generate a 3D-printable watertight STL model of a property,
  So that I can analyze local gradients and visualize structural layouts.

  Scenario: Resolve address and fetch property boundaries in Connecticut
    Given the geocoder resolves the address "Clinton, CT, USA"
    When the parcel service queries the Connecticut statewide parcel Feature Server
    Then it must return a valid parcel polygon containing vertices
    And the orchestrator must override the query bounds to fit the parcel bounds with a 25% margin.

  Scenario: Clip terrain to property boundaries (Pedestal Generation)
    Given a valid property boundary polygon in Clinton, CT
    When the elevation grid is downloaded from the USGS 3DEP API
    And the mesh builder constructs the solid 3D mesh
    Then any grid point outside the property polygon must have its Z coordinate set to base + border_thickness_mm
    And any grid point inside the property polygon must retain its true scaled USGS elevation.

  Scenario: Watertight Mesh Validation
    Given a constructed 3D mesh of a property
    When the validation harness runs a topological check
    Then every edge in the mesh must be shared by exactly two triangles (is manifold)
    And there must be no NaN or infinite coordinates in the output.

  Scenario: Role-Based Tool Gating (Zero-Trust Gating)
    Given the agent is running in the "viewer" role
    When the agent attempts to run the tool "raw_shell_execute"
    Then the Policy Server must intercept the call and block execution.
