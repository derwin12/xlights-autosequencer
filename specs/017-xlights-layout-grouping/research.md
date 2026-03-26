# Research: xLights Layout Grouping

**Date**: 2026-03-26
**Branch**: `017-xlights-layout-grouping`

---

## xlights_rgbeffects.xml Format

### Decision: Use `WorldPosX` / `WorldPosY` / `WorldPosZ` for coordinates
**Rationale**: These are the canonical xLights world-position attributes present on all placed model elements. They store floating-point values representing 3D coordinates in the layout space.
**Alternatives considered**: Screen-space pixel coordinates (too viewport-dependent, not layout-stable).

**Example model element**:
```xml
<model DisplayAs="Poly Line" name="RooflineLeft"
  WorldPosX="394.02" WorldPosY="20.02" WorldPosZ="0.00"
  ScaleX="1.0" ScaleY="1.0" ScaleZ="1.0"
  parm1="1" parm2="50" parm3="1"
  LayoutGroup="Default" ...>
  <subModel name="Segment1" nodesOrValues="1-25" />
</model>
```

### Decision: Use `parm1` × `parm2` as proxy pixel count
**Rationale**: For most model types (arches, matrices, trees, megatrees), `parm1` = number of strings and `parm2` = lights per string, so `parm1 * parm2` gives total node count. This is the standard xLights convention.
**Alternatives considered**: Counting `<ControllerConnection>` entries (not always present); `NodeCount` derived attribute (not in XML directly).
**Edge case**: For custom models, parm1/parm2 semantics differ; fallback to `parm1` alone.

### Decision: Sub-models are child `<subModel>` elements
**Rationale**: xLights stores sub-model definitions as child XML elements within the parent `<model>` tag. They are NOT separate top-level entries with slash names. Name-slash convention (e.g., `SingingFace/Eyes`) is the display name xLights shows in the sequence editor for sub-models.
**Alternatives considered**: Separate top-level models — not used by xLights for sub-models.

### Decision: Groups use `<ModelGroup>` elements with comma-separated `models` attribute
**Rationale**: The xLights source code and community XML samples confirm `<ModelGroup name="..." models="Model1,Model2,Model3" />` is the correct format. Groups live at the top level of `xlights_rgbeffects.xml`, sibling to `<model>` elements.

**Example group element**:
```xml
<ModelGroup name="01_BASE_All" models="RooflineLeft,RooflineRight,GarageLeft,WalkwayArch" />
```

### Decision: Hero detection via `DisplayAs` attribute for trees; name-substring for faces
**Rationale**: xLights uses `DisplayAs="Tree 360"`, `DisplayAs="Tree 180"`, `DisplayAs="Icicles"`, and similar for tree-type props. Singing faces do not have a single `DisplayAs` value — they are conventionally named with "Face" or "SingingFace" in the model name. Name-based detection is the only reliable approach for faces.
**Alternatives considered**: Parsing embedded face configuration XML (brittle, format varies by xLights version).

---

## Spatial Normalization

### Decision: Normalize from WorldPos bounding box, skip Z for primary tier assignment
**Rationale**: Most residential xLights layouts are 2D (Z=0 or near-zero). Horizontal (X) and vertical (Y) axes are sufficient for all 6 tiers. Z can be used as a tiebreaker for beat group ordering in the future.
**Alternatives considered**: 3D spatial bins — over-engineered for typical residential use.

---

## Aspect Ratio Classification

### Decision: Use `ScaleX` × default model width vs `ScaleY` × default model height
**Rationale**: Each xLights model type has an implicit default width/height before scaling. For the purposes of Vertical vs. Horizontal classification, the ratio of `ScaleY / ScaleX` (both available in the XML) serves as a reliable proxy when absolute dimensions are unavailable.
**Alternatives considered**: Computing bounding box from `WorldPos` + `Scale` + model type geometry — accurate but complex; the Scale ratio alone handles the vast majority of real-world props correctly.

---

## No New Dependencies Needed

**Decision**: Use Python stdlib `xml.etree.ElementTree` for XML parsing and writing.
**Rationale**: The project already uses ET in `src/analyzer/xtiming.py`. No new dependencies needed. The layout file is simple enough that a full XML library (lxml) adds no value.
**Alternatives considered**: `lxml` (faster, XPath support, but not installed; overkill for this use case).
