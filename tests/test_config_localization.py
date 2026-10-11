from maibot_sdk.config import generate_plugin_config_schema

from config import MaizonePluginConfig


def test_every_config_section_and_field_has_simplified_chinese_schema() -> None:
    schema = generate_plugin_config_schema(MaizonePluginConfig, plugin_id="internetsb.maizone")

    assert schema["sections"]
    for section in schema["sections"].values():
        assert section["i18n"]["zh_CN"]["title"] == section["title"]
        for field in section["fields"].values():
            localized = field["i18n"]["zh_CN"]
            assert localized["label"] == field["label"]
            assert localized["hint"] == field["hint"]
            assert localized["label"]
