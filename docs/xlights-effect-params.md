# xLights Effect Parameters Reference

Source: `resources/effectmetadata/` in the [xLights repo](https://github.com/xLightsSequencer/xLights).
Parameter storage names are what xLights writes into XSQ `<EffectDB>` settings strings.
Use these exact names in `parameter_overrides` in variant JSON files.

Control type prefixes:
- `E_SLIDER_` — numeric slider (int or float)
- `E_CHECKBOX_` — boolean toggle
- `E_CHOICE_` — enum dropdown
- `E_TEXTCTRL_` — text/numeric input (rare — only use when metadata says `textctrl`)

---

## Adjust

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_CHOICE_Action` | Adjustment | choice | None | `None`, `Adjust By Value`, `Adjust By Percentage`, `Set Minimum`, +5 more |  | The type of channel value adjustment to apply. Options in... |
| `E_SPIN_Value1` | Value 1 | spin | 0 | -255–255 |  | Primary adjustment value. Its meaning depends on the acti... |
| `E_SPIN_Value2` | Value 2 | spin | 0 | -255–255 |  | Secondary adjustment value used by actions that require a... |
| `E_SPIN_NthChannel` | Nth Channel | spin | 1 | 1–32 |  | Apply the adjustment to every Nth channel. A value of 1 a... |
| `E_SPIN_StartingAt` | Starting At | spin | 1 | 1–100 |  | The first channel number (1-based) to begin applying the ... |
| `E_SPIN_Count` | Count | spin | 0 | 0–10000 |  | Maximum number of channels to adjust. A value of 0 means ... |

---

## Bars

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Bars_BarCount` | Palette Rep | slider | 1 | 1–5 | ✓ | Number of times the full palette color sequence repeats a... |
| `E_SLIDER_Bars_Cycles` | Cycles | slider | 1.0 | 0.0–30.0 (×1/10) | ✓ | Number of times the bars scroll completely across the mod... |
| `E_CHOICE_Bars_Direction` | Direction | choice | up | `up`, `down`, `expand`, `compress`, +10 more |  | Direction the bars travel. Expand/compress radiate from o... |
| `E_SLIDER_Bars_Center` | Center Point | slider | 0 | -100–100 | ✓ | Shifts the expansion/compression origin or the static bar... |
| `E_CHECKBOX_Bars_Highlight` | Highlight | checkbox | false | — |  | Adds a bright white highlight line at the leading edge of... |
| `E_CHECKBOX_Bars_UseFirstColorForHighlight` | Use First Color for Highlight | checkbox | false | — |  | When Highlight is enabled, uses the first palette color f... |
| `E_CHECKBOX_Bars_3D` | 3D | checkbox | false | — |  | Applies a brightness or alpha gradient within each bar so... |
| `E_CHECKBOX_Bars_Gradient` | Gradient | checkbox | false | — |  | Smoothly blends colors between adjacent bars instead of u... |

---

## Butterfly

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_CHOICE_Butterfly_Colors` | Colors | choice | Rainbow | `Rainbow`, `Palette` |  | Selects the color source. Rainbow uses a full HSV rainbow... |
| `E_SLIDER_Butterfly_Style` | Style | slider | 1 | 1–10 |  | Selects the mathematical pattern formula. Styles 1-5 prod... |
| `E_SLIDER_Butterfly_Chunks` | Bkgrd Chunks | slider | 1 | 1–10 | ✓ | Divides the pattern into repeated segments, increasing th... |
| `E_SLIDER_Butterfly_Skip` | Bkgrd Skip | slider | 2 | 2–10 | ✓ | Controls the spacing interval used when sampling the patt... |
| `E_SLIDER_Butterfly_Speed` | Speed | slider | 10 | 0–100 | ✓ | Controls how fast the pattern animates. For styles 1-5 th... |
| `E_CHOICE_Butterfly_Direction` | Direction | choice | Normal | `Normal`, `Reverse` |  | Sets the animation direction. Reverse inverts the pattern... |

---

## Candle

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Candle_FlameAgility` | Flame Agility | slider | 2 | 1–10 | ✓ | Controls how quickly the flame responds to changes. Highe... |
| `E_SLIDER_Candle_WindBaseline` | Wind Baseline | slider | 30 | 0–255 | ✓ | Sets the resting wind strength that the simulated wind co... |
| `E_SLIDER_Candle_WindVariability` | Wind Variability | slider | 5 | 0–10 | ✓ | Controls how often random wind gusts occur. Higher values... |
| `E_SLIDER_Candle_WindCalmness` | Wind Calmness | slider | 2 | 0–10 | ✓ | Dampens the wind's effect on the flame. Higher values mak... |
| `E_CHECKBOX_PerNode` | Per node | checkbox | false | — |  | When enabled, each pixel gets its own independent flame s... |
| `E_CHECKBOX_UsePalette` | Use Palette | checkbox | false | — |  | When enabled, the flame color blends between the first tw... |

---

## Circles

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Circles_Count` | Number of Circles | slider | 3 | 1–10 | ✓ | Sets the number of circles drawn on the model. In radial ... |
| `E_SLIDER_Circles_Size` | Size | slider | 5 | 1–20 | ✓ | Controls the radius of each circle. In radial mode, this ... |
| `E_SLIDER_Circles_Speed` | Speed | slider | 10 | 1–30 | ✓ | Controls how fast the circles move across the model. In r... |
| `E_CHECKBOX_Circles_Bounce` | Bounce | checkbox | false | — |  | When enabled, circles bounce off the edges of the model i... |
| `E_CHECKBOX_Circles_Radial` | Radial | checkbox | false | — |  | Draws expanding concentric rings radiating outward from t... |
| `E_CHECKBOX_Circles_Plasma` | Plasma | checkbox | false | — |  | Uses a metaball algorithm where overlapping circle influe... |
| `E_CHECKBOX_Circles_Radial_3D` | Radial 3D | checkbox | false | — |  | Draws expanding concentric rings with a continuously cycl... |
| `E_CHECKBOX_Circles_Bubbles` | Bubbles | checkbox | false | — |  | Draws hollow circle outlines instead of filled circles, a... |
| `E_CHECKBOX_Circles_Linear_Fade` | Linear Fade | checkbox | false | — |  | Makes each circle fade from full brightness at the center... |
| `E_SLIDER_Circles_XC` | X Center | slider | 0 | -50–50 | ✓ | Shifts the center point of radial rings horizontally. Onl... |
| `E_SLIDER_Circles_YC` | Y Center | slider | 0 | -50–50 | ✓ | Shifts the center point of radial rings vertically. Only ... |

---

## Color Wash

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_ColorWash_Cycles` | Count | slider | 1.0 | 0.1–20.0 (×1/10) | ✓ | Number of times the full palette color sequence cycles du... |
| `E_CHECKBOX_ColorWash_VFade` | Vertical Fade | checkbox | false | — |  | Fades the wash color from full brightness at the vertical... |
| `E_CHECKBOX_ColorWash_HFade` | Horizontal Fade | checkbox | false | — |  | Fades the wash color from full brightness at the horizont... |
| `E_CHECKBOX_ColorWash_ReverseFades` | Reverse Fades | checkbox | false | — |  | Reverses the direction of the vertical and horizontal fad... |
| `E_CHECKBOX_ColorWash_Shimmer` | Shimmer | checkbox | false | — |  | Alternates between the current wash color and black on ev... |
| `E_CHECKBOX_ColorWash_CircularPalette` | Circular Palette | checkbox | false | — |  | Makes the palette wrap around by blending the last color ... |

---

## Curtain

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_CHOICE_Curtain_Edge` | Curtain Edge | choice | left | `left`, `center`, `right`, `bottom`, +2 more |  | Sets which edge or pair of edges the curtain opens/closes... |
| `E_CHOICE_Curtain_Effect` | Effect | choice | open | `open`, `close`, `open then close`, `close then open` |  | Controls the curtain motion. Open reveals the model by pu... |
| `E_SLIDER_Curtain_Swag` | Swag Width | slider | 3 | 0–10 | ✓ | Controls the width of the decorative draped curve at the ... |
| `E_SLIDER_Curtain_Speed` | Swag Speed | slider | 1.0 | 0.0–10.0 (×1/10) | ✓ | Controls how fast the curtain opens or closes. Values abo... |
| `E_CHECKBOX_Curtain_Repeat` | Repeat | checkbox | false | — |  | When enabled, the curtain motion cycles repeatedly for th... |

---

## Fan

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Fan_CenterX` | Center X | slider | 50 | 0–100 | ✓ | Horizontal position of the fan center as a percentage of ... |
| `E_SLIDER_Fan_CenterY` | Center Y | slider | 50 | 0–100 | ✓ | Vertical position of the fan center as a percentage of th... |
| `E_SLIDER_Fan_Start_Radius` | Radius1 | slider | 1 | 0–2500 | ✓ | Inner radius of the fan blades. Pixels closer to the cent... |
| `E_SLIDER_Fan_Start_Angle` | Angle | slider | 0 | 0–360 | ✓ | Starting rotation angle of the fan blades in degrees. |
| `E_SLIDER_Fan_End_Radius` | Radius2 | slider | 10 | 0–2500 | ✓ | Outer radius of the fan blades. Pixels farther from the c... |
| `E_SLIDER_Fan_Revolutions` | Rev's | slider | 2.0 | 0.0–10.0 (×1/360) | ✓ | Total number of revolutions the fan rotates over the dura... |
| `E_SLIDER_Fan_Num_Blades` | # Blades | slider | 3 | 1–16 | ✓ | Number of blades evenly spaced around the fan. |
| `E_SLIDER_Fan_Blade_Width` | Width | slider | 50 | 5–100 | ✓ | Angular width of each blade as a percentage of the space ... |
| `E_SLIDER_Fan_Blade_Angle` | Angle | slider | 90 | -360–360 | ✓ | Twist angle applied to each blade based on distance from ... |
| `E_SLIDER_Fan_Num_Elements` | # Elements | slider | 1 | 1–4 | ✓ | Number of colored sub-elements within each blade. Each el... |
| `E_SLIDER_Fan_Element_Width` | Width | slider | 100 | 5–100 | ✓ | Width of each element as a percentage of the available el... |
| `E_SLIDER_Fan_Duration` | Duration | slider | 80 | 0–100 | ✓ | Percentage of the effect time that the blades are fully v... |
| `E_SLIDER_Fan_Accel` | Acceleration | slider | 0 | -10–10 | ✓ | Adjusts the rotation speed curve. Positive values acceler... |
| `E_CHECKBOX_Fan_Reverse` | Reverse | checkbox | false | — |  | Reverses the direction of fan rotation. |
| `E_CHECKBOX_Fan_Blend_Edges` | Blend Edges | checkbox | true | — |  | When enabled, blade edges fade smoothly using alpha or br... |
| `E_CHECKBOX_Fan_Scale` | Scale to Buffer | checkbox | true | — |  | When enabled, radius values are treated as percentages of... |

---

## Fill

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Fill_Position` | Position | slider | 100 | 0–100 | ✓ | How far the fill extends across the buffer as a percentag... |
| `E_SLIDER_Fill_Band_Size` | Band Size | slider | 0 | 0–250 | ✓ | Width of each colored band in pixels. When zero, colors b... |
| `E_SLIDER_Fill_Skip_Size` | Skip Size | slider | 0 | 0–250 | ✓ | Number of blank (black) pixels between each colored band.... |
| `E_SLIDER_Fill_Offset` | Offset | slider | 0 | 0–100 | ✓ | Shifts the starting position of the fill. Interpretation ... |
| `E_CHECKBOX_Fill_Offset_In_Pixels` | Offset in Pixels | checkbox | true | — |  | When enabled, the offset value is in pixels. When disable... |
| `E_CHECKBOX_Fill_Color_Time` | Change Color based on Time | checkbox | false | — |  | When enabled, color is determined by the effect time posi... |
| `E_CHECKBOX_Fill_Wrap` | Wrap | checkbox | true | — |  | When enabled, the fill wraps around to the beginning of t... |
| `E_CHOICE_Fill_Direction` | Direction | choice | Up | `Up`, `Down`, `Left`, `Right` |  | Direction the fill progresses across the buffer. |

---

## Fire

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Fire_Height` | Height | slider | 50 | 1–100 | ✓ | Controls how tall the flames reach. Higher values produce... |
| `E_SLIDER_Fire_HueShift` | Hue Shift | slider | 0 | 0–100 | ✓ | Shifts the fire color palette hue. At zero the fire is re... |
| `E_SLIDER_Fire_GrowthCycles` | Growth Cycles | slider | 0.0 | 0.0–20.0 (×1/10) | ✓ | Number of times the fire height oscillates (grows and shr... |
| `E_CHECKBOX_Fire_GrowWithMusic` | Grow with music | checkbox | false | — |  | When enabled, flame height is driven by audio volume inst... |
| `E_CHOICE_Fire_Location` | Location | choice | Bottom | `Bottom`, `Top`, `Left`, `Right` |  | Which edge of the buffer the fire originates from. |

---

## Fireworks

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Fireworks_Explosions` | Number of Explosions | slider | 16 | 1–50 |  | Total number of firework explosions randomly distributed ... |
| `E_SLIDER_Fireworks_Count` | Particles in Explosion | slider | 50 | 1–100 | ✓ | Number of particles created in each explosion. More parti... |
| `E_SLIDER_Fireworks_Velocity` | Velocity of Particles | slider | 2 | 1–10 | ✓ | Maximum speed of particles as they fly outward from the e... |
| `E_SLIDER_Fireworks_XVelocity` | X Velocity | slider | 0 | -100–100 | ✓ | Horizontal drift applied to all particles. Positive value... |
| `E_SLIDER_Fireworks_YVelocity` | Y Velocity | slider | 0 | -100–100 | ✓ | Vertical drift applied to all particles. Positive values ... |
| `E_SLIDER_Fireworks_XLocation` | X Location | slider | -1 | -1–100 | ✓ | Fixed horizontal position for explosions as a percentage ... |
| `E_SLIDER_Fireworks_YLocation` | Y Location | slider | -1 | -1–100 | ✓ | Fixed vertical position for explosions as a percentage of... |
| `E_CHECKBOX_Fireworks_HoldColour` | Hold color | checkbox | true | — |  | When enabled, each particle keeps its initial color as it... |
| `E_CHECKBOX_Fireworks_Gravity` | Gravity | checkbox | true | — |  | When enabled, particles arc downward over time simulating... |
| `E_SLIDER_Fireworks_Fade` | Particle Fade | slider | 50 | 1–100 | ✓ | How long particles remain visible before fading out. High... |
| `E_CHECKBOX_Fireworks_UseMusic` | Fire with music | checkbox | false | — |  | When enabled, explosions are triggered by audio volume pe... |
| `E_SLIDER_Fireworks_Sensitivity` | Trigger level | slider | 50 | 0–100 |  | Audio volume threshold for triggering explosions when Fir... |
| `E_CHECKBOX_FIRETIMING` | Fire with timing track | checkbox | false | — |  | When enabled, explosions are triggered at the start and e... |
| `E_CHOICE_FIRETIMINGTRACK` | Timing Track | choice |  | — |  | The timing track whose marks trigger firework explosions ... |

---

## Galaxy

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Galaxy_CenterX` | Center X | slider | 50 | 0–100 | ✓ | Horizontal position of the galaxy center as a percentage ... |
| `E_SLIDER_Galaxy_CenterY` | Center Y | slider | 50 | 0–100 | ✓ | Vertical position of the galaxy center as a percentage of... |
| `E_SLIDER_Galaxy_Start_Radius` | Radius | slider | 1 | 0–250 | ✓ | Inner radius of the spiral arm at the center of the galaxy. |
| `E_SLIDER_Galaxy_Start_Width` | Width | slider | 5 | 0–255 | ✓ | Thickness of the spiral arm at the inner starting point. |
| `E_SLIDER_Galaxy_Start_Angle` | Angle | slider | 0 | 0–360 | ✓ | Initial rotation angle of the spiral arm in degrees. |
| `E_SLIDER_Galaxy_End_Radius` | Radius | slider | 10 | 0–250 | ✓ | Outer radius of the spiral arm at the edge of the galaxy. |
| `E_SLIDER_Galaxy_End_Width` | Width | slider | 5 | 0–255 | ✓ | Thickness of the spiral arm at the outer ending point. |
| `E_SLIDER_Galaxy_Revolutions` | Rev's | slider | 4.0 | 0.0–10.0 (×1/360) | ✓ | Number of full revolutions the spiral arm wraps around th... |
| `E_SLIDER_Galaxy_Duration` | Head Duration | slider | 20 | 0–100 | ✓ | Percentage of the effect time that the leading head of th... |
| `E_SLIDER_Galaxy_Accel` | Acceleration | slider | 0 | -10–10 | ✓ | Adjusts the animation speed curve. Positive values accele... |
| `E_CHECKBOX_Galaxy_Reverse` | Reverse | checkbox | false | — |  | Reverses the direction the spiral arm rotates. |
| `E_CHECKBOX_Galaxy_Blend_Edges` | Blend Edges | checkbox | true | — |  | When enabled, the spiral arm edges fade smoothly using al... |
| `E_CHECKBOX_Galaxy_Inward` | Inward | checkbox | false | — |  | When enabled, the spiral draws from the outside inward. W... |
| `E_CHECKBOX_Galaxy_Scale` | Scale To Buffer | checkbox | true | — |  | When enabled, radius and width values are treated as perc... |

---

## Garlands

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Garlands_Type` | Garland Type | slider | 0 | 0–4 |  | Selects the garland droop pattern. Type 0 is flat, types ... |
| `E_SLIDER_Garlands_Spacing` | Spacing | slider | 10 | 1–100 | ✓ | Distance between garland rows as a percentage of the buff... |
| `E_SLIDER_Garlands_Cycles` | Cycles | slider | 1.0 | 0.0–20.0 (×1/10) | ✓ | Number of times the garland animation cycles over the eff... |
| `E_CHOICE_Garlands_Direction` | Stack Direction | choice | Up | `Up`, `Down`, `Left`, `Right`, +4 more |  | Direction the garlands stack and move. The 'then' options... |

---

## Glediator

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_FILEPICKER_Glediator_Filename` | Glediator File | filepicker |  | — |  | Path to a Glediator (.gled), Jinx (.out), or CSV file con... |
| `E_CHOICE_Glediator_DurationTreatment` | Duration Treatment | choice | Normal | `Normal`, `Loop`, `Slow/Accelerate` |  | How to handle timing when the file length differs from th... |

---

## Kaleidoscope

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_CHOICE_Kaleidoscope_Type` | Kaleidoscope Type | choice | Triangle | `Triangle`, `Square`, `Square 2`, `6-Fold`, +3 more |  | Selects the symmetry pattern used for the kaleidoscope re... |
| `E_SLIDER_Kaleidoscope_X` | Center X | slider | 50 | 0–100 | ✓ | Horizontal position of the kaleidoscope center point as a... |
| `E_SLIDER_Kaleidoscope_Y` | Center Y | slider | 50 | 0–100 | ✓ | Vertical position of the kaleidoscope center point as a p... |
| `E_SLIDER_Kaleidoscope_Size` | Size | slider | 5 | 2–100 | ✓ | Controls the size of the base tile that gets reflected to... |
| `E_SLIDER_Kaleidoscope_Rotation` | Rotation | slider | 0 | 0–359 | ✓ | Rotates the entire kaleidoscope pattern around the center... |

---

## Life

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Life_Count` | Cells to start | slider | 50 | 0–100 |  | Percentage of the buffer cells that are initially alive. ... |
| `E_SLIDER_Life_Seed` | Type | slider | 0 | 0–4 |  | Selects the cellular automaton ruleset: 0=B3/S23 (classic... |
| `E_SLIDER_Life_Speed` | Speed | slider | 10 | 1–30 |  | Controls how fast generations advance. Higher values evol... |

---

## Lightning

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Number_Bolts` | Number of Segments | slider | 10 | 1–50 | ✓ | Number of zigzag segments that make up the lightning bolt... |
| `E_SLIDER_Number_Segments` | Width of Bolt | slider | 5 | 1–20 | ✓ | Controls the horizontal deviation of each zigzag segment.... |
| `E_CHECKBOX_ForkedLightning` | Forked Lightning | checkbox | false | — |  | When enabled, the bolt splits into a secondary fork partw... |
| `E_SLIDER_Lightning_TopX` | Top X Location | slider | 0 | -50–50 | ✓ | Horizontal offset of the bolt's starting point relative t... |
| `E_SLIDER_Lightning_TopY` | Top Y Location | slider | 0 | 0–100 | ✓ | Vertical offset of the bolt's starting point. For 'Up' di... |
| `E_SLIDER_Lightning_BOTX` | X Movement | slider | 0 | -50–50 |  | Causes the entire bolt to drift horizontally over time. P... |
| `E_SLIDER_Lightning_WIDTH` | Width | slider | 1 | 1–7 |  | Pixel thickness of each bolt segment line. Higher values ... |
| `E_CHOICE_Lightning_Direction` | Direction | choice | Up | `Up`, `Down` |  | Direction the lightning bolt extends. 'Up' draws from bot... |

---

## Lines

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Lines_Objects` | Lines | slider | 2 | 1–20 |  | Number of independent line objects drawn on the model. Ea... |
| `E_SLIDER_Lines_Segments` | Points | slider | 3 | 2–6 |  | Number of control points per line. Lines are drawn betwee... |
| `E_SLIDER_Lines_Thickness` | Thickness | slider | 1 | 1–10 | ✓ | Pixel width of each drawn line. Higher values produce thi... |
| `E_SLIDER_Lines_Speed` | Speed | slider | 1 | 1–10 | ✓ | How fast the line points move across the model. Points bo... |
| `E_SLIDER_Lines_Trails` | Trails | slider | 0 | 0–10 |  | Number of trailing afterimages left behind each line, cre... |
| `E_CHECKBOX_Lines_FadeTrails` | Fade Trails | checkbox | true | — |  | When enabled, older trail copies fade out progressively, ... |

---

## Liquid

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_CHECKBOX_TopBarrier` | Top Barrier | checkbox | false | — |  | Places a solid wall along the top edge of the model that ... |
| `E_CHECKBOX_BottomBarrier` | Bottom Barrier | checkbox | true | — |  | Places a solid wall along the bottom edge of the model th... |
| `E_CHECKBOX_LeftBarrier` | Left Barrier | checkbox | false | — |  | Places a solid wall along the left edge of the model that... |
| `E_CHECKBOX_RightBarrier` | Right Barrier | checkbox | false | — |  | Places a solid wall along the right edge of the model tha... |
| `E_CHECKBOX_HoldColor` | Hold Particle Color | checkbox | true | — |  | When enabled, particles keep the color they were assigned... |
| `E_CHECKBOX_MixColors` | Mix Colors | checkbox | false | — |  | When enabled, particles that touch each other blend their... |
| `E_CHOICE_ParticleType` | Type | choice | Elastic | `Powder`, `Elastic`, `Spring`, `Tensile`, +5 more |  | Selects the physics behavior of the particles. Each type ... |
| `E_SLIDER_LifeTime` | Lifetime | slider | 1000 | 0–1000 | ✓ | How long each particle lives before disappearing, in hund... |
| `E_SLIDER_Size` | Size | slider | 500 | 1–10000 |  | Radius of each particle in thousandths of a pixel. Larger... |
| `E_SLIDER_WarmUpFrames` | Warm Up Frames | slider | 0 | 0–500 |  | Number of simulation frames to run before the first visib... |
| `E_SLIDER_Despeckle` | Despeckle Threshold | slider | 0 | 0–4 |  | Fills in isolated black pixels surrounded by colored part... |
| `E_SLIDER_Liquid_Gravity` | Gravity | slider | 10.0 | -100.0–100.0 (×1/10) | ✓ | Strength of the gravitational force applied to particles.... |
| `E_SLIDER_Liquid_GravityAngle` | Gravity Angle | slider | 0 | 0–360 | ✓ | Direction of gravity in degrees. 0 pulls downward, 90 pul... |
| `E_SLIDER_X1` | X | slider | 50 | 0–100 | ✓ | Horizontal position of particle source 1 as a percentage ... |
| `E_SLIDER_Y1` | Y | slider | 100 | 0–100 | ✓ | Vertical position of particle source 1 as a percentage of... |
| `E_SLIDER_Direction1` | Direction | slider | 270 | 0–360 | ✓ | Angle in degrees at which particles are emitted from sour... |
| `E_SLIDER_Velocity1` | Velocity | slider | 100 | 0–1000 | ✓ | Initial speed of particles emitted from source 1. Higher ... |
| `E_SLIDER_Flow1` | Flow | slider | 100 | 0–1000 | ✓ | Number of new particles created per frame from source 1. ... |
| `E_SLIDER_Liquid_SourceSize1` | Source Size | slider | 0 | 0–100 | ✓ | Width of the emission area for source 1, spread perpendic... |
| `E_CHECKBOX_FlowMusic1` | Flow Matches Music | checkbox | false | — |  | When enabled, the particle flow rate from source 1 scales... |
| `E_CHECKBOX_Enabled2` | Enabled | checkbox | false | — |  | Enables particle source 2. When disabled, no particles ar... |
| `E_SLIDER_X2` | X | slider | 0 | 0–100 | ✓ | Horizontal position of particle source 2 as a percentage ... |
| `E_SLIDER_Y2` | Y | slider | 50 | 0–100 | ✓ | Vertical position of particle source 2 as a percentage of... |
| `E_SLIDER_Direction2` | Direction | slider | 0 | 0–360 | ✓ | Angle in degrees at which particles are emitted from sour... |
| `E_SLIDER_Velocity2` | Velocity | slider | 100 | 0–1000 | ✓ | Initial speed of particles emitted from source 2. Higher ... |
| `E_SLIDER_Flow2` | Flow | slider | 100 | 0–1000 | ✓ | Number of new particles created per frame from source 2. ... |
| `E_SLIDER_Liquid_SourceSize2` | Source Size | slider | 0 | 0–100 | ✓ | Width of the emission area for source 2, spread perpendic... |
| `E_CHECKBOX_FlowMusic2` | Flow Matches Music | checkbox | false | — |  | When enabled, the particle flow rate from source 2 scales... |
| `E_CHECKBOX_Enabled3` | Enabled | checkbox | false | — |  | Enables particle source 3. When disabled, no particles ar... |
| `E_SLIDER_X3` | X | slider | 50 | 0–100 | ✓ | Horizontal position of particle source 3 as a percentage ... |
| `E_SLIDER_Y3` | Y | slider | 0 | 0–100 | ✓ | Vertical position of particle source 3 as a percentage of... |
| `E_SLIDER_Direction3` | Direction | slider | 90 | 0–360 | ✓ | Angle in degrees at which particles are emitted from sour... |
| `E_SLIDER_Velocity3` | Velocity | slider | 100 | 0–1000 | ✓ | Initial speed of particles emitted from source 3. Higher ... |
| `E_SLIDER_Flow3` | Flow | slider | 100 | 0–1000 | ✓ | Number of new particles created per frame from source 3. ... |
| `E_SLIDER_Liquid_SourceSize3` | Source Size | slider | 0 | 0–100 | ✓ | Width of the emission area for source 3, spread perpendic... |
| `E_CHECKBOX_FlowMusic3` | Flow Matches Music | checkbox | false | — |  | When enabled, the particle flow rate from source 3 scales... |
| `E_CHECKBOX_Enabled4` | Enabled | checkbox | false | — |  | Enables particle source 4. When disabled, no particles ar... |
| `E_SLIDER_X4` | X | slider | 100 | 0–100 | ✓ | Horizontal position of particle source 4 as a percentage ... |
| `E_SLIDER_Y4` | Y | slider | 50 | 0–100 | ✓ | Vertical position of particle source 4 as a percentage of... |
| `E_SLIDER_Direction4` | Direction | slider | 180 | 0–360 | ✓ | Angle in degrees at which particles are emitted from sour... |
| `E_SLIDER_Velocity4` | Velocity | slider | 100 | 0–1000 | ✓ | Initial speed of particles emitted from source 4. Higher ... |
| `E_SLIDER_Flow4` | Flow | slider | 100 | 0–1000 | ✓ | Number of new particles created per frame from source 4. ... |
| `E_SLIDER_Liquid_SourceSize4` | Source Size | slider | 0 | 0–100 | ✓ | Width of the emission area for source 4, spread perpendic... |
| `E_CHECKBOX_FlowMusic4` | Flow Matches Music | checkbox | false | — |  | When enabled, the particle flow rate from source 4 scales... |

---

## Marquee

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Marquee_Band_Size` | Band Size | slider | 3 | 1–100 | ✓ | Number of consecutive lit pixels in each color band of th... |
| `E_SLIDER_Marquee_Skip_Size` | Skip Size | slider | 0 | 0–100 | ✓ | Number of unlit (dark) pixels between each color band. Ze... |
| `E_SLIDER_Marquee_Thickness` | Thickness | slider | 1 | 1–100 | ✓ | Number of concentric marquee rings drawn inward from the ... |
| `E_SLIDER_Marquee_Stagger` | Stagger | slider | 0 | 0–50 | ✓ | Offsets the starting position of each concentric ring so ... |
| `E_SLIDER_Marquee_Speed` | Speed | slider | 3 | 0–50 | ✓ | How fast the marquee pattern moves around the perimeter. ... |
| `E_SLIDER_Marquee_Start` | Start Pos | slider | 0 | 0–100 | ✓ | Initial offset position for the marquee pattern along the... |
| `E_CHECKBOX_Marquee_Reverse` | Reverse | checkbox | false | — |  | When enabled, the marquee pattern moves in the opposite d... |
| `E_SLIDER_Marquee_ScaleX` | Scale X | slider | 100 | 1–100 | ✓ | Scales the marquee rectangle width as a percentage. Value... |
| `E_SLIDER_Marquee_ScaleY` | Scale Y | slider | 100 | 1–100 | ✓ | Scales the marquee rectangle height as a percentage. Valu... |
| `E_CHECKBOX_Marquee_PixelOffsets` | Offsets In Pixels | checkbox | false | — |  | When enabled, the X and Y center offset values are interp... |
| `E_SLIDER_MarqueeXC` | X-axis Center | slider | 0 | -100–100 | ✓ | Horizontal offset of the marquee center. Shifts the entir... |
| `E_CHECKBOX_Marquee_WrapX` | Wrap X | checkbox | false | — |  | When enabled, pixels that move past the left or right edg... |
| `E_SLIDER_MarqueeYC` | Y-axis Center | slider | 0 | -100–100 | ✓ | Vertical offset of the marquee center. Shifts the entire ... |
| `E_CHECKBOX_Marquee_WrapY` | Wrap Y | checkbox | false | — |  | When enabled, pixels that move past the top or bottom edg... |

---

## Meteors

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_CHOICE_Meteors_Type` | Colors | choice | Rainbow | `Rainbow`, `Range`, `Palette` |  | Color scheme for the meteors. Rainbow uses random hues, R... |
| `E_CHOICE_Meteors_Effect` | Effect | choice | Down | `Down`, `Up`, `Left`, `Right`, +4 more |  | Direction of meteor movement. Down/Up/Left/Right move lin... |
| `E_SLIDER_Meteors_Count` | Count | slider | 10 | 1–100 | ✓ | Number of new meteors spawned per frame. Higher values cr... |
| `E_SLIDER_Meteors_Length` | Trail Length | slider | 25 | 1–100 | ✓ | Length of the fading trail behind each meteor. Higher val... |
| `E_SLIDER_Meteors_Swirl_Intensity` | Swirl Intensity | slider | 0 | 0–20 | ✓ | Adds a random sideways wobble to each meteor as it moves.... |
| `E_SLIDER_Meteors_Speed` | Speed | slider | 10 | 0–50 | ✓ | How fast the meteors travel across the model. Higher valu... |
| `E_SLIDER_Meteors_WamupFrames` | Warm up frames | slider | 0 | 0–100 |  | Number of simulation frames to run before the first visib... |
| `E_SLIDER_Meteors_XOffset` | Horizontal Offset | slider | 0 | -100–100 | ✓ | Shifts the center point horizontally for Implode and Expl... |
| `E_SLIDER_Meteors_YOffset` | Vertical Offset | slider | 0 | -100–100 | ✓ | Shifts the center point vertically for Implode and Explod... |
| `E_CHECKBOX_Meteors_UseMusic` | Adjust count based on music | checkbox | false | — |  | When enabled, the meteor count is scaled by the current m... |
| `E_CHECKBOX_FadeWithDistance` | Starfield simulation | checkbox | false | — |  | For Implode/Explode modes, meteors fade in brightness bas... |

---

## Morph

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Morph_Start_X1` | X1a | slider | 0 | 0–100 | ✓ | X coordinate of the first endpoint of the starting line (... |
| `E_SLIDER_Morph_Start_Y1` | Y1a | slider | 0 | 0–100 | ✓ | Y coordinate of the first endpoint of the starting line (... |
| `E_SLIDER_Morph_Start_X2` | X1b | slider | 100 | 0–100 | ✓ | X coordinate of the second endpoint of the starting line ... |
| `E_SLIDER_Morph_Start_Y2` | Y1b | slider | 0 | 0–100 | ✓ | Y coordinate of the second endpoint of the starting line ... |
| `E_SLIDER_MorphStartLength` | Head Length | slider | 1 | 0–100 | ✓ | Length of the colored head at the start of the morph. Thi... |
| `E_CHECKBOX_Morph_Start_Link` | Link Points | checkbox | false | — |  | When enabled, the second start point (X1b/Y1b) is locked ... |
| `E_SLIDER_Morph_End_X1` | X2a | slider | 0 | 0–100 | ✓ | X coordinate of the first endpoint of the ending line (si... |
| `E_SLIDER_Morph_End_Y1` | Y2a | slider | 100 | 0–100 | ✓ | Y coordinate of the first endpoint of the ending line (si... |
| `E_SLIDER_Morph_End_X2` | X2b | slider | 100 | 0–100 | ✓ | X coordinate of the second endpoint of the ending line (s... |
| `E_SLIDER_Morph_End_Y2` | Y2b | slider | 100 | 0–100 | ✓ | Y coordinate of the second endpoint of the ending line (s... |
| `E_SLIDER_MorphEndLength` | Head Length | slider | 1 | 0–100 | ✓ | Length of the colored head at the end of the morph. The h... |
| `E_CHECKBOX_Morph_End_Link` | Link Points | checkbox | false | — |  | When enabled, the second end point (X2b/Y2b) is locked to... |
| `E_SLIDER_MorphDuration` | Head Duration | slider | 20 | 0–100 | ✓ | Percentage of the effect duration during which the head i... |
| `E_SLIDER_MorphAccel` | Acceleration | slider | 0 | -10–10 | ✓ | Applies acceleration or deceleration to the morph movemen... |
| `E_SLIDER_Morph_Repeat_Count` | Repeat Count | slider | 0 | 0–250 | ✓ | Number of parallel copies of the morph drawn alongside th... |
| `E_SLIDER_Morph_Repeat_Skip` | Repeat Skip | slider | 1 | 1–100 | ✓ | Pixel spacing between each repeated morph copy. Higher va... |
| `E_SLIDER_Morph_Stagger` | Stagger | slider | 0 | -100–100 | ✓ | Time offset between repeated morph copies so they start a... |
| `E_CHECKBOX_ShowHeadAtStart` | Show Head at Start | checkbox | false | — |  | When enabled, the full head is visible at the starting po... |
| `E_CHECKBOX_Morph_AutoRepeat` | Auto Repeat | checkbox | false | — |  | Automatically calculates the repeat count needed to fill ... |
| `E_CUSTOM_Morph_QuickSet` | Quick Set | custom |  | — |  | Preset start/end point configurations (Full or Single Swe... |
| `E_CUSTOM_Morph_Swap` |  | custom |  | — |  | Swap the start and end X/Y coordinate values (and any act... |

---

## Off

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_CHOICE_Off_Style` | Off_Style | choice | Black | `Black`, `Transparent`, `Black -> Transparent`, `Transparent -> Black` |  | Controls how pixels are turned off. Black sets all pixels... |

---

## On

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Eff_On_Start` | Start Intensity | slider | 100 | 0–100 |  | Sets the brightness level at the beginning of the effect ... |
| `E_SLIDER_Eff_On_End` | End Intensity | slider | 100 | 0–100 |  | Sets the brightness level at the end of the effect as a p... |
| `E_SLIDER_On_Transparency` | Transparency | slider | 0 | 0–100 | ✓ | Sets the alpha transparency of the effect. At 0 the color... |
| `E_SLIDER_On_Cycles` | Cycle Count | slider | 1.0 | 0.0–100.0 (×1/10) |  | Number of times the start-to-end intensity ramp repeats o... |
| `E_CHECKBOX_On_Shimmer` | Shimmer | checkbox | false | — |  | When enabled, the effect alternates between the first and... |

---

## Pictures

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_CUSTOM_Pictures_FilenameBlock` |  | custom |  | — |  | Image file selection: Select / AI Generate / Clear button... |
| `E_CHOICE_Pictures_Direction` | Movement | choice | none | `none`, `left`, `right`, `up`, +19 more |  | Direction the image moves across the model. Includes scro... |
| `E_SLIDER_Pictures_Speed` | Movement Speed | slider | 1.0 | 0.0–20.0 (×1/10) |  | How fast the image moves in the chosen direction. Higher ... |
| `E_SLIDER_Pictures_FrameRateAdj` | Frame Rate Adj | slider | 1.0 | 0.0–20.0 (×1/10) |  | Multiplier for the playback speed of animated GIF frames.... |
| `E_CHECKBOX_Pictures_PixelOffsets` | Offsets In Pixels | checkbox | false | — |  | When enabled, the X and Y center offset values are treate... |
| `E_CHOICE_Scaling` | Scaling | choice | No Scaling | `No Scaling`, `Scale To Fit`, `Scale Keep Aspect Ratio`, `Scale Keep Aspect Ratio Crop` |  | How the image is resized to fit the model. No Scaling use... |
| `E_CHECKBOX_Pictures_Shimmer` | Shimmer | checkbox | false | — |  | When enabled, the image flickers on and off on alternatin... |
| `E_CHECKBOX_LoopGIF` | Loop Animated GIF | checkbox | false | — |  | When enabled, an animated GIF restarts from the first fra... |
| `E_CHECKBOX_SuppressGIFBackground` | Suppress GIF Background | checkbox | true | — |  | When enabled, the background color of an animated GIF is ... |
| `E_CUSTOM_Pictures_TransparentBlackRow` |  | custom |  | — |  | Transparent Black checkbox with an inline brightness thre... |
| `E_SLIDER_PicturesXC` | X-axis Center | slider | 0 | -100–100 | ✓ | Horizontal offset for the starting position of the image,... |
| `E_CHECKBOX_Pictures_WrapX` | Wrap X | checkbox | false | — |  | When enabled, the image wraps around horizontally so pixe... |
| `E_SLIDER_PicturesYC` | Y-axis Center | slider | 0 | -100–100 | ✓ | Vertical offset for the starting position of the image, a... |
| `E_SLIDER_PicturesEndXC` | X-axis Center | slider | 0 | -100–100 |  | Horizontal offset for the ending position of the image wh... |
| `E_SLIDER_PicturesEndYC` | Y-axis Center | slider | 0 | -100–100 |  | Vertical offset for the ending position of the image when... |
| `E_SLIDER_Pictures_StartScale` | Scaling | slider | 100 | 0–1000 |  | Scale factor for the image at the start of the effect, as... |
| `E_SLIDER_Pictures_EndScale` | Scaling | slider | 100 | 0–1000 |  | Scale factor for the image at the end of the effect. The ... |

---

## Pinwheel

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Pinwheel_Arms` | #Arms | slider | 3 | 1–20 |  | Number of colored arms radiating from the center of the p... |
| `E_SLIDER_Pinwheel_ArmSize` | Size | slider | 100 | 0–400 | ✓ | Length of each arm as a percentage of the maximum radius.... |
| `E_SLIDER_Pinwheel_Twist` | Twist | slider | 0 | -360–360 | ✓ | Degrees of curvature applied along each arm from center t... |
| `E_SLIDER_Pinwheel_Thickness` | Thick | slider | 0 | 0–100 | ✓ | Width of each arm as a percentage of the angular space be... |
| `E_SLIDER_Pinwheel_Speed` | Speed | slider | 10 | 0–50 | ✓ | Rotation speed of the pinwheel. Higher values make the ar... |
| `E_SLIDER_Pinwheel_Offset` | Offset | slider | 0 | 0–360 | ✓ | Starting angular offset in degrees for the pinwheel arms.... |
| `E_CHOICE_Pinwheel_Style` | Style | choice | Old Render Method | `Old Render Method`, `New Render Method` |  | Rendering algorithm to use. The new method uses ISPC-acce... |
| `E_CHECKBOX_Pinwheel_Rotation` | Rotation | checkbox | true | — |  | Sets the rotation direction. When checked, the pinwheel s... |
| `E_CHOICE_Pinwheel_3D` | 3D | choice | None | `None`, `3D`, `3D Inverted`, `Sweep` |  | Applies a brightness or alpha gradient across each arm to... |
| `E_SLIDER_PinwheelXC` | X-axis Center | slider | 0 | -100–100 | ✓ | Horizontal position of the pinwheel center as a percentag... |
| `E_SLIDER_PinwheelYC` | Y-axis center | slider | 0 | -100–100 | ✓ | Vertical position of the pinwheel center as a percentage ... |

---

## Plasma

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_CHOICE_Plasma_Color` | Color Choice | choice | Normal | `Normal`, `Preset Colors 1`, `Preset Colors 2`, `Preset Colors 3`, +1 more |  | Color scheme for the plasma pattern. Normal uses the effe... |
| `E_SLIDER_Plasma_Style` | Add Twist to Effect | slider | 1 | 1–10 |  | Selects the mathematical formula used to generate the pla... |
| `E_SLIDER_Plasma_Line_Density` | Line Density | slider | 1 | 1–10 |  | Controls how tightly packed the plasma wave lines are. Hi... |
| `E_SLIDER_Plasma_Speed` | Speed | slider | 10 | 0–100 | ✓ | How fast the plasma pattern animates and flows. Higher va... |

---

## Ripple

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_CHOICE_Ripple_Draw_Style` | Draw Style | choice | Old | `Old`, `Lines Inward`, `Lines Outward`, `Lines Both`, +15 more |  | Rendering style and direction for the ripple waves. Lines... |
| `E_CHOICE_Ripple_Object_To_Draw` | Object | choice | Circle | `Circle`, `Square`, `Triangle`, `Star`, +8 more |  | Shape of the ripple waves expanding from the center. Choo... |
| `E_CUSTOM_Ripple_SVG` | SVG | custom |  | — |  | Path to a simple SVG file whose outline is used as the ri... |
| `E_CHOICE_Ripple_Movement` | Movement | choice | Explode | `Explode`, `Implode`, `None` |  | Controls whether ripple waves expand outward (Explode), c... |
| `E_SLIDER_Ripple_Scale` | Scale | slider | 100 | 0–500 | ✓ | Overall size of the ripple pattern as a percentage. Value... |
| `E_SLIDER_Ripple_Outline` | Outline | slider | 1.0 | 0.0–10.0 (×1/10) | ✓ | Thickness of each ripple line. Higher values draw wider r... |
| `E_SLIDER_Ripple_Thickness` | Ripples | slider | 3 | 1–100 | ✓ | Number of concentric ripple rings displayed simultaneousl... |
| `E_SLIDER_Ripple_Spacing` | Spacing | slider | 1.0 | 0.1–40.0 (×1/10) | ✓ | Distance between consecutive ripple rings. Larger values ... |
| `E_SLIDER_Ripple_Cycles` | Cycle Cnt | slider | 1.0 | 0.0–30.0 (×1/10) | ✓ | Number of complete ripple animation cycles over the effec... |
| `E_SLIDER_RIPPLE_POINTS` | Points | slider | 5 | 3–8 |  | Number of points for star, polygon, and snowflake shapes.... |
| `E_SLIDER_Ripple_Rotation` | Rotation | slider | 0 | -360–360 | ✓ | Rotates the ripple shape by this many degrees. Useful for... |
| `E_SLIDER_Ripple_Twist` | Twist | slider | 0.0 | -45.0–45.0 (×1/10) | ✓ | Applies increasing rotation to each successive ripple rin... |
| `E_SLIDER_Ripple_XC` | X Center | slider | 0 | -100–100 | ✓ | Horizontal position of the ripple center as a percentage ... |
| `E_SLIDER_Ripple_YC` | Y Center | slider | 0 | -100–100 | ✓ | Vertical position of the ripple center as a percentage of... |
| `E_SLIDER_Ripple_Velocity` | Velocity | slider | 0.0 | 0.0–30.0 (×1/10) | ✓ | Speed at which the ripple center moves across the model i... |
| `E_SLIDER_Ripple_Direction` | Direction | slider | 0 | -360–360 | ✓ | Angle in degrees that the ripple center travels when velo... |
| `E_CHECKBOX_Ripple3D` | 3D | checkbox | false | — |  | When enabled, applies a brightness gradient to the ripple... |

---

## Servo

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_CHOICE_Channel` | Base Channel | choice |  | — |  | Selects which channel on the DMX model to control. The ch... |
| `E_CHECKBOX_16bit` | 16 bit | checkbox | true | — |  | When enabled, outputs a 16-bit value across two channels ... |
| `E_CHECKBOX_Timing_Track` | Use Timing Track | checkbox | false | — |  | When enabled, the servo position is driven by phoneme dat... |
| `E_CHOICE_Servo_TimingTrack` | Timing Track | choice |  | — |  | Selects which timing track to use for phoneme-driven serv... |
| `E_CUSTOM_Servo_StartEndRow` |  | custom |  | — |  | Start/End servo position sliders (0-100% as a float with ... |
| `E_CUSTOM_Servo_ButtonRow` |  | custom |  | — |  | Sync (mirrors Start and End values), Equal (copies Start ... |

---

## Shape

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_CHOICE_Shape_ObjectToDraw` | Object to Draw | choice | Circle | `Circle`, `Ellipse`, `Triangle`, `Square`, +13 more |  | The geometric shape, holiday object, emoji, or SVG to dra... |
| `E_CUSTOM_Shape_Font` | Character | custom |  | — |  | Font used for rendering emoji characters when Object to D... |
| `E_CUSTOM_Shape_Char` | Character Code | custom | 127876 | 32–917631 |  | Unicode code point of the emoji or character to display w... |
| `E_CUSTOM_Shape_SkinTone` | Skin Tone | custom | Default | `Default`, `Light`, `Medium Light`, `Medium`, +2 more |  | Skin tone modifier applied to emoji characters that suppo... |
| `E_CUSTOM_SVG` | SVG File | custom |  | — |  | Path to an SVG file to use as the shape when Object to Dr... |
| `E_SLIDER_Shape_Thickness` | Thickness | slider | 1 | 1–100 | ✓ | Line thickness used to draw the outline of each shape. Hi... |
| `E_SLIDER_Shape_Count` | Count | slider | 5 | 1–100 | ✓ | Number of shape instances spawned simultaneously on the m... |
| `E_SLIDER_Shape_StartSize` | Start Size | slider | 1 | 0–100 | ✓ | Initial size of each shape when it first appears. The sha... |
| `E_CHECKBOX_Shape_RandomInitial` | Random initial shape sizes | checkbox | true | — |  | When enabled, each shape starts at a random size and age ... |
| `E_SLIDER_Shapes_Velocity` | Velocity | slider | 0 | 0–20 | ✓ | Speed at which each shape moves across the model in the s... |
| `E_SLIDER_Shapes_Direction` | Direction | slider | 90 | 0–359 | ✓ | Angle in degrees that shapes travel when velocity is non-... |
| `E_SLIDER_Shape_Lifetime` | Lifetime | slider | 5 | 1–100 | ✓ | How long each shape lives as a percentage of the total ef... |
| `E_SLIDER_Shape_Growth` | Growth | slider | 10 | -100–100 | ✓ | Rate at which each shape changes size over its lifetime. ... |
| `E_SLIDER_Shape_CentreX` | X Center | slider | 50 | 0–100 | ✓ | Horizontal spawn position for shapes as a percentage of t... |
| `E_SLIDER_Shape_CentreY` | Y Center | slider | 50 | 0–100 | ✓ | Vertical spawn position for shapes as a percentage of the... |
| `E_SLIDER_Shape_Points` | Points | slider | 5 | 2–9 |  | Number of points on star shapes. Only applies when the Ob... |
| `E_SLIDER_Shape_Rotation` | Rotation | slider | 0 | 0–360 | ✓ | Rotation angle in degrees applied to each shape. Use a va... |
| `E_CHECKBOX_Shape_RandomLocation` | Random Location | checkbox | true | — |  | When enabled, each shape spawns at a random position on t... |
| `E_CHECKBOX_Shapes_RandomMovement` | Random movement | checkbox | false | — |  | When enabled, each shape gets a random velocity and direc... |
| `E_CHECKBOX_Shape_FadeAway` | Fade Away | checkbox | true | — |  | When enabled, shapes gradually become transparent as they... |
| `E_CHECKBOX_Shape_HoldColour` | Hold Color | checkbox | true | — |  | When enabled, each shape keeps the color it was assigned ... |
| `E_CHECKBOX_Shape_UseMusic` | Fire with music | checkbox | false | — |  | When enabled, new shapes are spawned in response to audio... |
| `E_SLIDER_Shape_Sensitivity` | Trigger level | slider | 50 | 0–100 |  | Audio volume threshold for triggering new shapes when Fir... |
| `E_CHECKBOX_Shape_FireTiming` | Fire with timing track | checkbox | false | — |  | When enabled, new shapes are spawned at each timing mark ... |
| `E_CHOICE_Shape_FireTimingTrack` | Timing Track | choice |  | — |  | Selects which timing track to use for triggering new shap... |
| `E_TEXT_Shape_FilterLabel` | Filter Label | text |  | — |  | Only timing marks whose label matches this text will trig... |
| `E_CHECKBOX_Shape_FilterReg` | Reg | checkbox | false | — |  | When enabled, the Filter Label is treated as a regular ex... |

---

## Shimmer

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Shimmer_Duty_Factor` | Duty Factor | slider | 50 | 1–100 | ✓ | Percentage of each cycle the color is visible before goin... |
| `E_SLIDER_Shimmer_Cycles` | Cycle Count | slider | 1.0 | 0.0–600.0 (×1/10) | ✓ | Number of on/off shimmer cycles over the duration of the ... |
| `E_CHECKBOX_Shimmer_Use_All_Colors` | Use All Colors | checkbox | false | — |  | When enabled, each pixel is assigned a random color from ... |
| `E_CHECKBOX_PRE_2017_7` | Pre v2017.7 Shimmer | checkbox | false | — |  | Uses the legacy shimmer rendering algorithm from before v... |

---

## Shockwave

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Shockwave_CenterX` | Center X | slider | 50 | 0–100 | ✓ | Horizontal center of the shockwave ring as a percentage o... |
| `E_SLIDER_Shockwave_CenterY` | Center Y | slider | 50 | 0–100 | ✓ | Vertical center of the shockwave ring as a percentage of ... |
| `E_SLIDER_Shockwave_Start_Radius` | Radius1 | slider | 1 | 0–750 | ✓ | Starting radius of the expanding ring at the beginning of... |
| `E_SLIDER_Shockwave_End_Radius` | Radius2 | slider | 10 | 0–750 | ✓ | Ending radius of the expanding ring at the end of each cy... |
| `E_SLIDER_Shockwave_Start_Width` | Width1 | slider | 5 | 0–255 | ✓ | Thickness of the ring band at the start of each cycle. |
| `E_SLIDER_Shockwave_End_Width` | Width2 | slider | 10 | 0–255 | ✓ | Thickness of the ring band at the end of each cycle. |
| `E_SLIDER_Shockwave_Accel` | Acceleration | slider | 0 | -10–10 |  | Adjusts the expansion speed curve. Positive values make t... |
| `E_SLIDER_Shockwave_Cycles` | Cycles | slider | 1 | 1–100 |  | Number of times the shockwave ring expands from Radius1 t... |
| `E_CHECKBOX_Shockwave_Blend_Edges` | Blend Edges | checkbox | true | — |  | When enabled, the ring edges fade out smoothly based on d... |
| `E_CHECKBOX_Shockwave_Scale` | Scale to Buffer | checkbox | true | — |  | When enabled, radius and width values are treated as perc... |

---

## SingleStrand

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_CHOICE_SingleStrand_Colors` | Colors | choice | Palette | `Rainbow`, `Palette` |  | Selects the color source for the chase. Palette uses the ... |
| `E_SLIDER_Number_Chases` | Number Chases | slider | 1 | 1–20 | ✓ | Number of simultaneous chase segments running across the ... |
| `E_SLIDER_Color_Mix1` | Chase Size | slider | 10 | 1–100 | ✓ | Length of each lit chase segment as a percentage of the t... |
| `E_SLIDER_Chase_Rotations` | Cycles | slider | 1.0 | 0.1–50.0 (×1/10) | ✓ | Number of complete chase traversals over the effect durat... |
| `E_SLIDER_Chase_Offset` | Offset | slider | 0.0 | -500.0–500.0 (×1/10) | ✓ | Shifts the starting position of the chase pattern along t... |
| `E_CHOICE_Chase_Type1` | Chase Types | choice | Left-Right | `Left-Right`, `Right-Left`, `Bounce from Left`, `Bounce from Right`, +11 more |  | Direction and movement pattern of the chase. Bounce types... |
| `E_CHOICE_Fade_Type` | Fade | choice | None | `None`, `From Head`, `From Tail`, `Head and Tail`, +1 more |  | Applies a brightness fade to the chase segment. 'From Hea... |
| `E_CHECKBOX_Chase_Group_All` | Group All Strands | checkbox | false | — |  | When enabled, treats all strands of the model as one cont... |
| `E_SLIDER_Skips_BandSize` | Band size | slider | 1 | 1–20 |  | Number of consecutive lit pixels in each colored band of ... |
| `E_SLIDER_Skips_SkipSize` | Skip size | slider | 1 | 0–20 |  | Number of unlit (dark) pixels between each colored band. ... |
| `E_SLIDER_Skips_StartPos` | Starting Position | slider | 1 | 1–20 |  | Pixel offset where the first band begins on the strand. |
| `E_SLIDER_Skips_Advance` | Number of Advances | slider | 0 | 0–100 |  | Number of times the skip pattern shifts position over the... |
| `E_CHOICE_Skips_Direction` | Direction | choice | Left | `Left`, `Right`, `From Middle`, `To Middle` |  | Direction in which the skip pattern is drawn. 'From Middl... |
| `E_CHOICE_SingleStrand_FX` | FX | choice | Blink | — |  | Selects which WS2812FX-style animation to run, such as Bl... |
| `E_CHOICE_SingleStrand_FX_Palette` | Palette | choice | Default | — |  | Selects the color palette mode used by the chosen FX anim... |
| `E_SLIDER_FX_Intensity` | Intensity | slider | 128 | 0–255 | ✓ | Controls the intensity parameter of the selected FX anima... |
| `E_SLIDER_FX_Speed` | Speed | slider | 128 | 0–255 | ✓ | Controls the speed of the selected FX animation. Higher v... |

---

## Sketch

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_CUSTOM_Sketch_Info` |  | custom |  | — |  | Explanatory text describing the Sketch effect plus links ... |
| `E_CUSTOM_Sketch_DefRow` |  | custom |  | — |  | Read-only display of the active sketch definition string.... |
| `E_CUSTOM_Sketch_BackgroundRow` |  | custom |  | — |  | Background image used as a tracing reference inside the E... |
| `E_SLIDER_SketchBackgroundOpacity` | Opacity | slider | 48 | 0–255 |  | Opacity (0-255) of the background tracing image when show... |
| `E_SLIDER_DrawPercentage` | Draw Percentage | slider | 40 | 0–100 | ✓ | Percentage of the effect duration over which the sketch p... |
| `E_SLIDER_Thickness` | Thickness | slider | 1 | 1–25 | ✓ | Line thickness in pixels used when drawing the sketch. |
| `E_CHECKBOX_MotionEnabled` | Motion | checkbox | false | — |  | When enabled, the sketch is fully drawn over the entire e... |
| `E_SLIDER_MotionPercentage` | Motion Percentage | slider | 100 | 1–100 | ✓ | When Motion is enabled, percentage of the sketch to rende... |

---

## Snowflakes

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Snowflakes_Count` | Max flakes | slider | 5 | 1–100 | ✓ | Maximum number of snowflakes visible on the buffer at the... |
| `E_SLIDER_Snowflakes_Type` | Type | slider | 1 | 0–9 |  | Selects the snowflake shape. 0 uses a random mix of all t... |
| `E_SLIDER_Snowflakes_Speed` | Speed | slider | 10 | 0–50 | ✓ | Controls how fast snowflakes move. In Driving mode this a... |
| `E_CHOICE_Falling` | Falling | choice | Driving | `Driving`, `Falling`, `Falling & Accumulating` |  | Selects the snowflake movement mode. 'Driving' scrolls fl... |
| `E_SLIDER_Snowflakes_WarmupFrames` | Warm up frames | slider | 0 | 0–100 |  | Number of simulation frames to run before the effect star... |

---

## Snowstorm

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Snowstorm_Count` | Max flakes | slider | 50 | 0–100 |  | Number of snowstorm particles wandering across the buffer... |
| `E_SLIDER_Snowstorm_Length` | Trail Length | slider | 50 | 0–100 |  | Maximum length of the fading trail behind each particle. ... |
| `E_SLIDER_Snowstorm_Speed` | Speed | slider | 10 | 1–50 |  | Controls how fast each particle moves and how quickly tra... |

---

## Spirals

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Spirals_Count` | Palette Rep | slider | 1 | 1–5 | ✓ | Number of times the full color palette is repeated across... |
| `E_SLIDER_Spirals_Rotation` | Spiral Wraps | slider | 2.0 | -30.0–30.0 (×1/10) | ✓ | Number of times each spiral arm wraps around the model fr... |
| `E_SLIDER_Spirals_Thickness` | Thickness | slider | 50 | 0–100 | ✓ | Width of each spiral arm as a percentage of the available... |
| `E_SLIDER_Spirals_Movement` | Movement | slider | 1.0 | -20.0–20.0 (×1/10) | ✓ | Speed and direction of the spiral rotation. Positive valu... |
| `E_CHECKBOX_Spirals_Blend` | Blend | checkbox | false | — |  | When enabled, blends all palette colors vertically across... |
| `E_CHECKBOX_Spirals_3D` | 3D | checkbox | false | — |  | When enabled, applies a brightness gradient across each s... |
| `E_CHECKBOX_Spirals_Grow` | Grow | checkbox | false | — |  | When enabled, the spiral arms gradually increase in thick... |
| `E_CHECKBOX_Spirals_Shrink` | Shrink | checkbox | false | — |  | When enabled, the spiral arms gradually decrease in thick... |

---

## Spirograph

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Spirograph_Speed` | Speed | slider | 10 | 0–50 | ✓ | Controls how fast the spirograph pattern rotates over tim... |
| `E_SLIDER_Spirograph_R` | R - Radius of outer circle | slider | 20 | 1–100 | ✓ | Radius of the fixed outer circle as a percentage of the b... |
| `E_SLIDER_Spirograph_r` | r - Radius of inner circle | slider | 10 | 1–100 | ✓ | Radius of the rolling inner circle as a percentage of the... |
| `E_SLIDER_Spirograph_d` | d - Distance | slider | 30 | 1–100 | ✓ | Distance of the drawing point from the center of the inne... |
| `E_SLIDER_Spirograph_Animate` | a - Animation | slider | 0 | -50–50 | ✓ | Gradually changes the distance parameter (d) over time, c... |
| `E_SLIDER_Spirograph_Length` | Length | slider | 20 | 0–50 | ✓ | How much of the spirograph curve is drawn each frame, mea... |
| `E_SLIDER_Spirograph_Width` | Width | slider | 1 | 1–50 | ✓ | Thickness of the drawn spirograph line in pixels. The lin... |

---

## Strobe

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Number_Strobes` | Number Strobes | slider | 3 | 1–300 |  | How many strobe flashes are active at the same time. High... |
| `E_SLIDER_Strobe_Duration` | Strobe Duration | slider | 10 | 1–100 |  | How many frames each strobe flash remains visible before ... |
| `E_SLIDER_Strobe_Type` | Strobe Type | slider | 1 | 1–4 |  | Shape of each strobe flash. Type 1 is a single pixel, typ... |
| `E_CHECKBOX_Strobe_Music` | Reacts to music | checkbox | false | — |  | When enabled, the number of active strobes scales with th... |

---

## Tendril

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_CHOICE_Tendril_Movement` | Movement | choice | Circle | `Random`, `Square`, `Circle`, `Horizontal Zig Zag`, +6 more |  | The path the tendril head follows. Options include geomet... |
| `E_SLIDER_Tendril_TuneMovement` | Tune Movement | slider | 10 | 0–20 | ✓ | Controls the magnitude of the tendril head movement. High... |
| `E_SLIDER_Tendril_Thickness` | Thickness | slider | 3 | 1–20 | ✓ | The line width of the tendril in pixels. Higher values dr... |
| `E_SLIDER_Tendril_Friction` | Friction | slider | 10 | 0–20 |  | Controls how quickly node velocity decays. Lower values a... |
| `E_SLIDER_Tendril_Dampening` | Dampening | slider | 10 | 0–20 |  | How much each node is influenced by the velocity of its p... |
| `E_SLIDER_Tendril_Tension` | Tension | slider | 20 | 0–39 |  | Controls how quickly the spring force decays along the te... |
| `E_SLIDER_Tendril_Trails` | Trails | slider | 1 | 1–20 |  | Number of parallel tendril strands drawn. Each trail has ... |
| `E_SLIDER_Tendril_Length` | Length | slider | 60 | 5–100 |  | Number of nodes in the tendril chain. More nodes create a... |
| `E_SLIDER_Tendril_Speed` | Speed | slider | 10 | 1–10 |  | How fast the tendril head moves along its chosen path. Hi... |
| `E_SLIDER_Tendril_XOffset` | Horizontal Offset | slider | 0 | -100–100 | ✓ | Shifts the entire tendril pattern left or right as a perc... |
| `E_SLIDER_Tendril_YOffset` | Vertical Offset | slider | 0 | -100–100 | ✓ | Shifts the entire tendril pattern up or down as a percent... |
| `E_SLIDER_Tendril_ManualX` | Manual X | slider | 0 | 0–100 | ✓ | Manually sets the horizontal target position for the tend... |
| `E_SLIDER_Tendril_ManualY` | Manual Y | slider | 0 | 0–100 | ✓ | Manually sets the vertical target position for the tendri... |

---

## Text

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_TEXT_Text` | Text | text |  | — |  | The text string to display. Supports multiple lines and s... |
| `E_CUSTOM_Text_File_Row` | From File | custom |  | — |  | Path to a text file whose contents are displayed instead ... |
| `E_CHOICE_Text_LyricTrack` | From Lyrics | choice |  | — |  | Selects a lyric timing track to use as the text source. T... |
| `E_FONTPICKER_Text_Font` | Font | fontpicker |  | — |  | The font face, size, and style used to render the text. |
| `E_CUSTOM_Text_Font_XL_Row` | XL Font | custom |  | — |  | Selects an xLights bitmap font (under fonts/) to use inst... |
| `E_CHOICE_Text_Dir` | Movement | choice | none | `none`, `left`, `right`, `up`, +10 more |  | Direction the text moves across the model. Options includ... |
| `E_CHECKBOX_TextToCenter` | Move to center | checkbox | false | — |  | When enabled, the text movement stops when the text reach... |
| `E_CHECKBOX_TextNoRepeat` | Do not repeat | checkbox | false | — |  | When enabled, the text scrolls through once and then stop... |
| `E_SLIDER_Text_Speed` | Speed | slider | 10 | 0–100 |  | How fast the text scrolls across the model. Higher values... |
| `E_CHOICE_Text_Effect` | Effect | choice | normal | `normal`, `vert text up`, `vert text down`, `rotate up 45`, +3 more |  | Text rendering style. Normal draws text horizontally; oth... |
| `E_CHOICE_Text_Count` | Count down | choice | none | `none`, `seconds`, `minutes seconds`, `to date 'd h m s'`, +4 more |  | Enables countdown mode. The text field value is used as t... |
| `E_CHECKBOX_Text_PixelOffsets` | Offsets In Pixels | checkbox | false | — |  | When enabled, the X and Y position values are interpreted... |
| `E_CHECKBOX_Text_Color_PerWord` | Color Per Word | checkbox | false | — |  | When enabled, each word in the text is drawn using a diff... |
| `E_SLIDER_Text_XStart` | X-axis Start | slider | 0 | -200–200 |  | Horizontal starting position of the text. Used as the ori... |
| `E_SLIDER_Text_YStart` | Y-axis Start | slider | 0 | -200–200 |  | Vertical starting position of the text. Used as the origi... |
| `E_SLIDER_Text_XEnd` | X-axis End | slider | 0 | -200–200 |  | Horizontal ending position for vector movement mode. The ... |
| `E_SLIDER_Text_YEnd` | Y-axis End | slider | 0 | -200–200 |  | Vertical ending position for vector movement mode. The te... |

---

## Tree

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Tree_Branches` | Number Branches | slider | 3 | 1–10 |  | Number of horizontal branch rows on the tree. The buffer ... |
| `E_SLIDER_Tree_Speed` | Speed | slider | 10 | 1–50 |  | How fast the garland lights sweep across each branch row.... |
| `E_CHECKBOX_Tree_ShowLights` | Show Tree Lights | checkbox | false | — |  | When enabled, displays additional twinkling Christmas lig... |

---

## Twinkle

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_Twinkle_Count` | Percent of Lights | slider | 3 | 2–100 | ✓ | Percentage of pixels that are actively twinkling at any g... |
| `E_SLIDER_Twinkle_Steps` | Twinkle Steps | slider | 30 | 2–400 | ✓ | Number of frames for a complete twinkle cycle (fade up th... |
| `E_CHOICE_Twinkle_Style` | Style | choice | Old Render Method | `Old Render Method`, `New Render Method` |  | Selects the rendering algorithm. Old Render Method uses t... |
| `E_CHECKBOX_Twinkle_Strobe` | Strobe | checkbox | false | — |  | When enabled, twinkling pixels snap on and off instantly ... |
| `E_CHECKBOX_Twinkle_ReRandom` | Re-Randomize after twinkle | checkbox | false | — |  | When enabled, each pixel is assigned a new random positio... |

---

## VU Meter

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_SLIDER_VUMeter_Bars` | Bars | slider | 6 | 1–100 |  | Number of bars or segments displayed in bar-based VU mete... |
| `E_CHOICE_VUMeter_Type` | Type | choice | Waveform | `Spectrogram`, `Spectrogram Peak`, `Spectrogram Line`, `Spectrogram Circle Line`, +41 more |  | The visualization style for the VU meter. Options include... |
| `E_CHOICE_VUMeter_TimingTrack` | Timing Track | choice |  | — |  | The timing track used for timing-event-based VU meter typ... |
| `E_TEXT_Filter` | Filter Label | text |  | — |  | Text filter applied to timing track labels. Only timing e... |
| `E_CHECKBOX_Regex` | Regex | checkbox | false | — |  | When enabled, the filter text is treated as a regular exp... |
| `E_SLIDER_VUMeter_Sensitivity` | Sensitivity | slider | 70 | 0–100 |  | Audio level threshold that must be exceeded to trigger th... |
| `E_SLIDER_VUMeter_Gain` | Gain | slider | 0 | -100–100 | ✓ | Amplifies or attenuates the audio signal level before it ... |
| `E_CHOICE_VUMeter_Shape` | Shape | choice | Circle | `Circle`, `Filled Circle`, `Square`, `Filled Square`, +15 more |  | The shape used for level-shape VU meter type. The shape i... |
| `E_FILEPICKER_SVGFile` | SVG File | filepicker |  | — |  | Path to an SVG file used as the shape when Shape is set t... |
| `E_CHECKBOX_VUMeter_SlowDownFalls` | Slow Down Falls | checkbox | true | — |  | When enabled, bars and levels fall gradually after a peak... |
| `E_SLIDER_VUMeter_StartNote` | Start Note | slider | 36 | 0–127 |  | The lowest MIDI note number included in frequency analysi... |
| `E_SLIDER_VUMeter_EndNote` | End Note | slider | 84 | 0–127 |  | The highest MIDI note number included in frequency analys... |
| `E_CHECKBOX_VUMeter_LogarithmicX` | Logarithmic X axis | checkbox | false | — |  | When enabled, the frequency axis uses a logarithmic scale... |
| `E_SLIDER_VUMeter_XOffset` | Horizontal Offset | slider | 0 | -100–100 | ✓ | Shifts the VU meter display left or right as a percentage... |
| `E_SLIDER_VUMeter_YOffset` | Vertical Offset | slider | 0 | -100–100 | ✓ | Shifts the VU meter display up or down as a percentage of... |
| `E_CHOICE_VUMeter_AudioTrack` | Audio Track | choice |  | — |  | Selects which audio track drives this VU Meter. 'Main' us... |

---

## Warp

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_CHOICE_Warp_Type` | Warp Type | choice | water drops | `water drops`, `dissolve`, `circle reveal`, `banded swirl`, +9 more |  | The distortion algorithm applied to pixels from lower lay... |
| `E_CHOICE_Warp_Treatment_APPLYLAST` | Treatment | choice | constant | `constant`, `in`, `out` |  | Controls how the warp intensity changes over the effect d... |
| `E_SLIDER_Warp_X` | X | slider | 50 | 0–100 | ✓ | Horizontal position of the warp center point or focal are... |
| `E_SLIDER_Warp_Y` | Y | slider | 50 | 0–100 | ✓ | Vertical position of the warp center point or focal area,... |
| `E_SLIDER_Warp_Cycle_Count` | Cycle Count | slider | 1 | 1–10 |  | Number of times the warp animation repeats over the effec... |
| `E_SLIDER_Warp_Speed` | Speed | slider | 20 | 0–40 |  | Controls the rate at which the warp distortion animates. ... |
| `E_SLIDER_Warp_Frequency` | Frequency | slider | 20 | 0–40 |  | Controls the spatial frequency of the distortion pattern.... |

---

## Wave

| Storage Name | Label | Type | Default | Range | Value Curve | Notes |
|---|---|---|---|---|---|---|
| `E_CHOICE_Wave_Type` | Wave Type | choice | Sine | `Sine`, `Triangle`, `Square`, `Decaying Sine`, +1 more |  | The waveform shape drawn across the model. Sine produces ... |
| `E_CHOICE_Fill_Colors` | Fill Colors | choice | None | `None`, `Rainbow`, `Palette` |  | How the area below the wave is filled. None leaves it emp... |
| `E_CHECKBOX_Mirror_Wave` | Mirror Wave | checkbox | false | — |  | When enabled, a mirrored copy of the wave is drawn on the... |
| `E_SLIDER_Number_Waves` | Number of Waves | slider | 2.5 | 0.5–10.0 (×1/360) | ✓ | Number of wave cycles drawn across the buffer width. 1.0 ... |
| `E_SLIDER_Thickness_Percentage` | Thickness of Wave | slider | 5 | 0–100 | ✓ | Vertical thickness of the wave line as a percentage of th... |
| `E_SLIDER_Wave_Height` | Scale Height of Wave | slider | 50 | 0–100 | ✓ | Scales the vertical amplitude of the wave as a percentage... |
| `E_SLIDER_Wave_Speed` | Speed | slider | 10.0 | 0.0–50.0 (×1/100) | ✓ | How fast the wave scrolls horizontally across the model. ... |
| `E_CHOICE_Wave_Direction` | Wave Direction | choice | Right to Left | `Right to Left`, `Left to Right` |  | The horizontal direction the wave scrolls. Right to Left ... |
| `E_SLIDER_Wave_YOffset` | Y Offset | slider | 0 | -250–250 | ✓ | Shifts the wave centerline up or down from the middle of ... |
