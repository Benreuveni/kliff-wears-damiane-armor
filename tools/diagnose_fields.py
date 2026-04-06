"""Diagnostic: Parse iteminfo fields to find character restriction mechanism.

Uses the exact binary schema from potter420/crimson-rs to parse item entries
and compare restriction-related fields across characters.

Requires only: lz4  (pip install lz4)

Usage:
    python diagnose_fields.py "C:\\SteamLibrary\\steamapps\\common\\Crimson Desert"

Output:
    ../refs/field_diagnostic.txt
"""

import os
import struct
import sys
from collections import defaultdict

import lz4.block

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paz_parse import parse_pamt, PazEntry


GAME_PAZ_FOLDER = "0008"

EQUIP_TYPE_NAMES = {
    0x750BE4D5: "Helm",
    0x9EFCCE6C: "Upperbody",
    0xD8434271: "Hand",
    0xCCEDA11E: "Foot",
    0x4A02EE45: "Cloak",
    0x8146C08C: "Earring",
    0x0275685F: "Necklace",
    0xA8EC88C6: "Ring",
    0x1E003A73: "Glass",
    0xF9946CC1: "Mask",
    0x6D4D3C83: "BackPack",
    0x983475F8: "Bracelet",
    0x166FD1CD: "HiddenEquip",
}

CHAR_PREFIXES = {
    "Kliff": ["Kliff_", "Old_Kliff_", "KliffOnly_"],
    "Damiane": ["Damian_", "DamianOnly_"],
    "Oongka": ["Oongka_"],
    "Yahn": ["Yahn_"],
}

ARMOR_KW = ["Armor", "Boots", "Gloves", "Cloak", "Helm", "Leather_",
            "Plate", "Chain_", "Iron_"]


# ── Binary primitives (matching crimson-rs BinaryRead) ──────────────────────

class ParseError(Exception):
    pass


class Reader:
    """Sequential binary reader with offset tracking."""

    __slots__ = ("data", "off")

    def __init__(self, data, off=0):
        self.data = data
        self.off = off

    def u8(self):
        v = self.data[self.off]
        self.off += 1
        return v

    def i8(self):
        v = struct.unpack_from('<b', self.data, self.off)[0]
        self.off += 1
        return v

    def u16(self):
        v = struct.unpack_from('<H', self.data, self.off)[0]
        self.off += 2
        return v

    def u32(self):
        v = struct.unpack_from('<I', self.data, self.off)[0]
        self.off += 4
        return v

    def i64(self):
        v = struct.unpack_from('<q', self.data, self.off)[0]
        self.off += 8
        return v

    def u64(self):
        v = struct.unpack_from('<Q', self.data, self.off)[0]
        self.off += 8
        return v

    def f32(self):
        v = struct.unpack_from('<f', self.data, self.off)[0]
        self.off += 4
        return v

    def f32x3(self):
        v = struct.unpack_from('<3f', self.data, self.off)
        self.off += 12
        return list(v)

    def u32x4(self):
        v = struct.unpack_from('<4I', self.data, self.off)
        self.off += 16
        return list(v)

    def cstring(self):
        n = self.u32()
        s = self.data[self.off:self.off + n].decode('utf-8', errors='replace')
        self.off += n
        return s

    def carray(self, read_fn):
        count = self.u32()
        return [read_fn() for _ in range(count)]

    def coptional(self, read_fn):
        present = self.u8()
        return read_fn() if present else None


# ── Struct readers (field order matches crimson-rs item.rs exactly) ──────────

def read_localizable_string(r: Reader):
    cat = r.u8()
    idx = r.u64()
    default = r.cstring()
    return {"category": cat, "index": idx, "default": default}


def read_occupied_equip_slot_data(r: Reader):
    key = r.u32()
    indices = r.carray(r.u8)
    return {"equip_slot_name_key": key, "equip_slot_name_index_list": indices}


def read_item_icon_data(r: Reader):
    icon_path = r.u32()
    check = r.u8()
    gimmick_states = r.carray(r.u32)
    return {"icon_path": icon_path, "check_exist_sealed_data": check,
            "gimmick_state_list": gimmick_states}


def read_passive_skill_level(r: Reader):
    return {"skill": r.u32(), "level": r.u32()}


def read_reserve_slot_target_data(r: Reader):
    return {"reserve_slot_info": r.u32(), "condition_info": r.u32()}


