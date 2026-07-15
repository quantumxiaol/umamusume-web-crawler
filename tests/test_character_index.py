import json

import pytest

from umamusume_web_crawler.web import character_index
from umamusume_web_crawler.web.biligame_assets import load_asset_targets_from_json


def test_parse_biligame_index_groups_base_and_costume_pages() -> None:
    html = """
    <div>
      <a href="/umamusume/特别周" title="特别周">
        <img alt="Chr icon 1001 100101 01.png" />
      </a>
      <a href="/umamusume/换装特别周" title="〖夏日〗特别周">
        <img alt="Chr icon 1001 100102 01.png" />
      </a>
      <a href="/umamusume/特别周" title="特别周">
        <img alt="Chr icon 1001 100101 01.png" />
      </a>
    </div>
    """

    records = character_index.parse_biligame_index(html)

    assert records == [
        {
            "character_id": "1001",
            "wiki_title": "特别周",
            "variants": [
                {
                    "costume_id": "100101",
                    "wiki_title": "特别周",
                    "label": None,
                    "is_base": True,
                },
                {
                    "costume_id": "100102",
                    "wiki_title": "〖夏日〗特别周",
                    "label": "〖夏日〗",
                    "is_base": False,
                },
            ],
        }
    ]


def test_parse_official_characters_excludes_second_article() -> None:
    html = """
    <div class="character-index">
      <article><div class="character-index__list"><ul><li>
        <a href="/character/specialweek">
          <div class="dt-bg"><p>Special Week</p></div>
          <dd><p class="name">スペシャルウィーク</p></dd>
        </a>
      </li></ul></div></article>
      <article><div class="character-index__list"><ul><li>
        <a href="/character/happymeek">
          <div class="dt-bg"><p>Happy Meek</p></div>
          <dd><p class="name">ハッピーミーク</p></dd>
        </a>
      </li></ul></div></article>
    </div>
    """

    assert character_index.parse_official_characters(html) == [
        {
            "official_slug": "specialweek",
            "name_en": "Special Week",
            "name_ja": "スペシャルウィーク",
        }
    ]


@pytest.mark.asyncio
async def test_build_character_index_merges_sources_and_manual_names(
    tmp_path, monkeypatch
) -> None:
    existing = tmp_path / "characters.json"
    existing.write_text(
        json.dumps(
            {
                "特别周": "Special Week",
                "罗伊斯兄弟": "Royce and Royce",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    overrides = tmp_path / "overrides.json"
    overrides.write_text(
        json.dumps({"杏目": "Almond Eye"}, ensure_ascii=False),
        encoding="utf-8",
    )
    biligame_html = """
    <a href="/umamusume/特别周" title="特别周">
      <img alt="Chr icon 1001 100101 01.png" />
    </a>
    <a href="/umamusume/杏目" title="杏目">
      <img alt="Chr icon 1129 112901 01.png" />
    </a>
    <a href="/umamusume/罗伊斯换装" title="【Inspiring Genius】ロイスアンドロイス">
      <img alt="Chr icon 1103 110301 01.png" />
    </a>
    """
    official_html = """
    <div class="character-index"><article><div class="character-index__list"><ul>
      <li><a href="/character/specialweek"><div class="dt-bg"><p>Special Week</p></div><dd><p class="name">スペシャルウィーク</p></dd></a></li>
      <li><a href="/character/almondeye"><div class="dt-bg"><p>Almond Eye</p></div><dd><p class="name">アーモンドアイ</p></dd></a></li>
      <li><a href="/character/royceandroyce"><div class="dt-bg"><p>Royce and Royce</p></div><dd><p class="name">ロイスアンドロイス</p></dd></a></li>
    </ul></div></article></div>
    """

    async def fake_biligame(title, **kwargs):
        assert title == character_index.BILIGAME_INDEX_TITLE
        return biligame_html

    async def fake_official(**kwargs):
        return official_html

    monkeypatch.setattr(character_index, "fetch_biligame_html", fake_biligame)
    monkeypatch.setattr(character_index, "fetch_official_character_html", fake_official)

    payload, unresolved = await character_index.build_character_index(
        existing_path=existing,
        overrides_path=overrides,
        detail_delay=0,
    )

    assert unresolved == []
    assert payload["counts"] == {
        "characters": 3,
        "implemented": 3,
        "variants": 3,
        "unresolved": 0,
    }
    assert [item["name_cn"] for item in payload["characters"]] == [
        "特别周",
        "杏目",
        "罗伊斯兄弟",
    ]


def test_load_asset_targets_from_rich_index_includes_variants(tmp_path) -> None:
    path = tmp_path / "characters.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "characters": [
                    {
                        "id": "1001",
                        "name_cn": "特别周",
                        "name_en": "Special Week",
                        "implemented": True,
                        "wiki_title": "特别周",
                        "variants": [
                            {
                                "costume_id": "100101",
                                "wiki_title": "特别周",
                                "is_base": True,
                            },
                            {
                                "costume_id": "100102",
                                "wiki_title": "〖夏日〗特别周",
                                "is_base": False,
                            },
                        ],
                    },
                    {
                        "name_cn": "未实装",
                        "name_en": "Unreleased",
                        "implemented": False,
                        "variants": [],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    targets = load_asset_targets_from_json(path, include_variants=True)

    assert [target.page_title for target in targets] == ["特别周", "〖夏日〗特别周"]
    assert all(target.name_en == "Special Week" for target in targets)
