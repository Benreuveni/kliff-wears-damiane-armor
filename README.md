# Kliff Wears Damiane Armor

A **Crimson Desert** mod that allows Kliff to equip Damiane-exclusive armor pieces. Designed for use alongside a Kliff-to-Damiane model swap mod — since Kliff's skeleton is replaced with Damiane's, her armor fits correctly but the game's equipment restriction system still blocks it. This mod removes that restriction.

Covers **plate**, **leather**, and **fabric** armor categories (~40 items total).

## How It Works

Every armor item in `iteminfo.pabgb` contains a `prefab_data_list` with `tribe_gender_list` entries — u32 hashes that determine which character can equip the item. Damiane's armor only contains her tribe hashes, so the game marks it as "unequippable" for Kliff.

`build_armor_mod.py` parses the binary item database, identifies Damiane-exclusive player armor (items prefixed with `DamianOnly_`, `Damian_`, or `Demian_`), and generates a JSON patch file that replaces her tribe hashes with Kliff's equivalents.

The output is a **v1 absolute-offset JSON patch** compatible with the [Better JSON Mod Manager](https://www.nexusmods.com/crimsondesert/mods/6).

## Requirements

- Python 3.10+
- `lz4` (`pip install lz4`)
- Crimson Desert game installation (for the PAZ archives)

## Usage

### Generate the mod (recommended)

```bash
python tools/build_armor_mod.py "C:\SteamLibrary\steamapps\common\Crimson Desert" --build-combined
```

This outputs a single `mods/kliff_wears_damiane_armor.json` containing patches for all supported armor types (plate + leather + fabric).

### Install

Copy `kliff_wears_damiane_armor.json` into the mod manager's `Mods/` folder and enable it.

### Build modes

| Command | Description |
|---|---|
| `--build-combined` | **Recommended.** Single file with plate + leather + fabric |
| `--build-split` | Separate files per category (for debugging or if combined crashes) |
| `--types plate` | Build only plate armor (the safest, most-tested subset) |
| `--types plate,leather` | Build specific categories |
| `--list` | Preview all patchable items with categories and hash counts |

### Debugging flags

| Flag | Description |
|---|---|
| `--test <keyword>` | Patch only items matching `<keyword>` (e.g. `--test Plate`, `--test Leather`) |
| `--max-items N` | Limit to the first N matching items |
| `--skip-items N` | Skip the first N matching items |
| `--allow-items 1,2,5` | Include only specific item numbers (from the numbered list) |
| `--output <name>` | Custom output filename (without `.json`) |

### Diagnostic tool

`diagnose_fields.py` performs a field-level analysis of item restriction mechanisms across characters.

```bash
python tools/diagnose_fields.py "C:\SteamLibrary\steamapps\common\Crimson Desert"
```

## Armor Categories

| Category | Items | Patches | Keywords |
|---|---|---|---|
| Plate | 23 | 92 | `PlateArmor`, `Plate_Boots`, `Pure_White_Plate` |
| Leather | 17 | ~68 | `Leather_Armor`, `Leather_Boots`, `Leather_Cloak`, `Leather_Gloves` |
| Fabric | varies | varies | `Fabric_Armor`, `Fabric_Cloak`, `Skirt_Fabric`, `Greyfur_Fabric` |

## Hash Mapping

| Damiane Hash | Kliff Hash |
|---|---|
| `0x26BE971F` | `0xFC66D914` |
| `0xF96C1DD4` | `0xBFA1F64B` |
| `0x8BF46446` | `0x13FB2B6E` |
| `0xABFCD791` | `0xD0A2E1EF` |
| `0x6CC4A721` | `0xFE7169E2` |

## Troubleshooting & Known Issues

### Why `--build-combined` instead of patching everything at once?

The initial version of this mod tried to patch all Damiane armor items in a single pass. This generated 200+ patches and crashed the game on startup. Through extensive testing, we discovered several issues:

#### 1. NPC items cause crashes

Many items share Damiane's `tribe_gender_list` hashes but belong to NPCs, faction members, or cutscene characters (e.g. items with `Demeniss`, `Uniform`, `_Npc` in their names). Patching these crashes the game. The mod now filters these out using `NPC_INDICATORS`.

#### 2. One specific item is incompatible

`Demian_Leather_Gloves_II` causes a crash-to-desktop even when patched in complete isolation (a single 5-patch mod with just this item). It's permanently excluded. Likely referenced by an NPC or cutscene internally despite having a player-style name.

#### 3. Certain leather item combinations crash in a single mod file

This was the most puzzling issue. Through binary search testing:

- **Plate** (23 items, 92 patches, offsets `0x379352–0x382403`): works in one file
- **Leather** (18 items, 76 patches, offsets `0x3413F8–0x34A8A1`): crashes in one file
- **Leather items 1–12** (50 patches): works
- **Leather items 13–17** (21 patches): works alone
- **Leather items 1–12 + any item from 13–17**: crashes in the same file

Every subset of leather items worked independently, but combining items from the first group (1–12) with items from the second group (13–17) in a **single mod file** always crashed — even though their patches don't overlap.

The root cause is unclear. Possible explanations:
- The mod loader has an internal limitation when patches span certain offset ranges within a single file
- A compression chunk boundary falls between the two groups, and the mod loader mishandles cross-chunk patches in a single mod
- Some undocumented interaction between the mod loader's patch application strategy and the binary layout

**The workaround**: splitting patches into separate mod files. The mod manager applies each file's patches independently, which avoids whatever internal conflict occurs when they're combined. The `--build-combined` mode merges plate + fabric + leather(1–12) into one file (since these work together), while `--build-split` generates separate files per category.

If `--build-combined` crashes with your mod setup, try `--build-split` and enable the files individually to isolate conflicts with other mods.

## Limitations

- Patches use absolute byte offsets (`v1` format), so they must be regenerated after game updates that modify `iteminfo.pabgb`.
- NPC items sharing Damiane's tribe hashes are intentionally excluded to prevent crashes.
- `Demian_Leather_Gloves_II` is excluded (crashes in isolation).
- Leather items 13–17 are only included in `--build-split` mode, not in `--build-combined`, due to the single-file crash issue described above.

## Acknowledgements

- **[potter420/crimson-rs](https://github.com/potter420/crimson-rs)** — Reverse-engineered `ItemInfo` binary schema (105 fields) that made the parser possible.
- **[NattKh/CRIMSON-DESERT-SAVE-EDITOR](https://github.com/NattKh/CRIMSON-DESERT-SAVE-EDITOR)** — Item database reference used during development.
- **[Better JSON Mod Manager](https://www.nexusmods.com/crimsondesert/mods/6)** — The mod manager this patch format targets.