def read_sub_item(r: Reader):
    type_id = r.u8()
    if type_id in (0, 3, 9):
        value = r.u32()
    elif type_id == 14:
        value = None
    else:
        raise ParseError(f"unknown SubItem type: {type_id} at offset {r.off - 1}")
    return {"type_id": type_id, "value": value}


def read_drop_default_data(r: Reader):
    drop_enchant = r.u16()
    socket_items = r.carray(r.u32)
    add_socket_mats = r.carray(lambda: {"item": r.u32(), "value": r.u64()})
    default_sub = read_sub_item(r)
    socket_valid = r.u8()
    use_socket = r.u8()
    return {"drop_enchant_level": drop_enchant, "socket_item_list": socket_items,
            "add_socket_material_item_list": add_socket_mats,
            "default_sub_item": default_sub,
            "socket_valid_count": socket_valid, "use_socket": use_socket}


def read_sealable_item_info(r: Reader):
    tag = r.u8()
    item_key = r.u32()
    unk0 = r.u64()
    if tag in (0, 1, 3, 4):
        value = r.u32()
    elif tag == 2:
        value = r.cstring()
    else:
        raise ParseError(f"unknown SealableItemInfo type: {tag}")
    return {"type_tag": tag, "item_key": item_key, "unknown0": unk0, "value": value}


def read_enchant_stat_data(r: Reader):
    max_stats = r.carray(lambda: {"stat": r.u32(), "change_mb": r.i64()})
    regen_stats = r.carray(lambda: {"stat": r.u32(), "change_mb": r.i64()})
    static_stats = r.carray(lambda: {"stat": r.u32(), "change_mb": r.i64()})
    static_level = r.carray(lambda: {"stat": r.u32(), "change_mb": r.i8()})
    return {"max_stat_list": max_stats, "regen_stat_list": regen_stats,
            "stat_list_static": static_stats, "stat_list_static_level": static_level}


def read_price_floor(r: Reader):
    return {"price": r.u64(), "sym_no": r.u32(), "item_info_wrapper": r.u32()}


def read_enchant_data(r: Reader):
    level = r.u16()
    stat_data = read_enchant_stat_data(r)
    buy_prices = r.carray(lambda: {"key": r.u32(), "price": read_price_floor(r)})
    equip_buffs = r.carray(lambda: {"buff": r.u32(), "level": r.u32()})
    return {"level": level, "enchant_stat_data": stat_data,
            "buy_price_list": buy_prices, "equip_buffs": equip_buffs}


def read_prefab_data(r: Reader):
    names = r.carray(r.u32)
    slots = r.carray(r.u16)
    tribe_gender = r.carray(r.u32)
    craft = r.u8()
    return {"prefab_names": names, "equip_slot_list": slots,
            "tribe_gender_list": tribe_gender, "is_craft_material": craft}


def read_gimmick_visual_prefab_data(r: Reader):
    tag = r.u32()
    scale = r.f32x3()
    names = r.carray(r.u32)
    anims = r.carray(r.u32)
    use_gimmick = r.u8()
    return {"tag_name_hash": tag, "scale": scale, "prefab_names": names,
            "animation_path_list": anims, "use_gimmick_prefab": use_gimmick}


def read_docking_child_data(r: Reader):
    d = {}
    d["gimmick_info_key"] = r.u32()
    d["character_key"] = r.u32()
    d["item_key"] = r.u32()
    d["attach_parent_socket_name"] = r.cstring()
    d["attach_child_socket_name"] = r.cstring()
    d["docking_tag_name_hash"] = r.u32x4()
    d["docking_equip_slot_no"] = r.u16()
    d["spawn_distance_level"] = r.u32()
    d["is_item_equip_docking_gimmick"] = r.u8()
    d["send_damage_to_parent"] = r.u8()
    d["is_body_part"] = r.u8()
    d["docking_type"] = r.u8()
    d["is_summoner_team"] = r.u8()
    d["is_player_only"] = r.u8()
    d["is_npc_only"] = r.u32()
    d["is_sync_break_parent"] = r.u8()
    d["hit_part"] = r.u8()
    d["detected_by_npc"] = r.u8()
    d["is_bag_docking"] = r.u8()
    d["enable_collision"] = r.u8()
    d["disable_collision_with_other_gimmick"] = r.u8()
    d["docking_slot_key"] = r.cstring()
    return d


def read_game_event_execute_data(r: Reader):
    return {"game_event_type": r.u8(), "player_condition": r.u32(),
            "target_condition": r.u32(), "event_condition": r.u32()}


