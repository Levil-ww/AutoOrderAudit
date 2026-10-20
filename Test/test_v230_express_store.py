"""
店铺/平台级快递选择功能测试
测试四级优先级：备注 > 店铺 > 平台 > 省份
"""
import pytest
from express_manager import ExpressManager


@pytest.fixture
def mgr(monkeypatch, tmp_path):
    """每个测试用例都拿到一个全新的 ExpressManager 实例（清除真实配置文件的影响）"""
    import express_manager as em
    monkeypatch.setattr(em, "_CONFIG_FILE", tmp_path / "express-fixture.json")
    monkeypatch.setattr(ExpressManager, "_instance", None)
    instance = ExpressManager()
    # 路径在实例化之前已隔离；仅使用测试默认配置。
    instance._store_map.clear()
    instance._platform_map.clear()
    yield instance
    ExpressManager._instance = None


# ── 店铺精确匹配 ──────────────────────────────────────────

class TestStoreOverride:
    def test_store_matches_configured_express(self, mgr):
        """已配置店铺应返回指定快递"""
        mgr.set_store_express("怡达怡盛家居专卖店", "中通")
        name, code = mgr.resolve_express(
            province="江苏",
            remark="",
            store_name="怡达怡盛家居专卖店",
            platform_name="抖音",
        )
        assert name == "中通"
        assert code == "ZTO"

    def test_unconfigured_store_falls_through_to_platform(self, mgr):
        """未配置的店铺降级到平台匹配"""
        mgr.set_platform_express("抖音", "极兔")
        name, code = mgr.resolve_express(
            province="江苏",
            remark="",
            store_name="大魔法时尚家居",
            platform_name="抖音",
        )
        assert name == "极兔"
        assert code == "HTKY"

    def test_empty_store_name_skips_store_level(self, mgr):
        """空 store_name 跳过店铺匹配"""
        mgr.set_store_express("怡达怡盛家居专卖店", "中通")
        mgr.set_platform_express("抖音", "极兔")
        name, code = mgr.resolve_express(
            province="江苏",
            remark="",
            store_name="",
            platform_name="抖音",
        )
        assert name == "极兔"


# ── 平台匹配 ──────────────────────────────────────────────

class TestPlatformOverride:
    def test_platform_matches_all_stores(self, mgr):
        """平台配置对该平台下所有店铺生效"""
        mgr.set_platform_express("抖音", "中通")
        name, code = mgr.resolve_express(
            province="江苏",
            remark="",
            store_name="芙娑家居企业店",
            platform_name="抖音",
        )
        assert name == "中通"
        assert code == "ZTO"

    def test_unconfigured_platform_falls_through_to_province(self, mgr):
        """未配置平台降级到省份匹配"""
        name, code = mgr.resolve_express(
            province="江苏",
            remark="",
            store_name="某店铺",
            platform_name="抖音",
        )
        assert name == "极兔"  # 江苏默认极兔

    def test_empty_platform_name_skips_platform_level(self, mgr):
        """空 platform_name 跳过平台匹配"""
        mgr.set_platform_express("抖音", "中通")
        name, code = mgr.resolve_express(
            province="江苏",
            remark="",
            store_name="某店铺",
            platform_name="",
        )
        assert name == "极兔"  # 直接落到省份


# ── 优先级完整链路 ─────────────────────────────────────────

class TestPriorityChain:
    def test_remark_beats_store(self, mgr):
        """备注优先级高于店铺"""
        mgr.set_store_express("怡达怡盛家居专卖店", "中通")
        name, code = mgr.resolve_express(
            province="江苏",
            remark="发顺丰",
            store_name="怡达怡盛家居专卖店",
            platform_name="抖音",
        )
        assert name == "顺丰"
        assert code == "SF"

    def test_store_beats_platform(self, mgr):
        """店铺配置优先于平台配置"""
        mgr.set_store_express("怡达怡盛家居专卖店", "中通")
        mgr.set_platform_express("抖音", "极兔")
        name, code = mgr.resolve_express(
            province="江苏",
            remark="",
            store_name="怡达怡盛家居专卖店",
            platform_name="抖音",
        )
        assert name == "中通"
        assert code == "ZTO"

    def test_platform_beats_province(self, mgr):
        """平台配置优先于省份映射"""
        mgr.set_platform_express("抖音", "中通")
        name, code = mgr.resolve_express(
            province="江苏",  # 默认极兔
            remark="",
            store_name="某店铺",
            platform_name="抖音",
        )
        assert name == "中通"

    def test_full_fallback_chain(self, mgr):
        """全部未配置时最终落到省份映射"""
        name, code = mgr.resolve_express(
            province="西藏",  # 默认中通
            remark="",
            store_name="未知店铺",
            platform_name="未知平台",
        )
        assert name == "中通"
        assert code == "ZTO"

    def test_all_unresolvable_returns_none(self, mgr):
        """省份也不在映射中时返回 None"""
        name, code = mgr.resolve_express(
            province="不存在的省份",
            remark="",
            store_name="",
            platform_name="",
        )
        assert name is None
        assert code is None


