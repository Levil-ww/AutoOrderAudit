"""
方果ERP自动审单 - 连通性测试
"""


def test_auth():
    print("=" * 60)
    print("🔐 测试鉴权")
    print("=" * 60)
    try:
        from adapters.fangguo import FangguoAdapter
        adapter = FangguoAdapter()
        orders = adapter.query_orders(page_no=1, page_size=3)
        print(f"✅ 鉴权成功！查询到 {len(orders)} 个订单")
        if orders:
            print(f"   第一个订单: {orders[0].trade_id}")
            print(f"   卖家备注: {orders[0].shop_remark[:50]}...")
        return True
    except Exception as e:
        print(f"❌ 鉴权失败: {e}")
        print("  请检查 adapters/fangguo/config.py 中的 Token/Cookie")
        return False


def test_parser():
    print("\n" + "=" * 60)
    print("🧩 测试备注解析器")
    print("=" * 60)
    from core.parser import parse_remark
    from adapters.fangguo.config import MATERIAL_MAP
    cases = [
        "定制双面芊花幔;38x195cm-1张",
        "定制吸水皮革花幔;40x60cm-1张",
        "定制防辣椒油;60x90cm*2",
        "定制有机硅;30x120cm-1张",
        "定制鹿皮绒烫画;50x80cm",
        "双面革花幔;30x120cm-2张",
    ]
    for r in cases:
        p = parse_remark(r, material_map=MATERIAL_MAP)
        s = "✅" if p.success else "❌"
        print(f"\n{s} 输入: {r}")
        print(f"   编码: {p.shop_mapping_sku}  [{p.material_source}]")


def test_full_flow():
    print("\n" + "=" * 60)
    print("🔄 全流程模拟（DRY RUN）")
    print("=" * 60)
    from adapters.fangguo import FangguoAdapter
    from core import AutoAuditEngine
    adapter = FangguoAdapter()
    engine = AutoAuditEngine(adapter=adapter, dry_run=True, max_orders=3)
    engine.run(page_size=10)


def main():
    auth_ok = test_auth()
    test_parser()
    if auth_ok:
        test_full_flow()
    print("\n" + "=" * 60)
    if auth_ok:
        print("✅ 一切就绪！运行 python main.py 开始自动审单")
    else:
        print("⚠️  请先修复鉴权问题")
    print("=" * 60)


if __name__ == "__main__":
    main()