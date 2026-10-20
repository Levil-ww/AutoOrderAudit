"""赠品匹配与配置持久化边界，复用安全插件的临时配置隔离。"""

import pytest

import gift_manager


@pytest.mark.parametrize("text,expected", [
    ("赠品沥水垫30×50厘米", "方垫"),
    ("送南爪", "南瓜"),
    ("", ""),
    ("完全无关的商品描述", ""),
])
def test_gift_matching_normalization_and_rejection(text: str, expected: str) -> None:
    assert gift_manager.GiftManager().match_gift(text) == expected


def test_custom_gift_save_reload_remove_and_defaults() -> None:
    manager = gift_manager.GiftManager()
    manager.add_gift(" 测试赠品 ", " 测试标题 ", "材质-颜色-型号-花型", "goods-fixture", "sku-fixture", ["测试别名"])
    manager.save()
    manager.reload()
    config = manager.get_config("测试别名")
    assert config is not None
    assert config["name"] == "测试赠品"
    assert config["title"] == "测试标题"
    assert config["goods_id"] == "goods-fixture"
    assert config["sku_id"] == "sku-fixture"
    assert config["shop_sku"] == "材质-颜色-型号-花型"
    assert manager.remove_gift("圆垫") is False
    assert manager.remove_gift("测试赠品") is True
    manager.save()
    manager.reload()
    assert manager.get_config("测试别名") is None
    assert manager.get_config("圆垫") is not None


def test_malformed_config_falls_back_to_defaults() -> None:
    gift_manager._CONFIG_FILE.write_text("{broken", encoding="utf-8")
    manager = gift_manager.GiftManager()
    assert manager.match_gift("南瓜") == "南瓜"
    assert manager.match_gift("方垫") == "方垫"