def read_inventory_change_data(r: Reader):
    return {"game_event_execute_data": read_game_event_execute_data(r),
            "to_inventory_info": r.u16()}


def read_page_data(r: Reader):
    return {"left_page_texture_path": r.cstring(),
            "right_page_texture_path": r.cstring(),
            "left_page_related_knowledge_info": r.u32(),
            "right_page_related_knowledge_info": r.u32()}


def read_inspect_data(r: Reader):
    d = {}
    d["item_info"] = r.u32()
    d["gimmick_info"] = r.u32()
    d["character_info"] = r.u32()
    d["spawn_reason_hash"] = r.u32()
    d["socket_name"] = r.cstring()
    d["speak_character_info"] = r.u32()
    d["inspect_target_tag"] = r.u32()
    d["reward_own_knowledge"] = r.u8()
    d["reward_knowledge_info"] = r.u32()
    d["item_desc"] = read_localizable_string(r)
    d["board_key"] = r.u32()
    d["inspect_action_type"] = r.u8()
    d["gimmick_state_name_hash"] = r.u32()
    d["target_page_index"] = r.u32()
    d["is_left_page"] = r.u8()
    d["target_page_related_knowledge_info"] = r.u32()
    d["enable_read_after_reward"] = r.u8()
    d["refer_to_left_page_inspect_data"] = r.u8()
    d["inspect_effect_info_key"] = r.u32()
    d["inspect_complete_effect_info_key"] = r.u32()
    return d


def read_inspect_action(r: Reader):
    return {"action_name_hash": r.u32(), "catch_tag_name_hash": r.u32(),
            "catcher_socket_name": r.cstring(),
            "catch_target_socket_name": r.cstring()}


def read_sharpness_data(r: Reader):
    return {"max_sharpness": r.u16(), "craft_tool_info": r.u16(),
            "stat_data": read_enchant_stat_data(r)}


def read_repair_data(r: Reader):
    return {"resource_item_info": r.u32(), "repair_value": r.u16(),
            "repair_style": r.u8(), "resource_item_count": r.u64()}


def read_unit_data(r: Reader):
    return {"ui_component": r.cstring(), "minimum": r.u32(),
            "icon_path": r.u32(),
            "item_name": read_localizable_string(r),
            "item_desc": read_localizable_string(r)}


def read_money_type_define(r: Reader):
    pfv = r.u64()
    entries = r.carray(lambda: {"key": r.u32(), "value": read_unit_data(r)})
    return {"price_floor_value": pfv, "unit_data_list_map": entries}


# ── Full ItemInfo reader (105 fields, exact order from item.rs) ─────────────

