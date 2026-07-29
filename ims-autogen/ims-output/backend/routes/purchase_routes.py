"""采购订单 & 入库确认路由"""

from flask import Blueprint, request
from services.purchase_service import PurchaseService
from utils.response import success_response, error_response

purchase_bp = Blueprint('purchase', __name__, url_prefix='/api/v1')


@purchase_bp.route('/purchase-orders', methods=['GET'])
def list_purchase_orders():
    """获取采购订单列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', '').strip() or None
    keyword = request.args.get('keyword', '').strip() or None

    try:
        orders, total = PurchaseService.get_order_list(
            page=page, per_page=per_page, status=status, keyword=keyword
        )
        return success_response({
            'items': [o.to_dict() for o in orders],
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page if per_page > 0 else 0
        })
    except Exception as e:
        return error_response(str(e))


@purchase_bp.route('/purchase-orders', methods=['POST'])
def create_purchase_order():
    """创建采购订单"""
    data = request.get_json(silent=True) or {}
    try:
        order = PurchaseService.create_order(data)
        return success_response(order.to_dict(), '采购订单创建成功')
    except ValueError as e:
        return error_response(str(e))
    except Exception as e:
        return error_response(f'创建失败：{str(e)}')


@purchase_bp.route('/purchase-orders/<int:order_id>', methods=['GET'])
def get_purchase_order(order_id):
    """获取采购订单详情"""
    try:
        order = PurchaseService.get_order_detail(order_id)
        if not order:
            return error_response('采购订单不存在', 404)
        return success_response(order.to_dict())
    except Exception as e:
        return error_response(str(e))


@purchase_bp.route('/purchase-orders/<int:order_id>', methods=['PUT'])
def update_purchase_order(order_id):
    """编辑采购订单"""
    data = request.get_json(silent=True) or {}
    try:
        order = PurchaseService.update_order(order_id, data)
        return success_response(order.to_dict(), '采购订单更新成功')
    except ValueError as e:
        return error_response(str(e))
    except Exception as e:
        return error_response(f'更新失败：{str(e)}')


@purchase_bp.route('/purchase-orders/<int:order_id>', methods=['DELETE'])
def delete_purchase_order(order_id):
    """删除采购订单"""
    try:
        PurchaseService.delete_order(order_id)
        return success_response(message='采购订单删除成功')
    except ValueError as e:
        return error_response(str(e))
    except Exception as e:
        return error_response(f'删除失败：{str(e)}')


@purchase_bp.route('/purchase-orders/<int:order_id>/receive', methods=['POST'])
def receive_purchase_order(order_id):
    """入库确认"""
    data = request.get_json(silent=True) or {}
    try:
        order = PurchaseService.receive_order(order_id, data.get('receive_items'))
        return success_response(order.to_dict(), '入库确认成功')
    except ValueError as e:
        return error_response(str(e))
    except Exception as e:
        return error_response(f'入库失败：{str(e)}')


@purchase_bp.route('/purchase-orders/<int:order_id>/cancel', methods=['POST'])
def cancel_purchase_order(order_id):
    """取消采购订单"""
    try:
        order = PurchaseService.cancel_order(order_id)
        return success_response(order.to_dict(), '订单已取消')
    except ValueError as e:
        return error_response(str(e))
    except Exception as e:
        return error_response(f'取消失败：{str(e)}')
