# ASCII styles as chance pulls

Two independent layers on every card:

1. **Card rarity sets the character count** (one grid per tier; every style prints exactly the same count on a given tier).
2. **The copy's code rolls a style**, exactly like the app's chance variants (`fxForCode`): `roll(fnv("fx:" + code) / 2^32)`.
   Plain Bone ASCII is the default (96.9% of copies); the 12 styles share the other 3.1%.

The odds and value multipliers are the app's own `FX_VAR` numbers, so pack prices, EV and the economy are unchanged.
Only the names and the look change (the left column is the existing key in the app).

| App key | Style | Engine | Palette | Odds | Value |
|---|---|---|---|---|---|
| (none) | Bone | brightness ramp | bone | default | x1 |
| steel | Phosphor | ramp | terminal green | 1 in 167 | x3 |
| dots | Amber | ramp | terminal amber | 1 in 200 | x3 |
| vhs | Glitch | ramp + VHS tear | violet | 1 in 250 | x3.5 |
| scratch | Typeset | the figure typeset from its caption | bone | 1 in 250 | x3.5 |
| ice | Stipple | braille dots | blue | 1 in 400 | x5 |
| chain | Linework | outline strokes | bone | 1 in 400 | x5 |
| wire | Pixel | half-block pixels | acid green | 1 in 500 | x6 |
| print | Blood | ramp | blood red | 1 in 500 | x6 |
| glass | Glow | ramp, duotone | magenta | 1 in 1,000 | x10 |
| blood | Toxic Glitch | ramp + VHS tear | toxic green | 1 in 1,000 | x10 |
| leaf | Iridescent | ramp, per-character colour | oil slick | 1 in 1,667 | x15 |
| kin | Dissolve | smooth top dissolving into pixels | blue | 1 in 3,333 | x25 |

`styles.json` has the machine-readable table and a 400,000-copy simulation of the roll (observed vs target for each style).

Known limits
- Dissolve's top part is a smooth image, not characters, so on that style the count only describes the lower half.
- On a very coarse grid (about 2,800 characters) all 13 still read, but Pixel and Dissolve look like pixel art, not text.
- Not wired into the app yet: the app still draws its old overlays. Wiring it means swapping the 12 overlay names and rendering each fighter in each style.