def read_item_info(r: Reader):
    it = {}
    it["key"] = r.u32()
    it["string_key"] = r.cstring()
    it["is_blocked"] = r.u8()
    it["max_stack_count"] = r.u64()
    it["item_name"] = read_localizable_string(r)
    it["broken_item_prefix_string"] = r.u32()
    it["inventory_info"] = r.u16()
    it["equip_type_info"] = r.u32()
    it["occupied_equip_slot_data_list"] = r.carray(
        lambda: read_occupied_equip_slot_data(r))
    it["item_tag_list"] = r.carray(r.u32)
    it["equipable_hash"] = r.u32()
    it["consumable_type_list"] = r.carray(r.u32)
    it["item_use_info_list"] = r.carray(r.u32)
    it["item_icon_list"] = r.carray(lambda: read_item_icon_data(r))
    it["map_icon_path"] = r.u32()
    it["money_icon_path"] = r.u32()
    it["use_map_icon_alert"] = r.u8()
    it["item_type"] = r.u8()
    it["material_key"] = r.u32()
    it["material_match_info"] = r.u32()
    it["item_desc"] = read_localizable_string(r)
    it["item_desc2"] = read_localizable_string(r)
    it["equipable_level"] = r.u32()
    it["category_info"] = r.u16()
    it["knowledge_info"] = r.u32()
    it["knowledge_obtain_type"] = r.u8()
    it["destroy_effec_info"] = r.u32()
    it["equip_passive_skill_list"] = r.carray(
        lambda: read_passive_skill_level(r))
    it["use_immediately"] = r.u8()
    it["apply_max_stack_cap"] = r.u8()
    it["extract_multi_change_info"] = r.u32()
    it["item_memo"] = r.cstring()
    it["filter_type"] = r.cstring()
    it["gimmick_info"] = r.u32()
    it["gimmick_tag_list"] = r.carray(r.cstring)
    it["max_drop_result_sub_item_count"] = r.u32()
    it["use_drop_set_target"] = r.u8()
    it["is_all_gimmick_sealable"] = r.u8()
    it["sealable_item_info_list"] = r.carray(lambda: read_sealable_item_info(r))
    it["sealable_character_info_list"] = r.carray(
        lambda: read_sealable_item_info(r))
    it["sealable_gimmick_info_list"] = r.carray(
        lambda: read_sealable_item_info(r))
    it["sealable_gimmick_tag_list"] = r.carray(
        lambda: read_sealable_item_info(r))
    it["sealable_tribe_info_list"] = r.carray(
        lambda: read_sealable_item_info(r))
    it["sealable_money_info_list"] = r.carray(r.u32)
    it["delete_by_gimmick_unlock"] = r.u8()
    it["gimmick_unlock_message_local_string_info"] = r.u32()
    it["can_disassemble"] = r.u8()
    it["transmutation_material_gimmick_list"] = r.carray(r.u32)
    it["transmutation_material_item_list"] = r.carray(r.u32)
    it["transmutation_material_item_group_list"] = r.carray(r.u16)
    it["is_register_trade_market"] = r.u8()
    it["multi_change_info_list"] = r.carray(r.u32)
    it["is_editor_usable"] = r.u8()
    it["discardable"] = r.u8()
    it["is_dyeable"] = r.u8()
    it["is_editable_grime"] = r.u8()
    it["is_destroy_when_broken"] = r.u8()
    it["quick_slot_index"] = r.u8()
    it["reserve_slot_target_data_list"] = r.carray(
        lambda: read_reserve_slot_target_data(r))
    it["item_tier"] = r.u8()
    it["is_important_item"] = r.u8()
    it["apply_drop_stat_type"] = r.u8()
    it["drop_default_data"] = read_drop_default_data(r)
    it["prefab_data_list"] = r.carray(lambda: read_prefab_data(r))
    it["enchant_data_list"] = r.carray(lambda: read_enchant_data(r))
    it["gimmick_visual_prefab_data_list"] = r.carray(
        lambda: read_gimmick_visual_prefab_data(r))
    it["price_list"] = r.carray(
        lambda: {"key": r.u32(), "price": read_price_floor(r)})
    it["docking_child_data"] = r.coptional(lambda: read_docking_child_data(r))
    it["inventory_change_data"] = r.coptional(
        lambda: read_inventory_change_data(r))
    it["unk_texture_path"] = r.cstring()
    it["fixed_page_data_list"] = r.carray(lambda: read_page_data(r))
    it["dynamic_page_data_list"] = r.carray(lambda: read_page_data(r))
    it["inspect_data_list"] = r.carray(lambda: read_inspect_data(r))
    it["inspect_action"] = read_inspect_action(r)
    it["default_sub_item"] = read_sub_item(r)
    it["cooltime"] = r.i64()
    it["item_charge_type"] = r.u8()
    it["sharpness_data"] = read_sharpness_data(r)
    it["max_charged_useable_count"] = r.u32()
    it["hackable_character_group_info_list"] = r.carray(r.u16)
    it["item_group_info_list"] = r.carray(r.u16)
    it["discard_offset_y"] = r.f32()
    it["hide_from_inventory_on_pop_item"] = r.u8()
    it["is_shield_item"] = r.u8()
    it["is_tower_shield_item"] = r.u8()
    it["is_wild"] = r.u8()
    it["packed_item_info"] = r.u32()
    it["unpacked_item_info"] = r.u32()
    it["convert_item_info_by_drop_npc"] = r.u32()
    it["look_detail_game_advice_info_wrapper"] = r.u32()
    it["look_detail_mission_info"] = r.u32()
    it["enable_alert_system_to_ui"] = r.u8()
    it["usable_alert"] = r.u8()
    it["is_save_game_data_at_use_item"] = r.u8()
    it["is_logout_at_use_item"] = r.u8()
    it["shared_cool_time_group_name_hash"] = r.u32()
    it["item_bundle_data_list"] = r.carray(
        lambda: {"count_mb": r.u64(), "key": r.u32()})
    it["money_type_define"] = r.coptional(lambda: read_money_type_define(r))
    it["emoji_texture_id"] = r.cstring()
    it["enable_equip_in_clone_actor"] = r.u8()
    it["is_blocked_store_sell"] = r.u8()
    it["is_preorder_item"] = r.u8()
    it["respawn_time_seconds"] = r.i64()
    it["max_endurance"] = r.u16()
    it["repair_data_list"] = r.carray(lambda: read_repair_data(r))
    return it


