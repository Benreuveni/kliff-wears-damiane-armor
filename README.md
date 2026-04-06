# Kliff Wears Damiane Armor

A **Crimson Desert** mod that allows Kliff to equip Damiane-exclusive armor pieces. Designed for use alongside a Kliff-to-Damiane model swap mod — since Kliff's skeleton is replaced with Damiane's, her armor fits correctly but the game's equipment restriction system still blocks it. This mod removes that restriction.

## How It Works

Every armor item in `iteminfo.pabgb` contains a `prefab_data_list` with `tribe_gender_list` entries — u32 hashes that determine which character can equip the item. Damiane's armor only contains her tribe hashes, so the game marks it as "unequippable" for Kliff.

`build_armor_mod.py` parses the binary item database, identifies Damiane-exclusive player armor (items prefixed with `DamianOnly_`, `Damian_`, or `Demian_`), and generates a JSON patch file that replaces her tribe hashes with Kliff's equivalents.

The output is a **v1 absolute-offset JSON patch** compatible with the [Better JSON Mod Manager](https://www.nexusmods.com/crimsondesert/mods/6).

## Requirements

- Python 3.10+
- `lz4` (`pip install lz4`)
- Crimson Desert game installation (for the PAZ archives)

## Usage

### Generate the mod

```bash
python tools/build_armor_mod.py "C:\SteamLibrary\steamapps\common\Crimson Desert"
```

This outputs `mods/kliff_wears_damiane_armor.json`.

### Install

Copy `kliff_wears_damiane_armor.json` into the mod manager's `Mods/` folder and enable it.

### Additional flags

| Flag | Description |
|---|---|
| `--list` | List all patchable Damiane items with their internal names and display names |
| `--test <keyword>` | Patch only items matching `<keyword>` (e.g. `--test Plate`) for isolated testing |

### Diagnostic tool

`diagnose_fields.py` performs a field-level analysis of item restriction mechanisms across characters. Useful for investigating how the game enforces equipment restrictions.

```bash
python tools/diagnose_fields.py "C:\SteamLibrary\steamapps\common\Crimson Desert"
```

## Hash Mapping

| Damiane Hash | Kliff Hash |
|---|---|
| `0x26BE971F` | `0xFC66D914` |
| `0xF96C1DD4` | `0xBFA1F64B` |
| `0x8BF46446` | `0x13FB2B6E` |
| `0xABFCD791` | `0xD0A2E1EF` |
| `0x6CC4A721` | `0xFE7169E2` |

## Limitations

- Patches use absolute byte offsets (`v1` format), so they may need to be regenerated after game updates that modify `iteminfo.pabgb`.
- Only patches items with `DamianOnly_`, `Damian_`, or `Demian_` name prefixes. NPC items sharing Damiane's tribe hashes are intentionally excluded to prevent crashes.

## Acknowledgements

- **[potter420/crimson-rs](https://github.com/potter420/crimson-rs)** — Reverse-engineered `ItemInfo` binary schema (105 fields) that made the parser possible.
- **[NattKh/CRIMSON-DESERT-SAVE-EDITOR](https://github.com/NattKh/CRIMSON-DESERT-SAVE-EDITOR)** — Item database reference used during development.
- **[Better JSON Mod Manager](https://www.nexusmods.com/crimsondesert/mods/6)** — The mod manager this patch format targets.
