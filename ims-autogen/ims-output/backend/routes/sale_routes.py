"""销售订单 & 出库确认路由"""

from flask import Blueprint, request
from services.sale_service import SaleService
from utils.response import success_response, error_response

sale_bp = Blueprint('sale', __name__, url_prefix='/api/v1')


@sale_bp.route('/sale-orders', methods=['GET'])
def list_sale_orders():
    """获取销售订单列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', '').strip() or None
    keyword = request.args.get('keyword', '').strip() or None

    try:
        orders, total = SaleService.get_order_list(
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


@sale_bp.route('/sale-orders', methods=['POST'])
def create_sale_order():
    """创建销售订单"""
    data = request.get_json(silent=True) or {}
    try:
        order, warnings = SaleService.create_order(data)
        result = order.to_dict()
        if warnings:
            result['warnings'] = warnings
        return success_response(result, '销售订单创建成功' + ('（含库存预警）' if warnings else ''))
    except ValueError as e:
        return error_response(str(e))
    except Exception as e:
        return error_response(f'创建失败：{str(e)}')


@sale_bp.route('/sale-orders/<int:order_id>', methods=['GET'])
def get_sale_order(order_id):
    """获取销售订单详情"""
    try:
        order = SaleService.get_order_detail(order_id)
        if not order:
            return error_response('销售订单不存在', 404)
        return success_response(order.to_dict())
    except Exception as e:
        return error_response(str(e))


@sale_bp.route('/sale-orders/<int:order_id>', methods=['PUT'])
def update_sale_order(order_id):
    """编辑销售订单"""
    data = request.get_json(silent=True) or {}
    try:
        order, warnings = SaleService.update_order(order_id, data)
        result = order.to_dict()
        if warnings:
            result['warnings'] = warnings
        return success_response(result, '销售订单更新成功')
    except ValueError as e:
        return error_response(str(e))
    except Exception as e:
        return error_response(f'更新失败：{str(e)}')


@sale_bp.route('/sale-orders/<int:order_id>', methods=['DELETE'])
def delete_sale_order(order_id):
    """删除销售订单"""
    try:
        SaleService.delete_order(order_id)
        return success_response(message='销售订单删除成功')
    except ValueError as e:
        return error_response(str(e))
    except Exception as e:
        return error_response(f'删除失败：{str(e)}')


@sale_bp.route('/sale-orders/<int:order_id>/ship', methods=['POST'])
def ship_sale_order(order_id):
    """出库确认"""
    data = request.get_json(silent=True) or {}
    try:
        order = SaleService.ship_order(order_id, data.get('ship_items'))
        return success_response(order.to_dict(), '出库确认成功')
    except ValueError as e:
        return error_response(str(e))
    except Exception as e:
        return error_response(f'出库失败：{str(e)}')


@sale_bp.route('/sale-orders/<int:order_id>/cancel', methods=['POST'])
def cancel_sale_order(order_id):
    """取消销售订单"""
    try:
        order = SaleService.cancel_order(order_id)
        return success_response(order.to_dict(), '订单已取消')
    except ValueError as e:
        return error_response(str(e))
    except Exception as e:
        return error_response(f'取消失败：{str(e)}')