# ── Extraction helpers ──────────────────────────────────────────────────────

def find_entry(entries, name):
    matches = [e for e in entries if name.lower() in e.path.lower()]
    exact = [e for e in matches
             if os.path.basename(e.path).lower() == name.lower()]
    return exact[0] if exact else (matches[0] if len(matches) == 1 else None)


def extract_raw(entry):
    read_size = entry.comp_size if entry.compressed else entry.orig_size
    with open(entry.paz_file, 'rb') as f:
        f.seek(entry.offset)
        data = f.read(read_size)
    if entry.compressed and entry.compression_type == 2:
        data = lz4.block.decompress(data, uncompressed_size=entry.orig_size)
    return data


def classify(name):
    for char, prefixes in CHAR_PREFIXES.items():
        for prefix in prefixes:
            if name.startswith(prefix):
                return char
    return "Other"


def is_armor(name):
    return any(kw in name for kw in ARMOR_KW)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python diagnose_fields.py <game_dir>")
        sys.exit(1)

    game_dir = sys.argv[1]
    paz_dir = os.path.join(game_dir, GAME_PAZ_FOLDER)
    pamt_path = os.path.join(paz_dir, "0.pamt")

    report = []
    def out(s=""):
        report.append(s)
        print(s)

    out("=" * 70)
    out("FIELD-LEVEL ITEM DIAGNOSTIC")
    out("Schema: potter420/crimson-rs ItemInfo (105 fields)")
    out("=" * 70)

    out("\n[1] Parsing PAMT index...")
    entries = parse_pamt(pamt_path, paz_dir=paz_dir)

    out("[2] Extracting iteminfo...")
    body = extract_raw(find_entry(entries, "iteminfo.pabgb"))
    header = extract_raw(find_entry(entries, "iteminfo.pabgh"))
    out(f"    Body: {len(body):,} bytes, Header: {len(header):,} bytes")

    item_count = struct.unpack_from('<H', header, 0)[0]
    out(f"    Header says {item_count} entries")

    out("\n[3] Parsing all items sequentially...")
    r = Reader(body)
    items = []
    errors = 0
    for i in range(item_count):
        start = r.off
        try:
            it = read_item_info(r)
            it["_start_off"] = start
            it["_end_off"] = r.off
            items.append(it)
        except Exception as e:
            errors += 1
            if errors <= 3:
                out(f"    ERROR at item #{i} offset 0x{start:X}: {e}")
            if errors == 3:
                out("    (suppressing further errors)")
            # Try to recover using header offset table
            if i + 1 < item_count:
                next_off = struct.unpack_from('<I', header, 2 + (i + 1) * 8 + 4)[0]
                r.off = next_off
            else:
                break

    out(f"    Successfully parsed: {len(items)} items ({errors} errors)")

    # Classify items
    char_armor = defaultdict(list)
    for it in items:
        name = it["string_key"]
        char = classify(name)
        etype = it["equip_type_info"]
        etype_name = EQUIP_TYPE_NAMES.get(etype, "")
        if char != "Other" and (is_armor(name) or etype_name):
            char_armor[char].append(it)
        elif char == "Other" and etype_name and is_armor(name) and \
                not name.startswith("CraftingRecipe_"):
            char_armor["Generic"].append(it)

    # ── Section 4: Dump fields ──
    out("\n" + "=" * 70)
    out("[4] RESTRICTION-RELATED FIELDS FOR CHARACTER ARMOR")
    out("=" * 70)

    for char in ["Kliff", "Damiane", "Oongka"]:
        items_list = sorted(char_armor.get(char, []),
                            key=lambda x: x["string_key"])
        out(f"\n  --- {char} ({len(items_list)} items) ---")
        for it in items_list:
            name = it["string_key"]
            etype = it["equip_type_info"]
            etype_name = EQUIP_TYPE_NAMES.get(etype, f"0x{etype:08X}")
            out(f"\n    {name} (key={it['key']}, type={etype_name}):")
            out(f"      equipable_hash:       0x{it['equipable_hash']:08X}")
            out(f"      equipable_level:      {it['equipable_level']}")
            out(f"      category_info:        {it['category_info']}")
            out(f"      item_type:            {it['item_type']}")
            out(f"      item_tier:            {it['item_tier']}")
            out(f"      filter_type:          {it['filter_type']!r}")

            tags = it.get("item_tag_list", [])
            out(f"      item_tag_list:        "
                f"[{', '.join(f'0x{t:08X}' for t in tags)}]")

            occ = it.get("occupied_equip_slot_data_list", [])
            out(f"      occupied_equip_slots: {len(occ)} entries")
            for j, slot in enumerate(occ):
                out(f"        [{j}] key=0x{slot['equip_slot_name_key']:08X}, "
                    f"indices={slot['equip_slot_name_index_list']}")

            hcg = it.get("hackable_character_group_info_list", [])
            out(f"      hackable_char_groups: {hcg}")

            ig = it.get("item_group_info_list", [])
            out(f"      item_group_info_list: {ig}")

            prefabs = it.get("prefab_data_list", [])
            out(f"      prefab_data_list:     {len(prefabs)} entries")
            for j, pf in enumerate(prefabs):
                tg = [f"0x{t:08X}" for t in pf["tribe_gender_list"]]
                out(f"        [{j}] slots={pf['equip_slot_list']}, "
                    f"tribe_gender={tg}")

    # ── Section 5: Cross-character comparison ──
    out("\n" + "=" * 70)
    out("[5] CROSS-CHARACTER FIELD COMPARISON")
    out("=" * 70)

    for field in ["equipable_hash", "category_info", "item_type",
                  "item_tier", "filter_type"]:
        out(f"\n  Field: {field}")
        for char in ["Kliff", "Damiane", "Oongka", "Generic"]:
            vals = set()
            for it in char_armor.get(char, []):
                v = it[field]
                if isinstance(v, int) and field == "equipable_hash":
                    vals.add(f"0x{v:08X}")
                else:
                    vals.add(str(v))
            if vals:
                out(f"    {char:10s}: {sorted(vals)}")

    out(f"\n  Field: occupied_equip_slot keys (unique)")
    for char in ["Kliff", "Damiane", "Oongka", "Generic"]:
        keys = set()
        for it in char_armor.get(char, []):
            for s in it.get("occupied_equip_slot_data_list", []):
                keys.add(f"0x{s['equip_slot_name_key']:08X}")
        if keys:
            out(f"    {char:10s}: {sorted(keys)}")

    out(f"\n  Field: item_tag_list (unique tags)")
    for char in ["Kliff", "Damiane", "Oongka", "Generic"]:
        tags = set()
        for it in char_armor.get(char, []):
            for t in it.get("item_tag_list", []):
                tags.add(f"0x{t:08X}")
        if tags:
            out(f"    {char:10s}: {sorted(tags)}")

    out(f"\n  Field: hackable_character_group_info_list (unique)")
    for char in ["Kliff", "Damiane", "Oongka", "Generic"]:
        vals = set()
        for it in char_armor.get(char, []):
            for v in it.get("hackable_character_group_info_list", []):
                vals.add(v)
        if vals:
            out(f"    {char:10s}: {sorted(vals)}")

    out(f"\n  Field: prefab tribe_gender_list (unique hashes)")
    for char in ["Kliff", "Damiane", "Oongka", "Generic"]:
        vals = set()
        for it in char_armor.get(char, []):
            for pf in it.get("prefab_data_list", []):
                for v in pf.get("tribe_gender_list", []):
                    vals.add(f"0x{v:08X}")
        if vals:
            out(f"    {char:10s}: {sorted(vals)}")

    # ── Section 6: Generic samples ──
    out("\n" + "=" * 70)
    out("[6] GENERIC ARMOR SAMPLES (first 5)")
    out("=" * 70)
    for it in char_armor.get("Generic", [])[:5]:
        name = it["string_key"]
        etype = EQUIP_TYPE_NAMES.get(it["equip_type_info"], "?")
        out(f"\n    {name} (key={it['key']}, type={etype}):")
        out(f"      equipable_hash:  0x{it['equipable_hash']:08X}")
        out(f"      category_info:   {it['category_info']}")
        tags = it.get("item_tag_list", [])
        out(f"      item_tag_list:   [{', '.join(f'0x{t:08X}' for t in tags)}]")
        for j, pf in enumerate(it.get("prefab_data_list", [])):
            tg = [f"0x{t:08X}" for t in pf["tribe_gender_list"]]
            out(f"      prefab[{j}]: tribe_gender={tg}")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "refs", "field_diagnostic.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    out(f"\n{'=' * 70}")
    out(f"Report saved to: {out_path}")


if __name__ == "__main__":
    main()
