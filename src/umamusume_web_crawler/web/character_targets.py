"""Character/costume targets shared by Bwiki download workflows."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CHARACTERS_JSON = "umamusume_characters.json"


@dataclass(frozen=True)
class CharacterAssetTarget:
    page_title: str
    name_cn: str
    name_en: str
    character_id: str | None = None
    costume_id: str | None = None
    is_base: bool = True


def load_asset_targets_from_json(
    json_path: str | Path, *, include_variants: bool = False
) -> list[CharacterAssetTarget]:
    path = Path(json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("characters"), list):
        targets: list[CharacterAssetTarget] = []
        for item in data["characters"]:
            if not isinstance(item, dict) or not item.get("implemented"):
                continue
            name_cn = str(item.get("name_cn") or "").strip()
            name_en = str(item.get("name_en") or "").strip()
            page_title = str(item.get("wiki_title") or name_cn).strip()
            character_id = str(item.get("id") or "").strip() or None
            variants = item.get("variants")
            if include_variants and isinstance(variants, list):
                for variant in variants:
                    if not isinstance(variant, dict):
                        continue
                    variant_title = str(variant.get("wiki_title") or "").strip()
                    if not variant_title:
                        continue
                    targets.append(
                        CharacterAssetTarget(
                            page_title=variant_title,
                            name_cn=name_cn,
                            name_en=name_en,
                            character_id=character_id,
                            costume_id=str(variant.get("costume_id") or "").strip()
                            or None,
                            is_base=bool(variant.get("is_base")),
                        )
                    )
            elif page_title and name_cn and name_en:
                targets.append(
                    CharacterAssetTarget(
                        page_title=page_title,
                        name_cn=name_cn,
                        name_en=name_en,
                        character_id=character_id,
                    )
                )
        return targets
    if not isinstance(data, dict):
        raise ValueError("characters json must be a mapping or a schema-v2 index")
    return [
        CharacterAssetTarget(
            page_title=str(name_cn),
            name_cn=str(name_cn),
            name_en=str(name_en),
        )
        for name_cn, name_en in data.items()
        if name_cn and name_en
    ]


def load_characters_from_json(json_path: str | Path) -> dict[str, str]:
    return {
        target.page_title: target.name_en
        for target in load_asset_targets_from_json(json_path)
    }