# ── 配置管理 ──────────────────────────────────────────────

class TestStorePlatformConfig:
    def test_remove_store_express(self, mgr):
        """移除店铺配置后降级到平台"""
        mgr.set_store_express("怡达怡盛家居专卖店", "中通")
        mgr.set_platform_express("抖音", "极兔")
        mgr.remove_store_express("怡达怡盛家居专卖店")
        name, code = mgr.resolve_express(
            province="江苏",
            remark="",
            store_name="怡达怡盛家居专卖店",
            platform_name="抖音",
        )
        assert name == "极兔"

    def test_remove_platform_express(self, mgr):
        """移除平台配置后降级到省份"""
        mgr.set_platform_express("抖音", "中通")
        mgr.remove_platform_express("抖音")
        name, code = mgr.resolve_express(
            province="江苏",  # 默认极兔
            remark="",
            store_name="某店铺",
            platform_name="抖音",
        )
        assert name == "极兔"

    def test_store_map_property(self, mgr):
        """store_map 属性返回当前配置副本"""
        mgr.set_store_express("店铺A", "中通")
        mgr.set_store_express("店铺B", "顺丰")
        assert mgr.store_map == {"店铺A": "中通", "店铺B": "顺丰"}

    def test_platform_map_property(self, mgr):
        """platform_map 属性返回当前配置副本"""
        mgr.set_platform_express("抖音", "极兔")
        mgr.set_platform_express("淘宝", "中通")
        assert mgr.platform_map == {"抖音": "极兔", "淘宝": "中通"}


# ── 持久化 ────────────────────────────────────────────────

class TestPersistence:
    def test_save_and_load_store_overrides(self, mgr, tmp_path, monkeypatch):
        """保存后重新加载，店铺配置不丢失"""
        import express_manager as em
        config_file = tmp_path / "express_config.json"
        monkeypatch.setattr(em, "_CONFIG_FILE", config_file)

        mgr.set_store_express("怡达怡盛家居专卖店", "中通")
        mgr.save()

        # 重新加载
        ExpressManager._instance = None
        new_mgr = ExpressManager()
        monkeypatch.setattr(em, "_CONFIG_FILE", config_file)
        new_mgr._load()
        assert new_mgr.store_map.get("怡达怡盛家居专卖店") == "中通"

    def test_save_and_load_platform_overrides(self, mgr, tmp_path, monkeypatch):
        """保存后重新加载，平台配置不丢失"""
        import express_manager as em
        config_file = tmp_path / "express_config.json"
        monkeypatch.setattr(em, "_CONFIG_FILE", config_file)

        mgr.set_platform_express("抖音", "极兔")
        mgr.save()

        ExpressManager._instance = None
        new_mgr = ExpressManager()
        monkeypatch.setattr(em, "_CONFIG_FILE", config_file)
        new_mgr._load()
        assert new_mgr.platform_map.get("抖音") == "极兔"


# ── 边界场景 ──────────────────────────────────────────────

class TestEdgeCases:
    def test_backward_compatible_call_without_new_params(self, mgr):
        """不传 store_name/platform_name 时行为与旧版一致"""
        name, code = mgr.resolve_express("江苏", "发顺丰")
        assert name == "顺丰"
        assert code == "SF"

    def test_backward_compatible_province_only(self, mgr):
        """只传省份时行为与旧版一致"""
        name, code = mgr.resolve_express("江苏", "")
        assert name == "极兔"
        assert code == "HTKY"

    def test_store_with_no_platform(self, mgr):
        """有店铺配置但无平台信息时，店铺匹配仍生效"""
        mgr.set_store_express("某店铺", "中通")
        name, code = mgr.resolve_express(
            province="江苏",
            remark="",
            store_name="某店铺",
            platform_name="",
        )
        assert name == "中通"

    def test_platform_with_no_store(self, mgr):
        """有平台配置但无店铺名时，平台匹配仍生效"""
        mgr.set_platform_express("抖音", "中通")
        name, code = mgr.resolve_express(
            province="江苏",
            remark="",
            store_name="",
            platform_name="抖音",
        )
        assert name == "中通"

    def test_store_override_takes_precedence_over_platform(self, mgr):
        """同一店铺既属于某平台，又有独立配置时，店铺配置优先"""
        mgr.set_platform_express("抖音", "极兔")
        mgr.set_store_express("怡达怡盛家居专卖店", "顺丰")
        name, code = mgr.resolve_express(
            province="江苏",
            remark="",
            store_name="怡达怡盛家居专卖店",
            platform_name="抖音",
        )
        assert name == "顺丰"
        assert code == "SF"


