import sys
sys.path.insert(0, '/')
from unittest.mock import MagicMock
from core.adapter_base import Order, OrderItem
from adapters.fangguo.adapter import FangguoAdapter
from core.parser import extract_multiple_remarks

adapter = FangguoAdapter()


def make_raw(item_id, sku, num, type_val=0):
    return {
        'id': item_id,
        'orderId': '3314708616421014679',
        'sysOid': f's{item_id}',
        'oid': '3314708616421014679',
        'title': '测试商品',
        'skuPropertiesName': '',
        'shopMappingSku': sku,
        'originalSkuId': '',
        'originalGoodsId': '',
        'merchandisePicPath': '',
        'num': num,
        'price': 100,
        'type': type_val,
        'shopRemark': '',
    }


remark = '定制双面革中古花园;33x43-1张, 巴黎左岸;45.8x194.5cm-1张, 花橙;40.8x220cm-1张, 定制镜面皮革墨客;124x124cm-1张，共计4张，8月10日发货'
parsed_list = extract_multiple_remarks(remark, material_map=adapter.material_map, material_matcher=adapter.get_material_matcher())
print('解析结果数:', len(parsed_list))
for p in parsed_list:
    print(' ', p.shop_mapping_sku, 'num=', p.num)

order = Order(
    trade_id='3314708616421014679',
    tid='3314708616421014679',
    sys_tid='',
    shop_remark=remark,
    factory_id=0,
    items=[
        OrderItem(id='1', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s1', title='测试商品', shop_mapping_sku='双面格-定制-定制尺寸-中古花园;45.8x194.5CM', num=1, raw=make_raw('1', '双面格-定制-定制尺寸-中古花园;45.8x194.5CM', 1, 0)),
        OrderItem(id='2', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s2', title='测试商品', shop_mapping_sku='双面格-定制-定制尺寸-中古花园;40.8x220CM', num=1, raw=make_raw('2', '双面格-定制-定制尺寸-中古花园;40.8x220CM', 1, 0)),
        OrderItem(id='3', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s3', title='测试商品', shop_mapping_sku='双面格-定制-定制尺寸-中古花园;33x43CM', num=1, raw=make_raw('3', '双面格-定制-定制尺寸-中古花园;33x43CM', 1, 0)),
        OrderItem(id='4', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s4', title='测试商品', shop_mapping_sku='镜面皮革-定制-定制尺寸-墨客;124x124CM8月10日发货', num=1, raw=make_raw('4', '镜面皮革-定制-定制尺寸-墨客;124x124CM8月10日发货', 1, 1)),
        OrderItem(id='5', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s5', title='测试商品', shop_mapping_sku='镜面皮革-定制-定制尺寸-墨客;124x124CM', num=1, raw=make_raw('5', '镜面皮革-定制-定制尺寸-墨客;124x124CM', 1, 1)),
        OrderItem(id='6', order_id='3314708616421014679', oid='3314708616421014679', sys_oid='s6', title='测试商品', shop_mapping_sku='镜面皮革-定制-定制尺寸-墨客;124x124CM', num=1, raw=make_raw('6', '镜面皮革-定制-定制尺寸-墨客;124x124CM', 1, 1)),
    ]
)

captured = {}
def mock_post(url, json=None, timeout=None):
    captured['payload'] = json
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {'code': 0, 'data': True, 'msg': ''}
    return resp

adapter._session.post = mock_post

result = adapter.update_merchant_code(order, parsed_list[0], parsed_list, None, gift_no_ship=False)
print('update_merchant_code result:', result)
print('提交商品行数:', len(captured['payload']['orderItems']))
for i, it in enumerate(captured['payload']['orderItems']):
    print(f"  item[{i}]: type={it.get('type')}, id={it.get('id')}, shopMappingSku={it.get('shopMappingSku')}, num={it.get('num')}")