# ── 用户实际配置场景集成测试 ──────────────────────────────

class TestRealWorldConfig:
    """
    用户指定的配置：
    - 抖音平台下所有店铺 → 中通
    - 微信小店 → 中通
    - 淘宝中特定5家店铺 → 中通
    - 其余由省份映射或备注决定
    """

    @pytest.fixture
    def configured_mgr(self):
        """预设用户指定的配置"""
        ExpressManager._instance = None
        mgr = ExpressManager()
        # 平台级配置
        mgr.set_platform_express("抖音", "中通")
        mgr.set_platform_express("微信小店", "中通")
        # 店铺级配置（淘宝特定店铺）
        mgr.set_store_express("诺栀旗舰店", "中通")
        mgr.set_store_express("芙娑旗舰店", "中通")
        mgr.set_store_express("HBLOVE 官方企业店", "中通")
        mgr.set_store_express("恋尚美家企业店", "中通")
        mgr.set_store_express("黑白之恋旗舰店", "中通")
        yield mgr
        ExpressManager._instance = None

    def test_douyin_store_uses_platform_rule(self, configured_mgr):
        """抖音下未单独配置的店铺走平台规则→中通"""
        name, code = configured_mgr.resolve_express(
            province="西藏",
            remark="",
            store_name="大魔法时尚家居",
            platform_name="抖音",
        )
        assert name == "中通"
        assert code == "ZTO"

    def test_douyin_store_remark_overrides_platform(self, configured_mgr):
        """抖音店铺备注指定顺丰时，备注优先"""
        name, code = configured_mgr.resolve_express(
            province="江苏",
            remark="发顺丰",
            store_name="dmf家居日用旗舰店",
            platform_name="抖音",
        )
        assert name == "顺丰"
        assert code == "SF"

    def test_wechat_shop_uses_platform_rule(self, configured_mgr):
        """微信小店走平台规则→中通"""
        name, code = configured_mgr.resolve_express(
            province="广东",
            remark="",
            store_name="dmf家居软装馆",
            platform_name="微信小店",
        )
        assert name == "中通"
        assert code == "ZTO"

    def test_taobao_configured_store_uses_store_rule(self, configured_mgr):
        """淘宝已配置店铺走店铺规则→中通"""
        name, code = configured_mgr.resolve_express(
            province="西藏",
            remark="",
            store_name="诺栀旗舰店",
            platform_name="淘宝",
        )
        assert name == "中通"
        assert code == "ZTO"

    def test_taobao_unconfigured_store_falls_to_province(self, configured_mgr):
        """淘宝未配置店铺走省份映射"""
        name, code = configured_mgr.resolve_express(
            province="江苏",  # 默认极兔
            remark="",
            store_name="花沐旗舰店",
            platform_name="淘宝",
        )
        assert name == "极兔"
        assert code == "HTKY"

    def test_taobao_unconfigured_store_remote_province(self, configured_mgr):
        """淘宝未配置店铺在偏远省份走省份映射→中通"""
        name, code = configured_mgr.resolve_express(
            province="新疆",  # 默认中通
            remark="",
            store_name="花沐旗舰店",
            platform_name="淘宝",
        )
        assert name == "中通"
        assert code == "ZTO"

    def test_pdd_store_falls_to_province(self, configured_mgr):
        """拼多多未配置平台和店铺，走省份映射"""
        name, code = configured_mgr.resolve_express(
            province="江苏",
            remark="",
            store_name="花沐家居旗舰店",
            platform_name="拼多多",
        )
        assert name == "极兔"  # 江苏默认极兔

    def test_all_five_taobao_stores(self, configured_mgr):
        """5家淘宝特定店铺全部返回中通"""
        stores = [
            "诺栀旗舰店", "芙娑旗舰店", "HBLOVE 官方企业店",
            "恋尚美家企业店", "黑白之恋旗舰店",
        ]
        for store in stores:
            name, code = configured_mgr.resolve_express(
                province="广东",
                remark="",
                store_name=store,
                platform_name="淘宝",
            )
            assert name == "中通", f"{store} 应该返回中通，实际返回 {name}"
            assert code == "ZTO"
