"""库存查询 & 流水路由"""

from flask import Blueprint, request
from services.stock_service import StockService
from utils.response import success_response, error_response

stock_bp = Blueprint('stock', __name__, url_prefix='/api/v1')


@stock_bp.route('/stock', methods=['GET'])
def get_stock_list():
    """获取库存列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    keyword = request.args.get('keyword', '').strip() or None
    category_id = request.args.get('category_id', type=int)
    low_stock_only = request.args.get('low_stock_only', type=bool) or False

    try:
        items, total = StockService.get_stock_list(
            page=page, per_page=per_page,
            keyword=keyword, category_id=category_id,
            low_stock_only=low_stock_only
        )
        return success_response({
            'items': items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page if per_page > 0 else 0
        })
    except Exception as e:
        return error_response(str(e))


@stock_bp.route('/stock/<int:product_id>', methods=['GET'])
def get_product_stock(product_id):
    """获取单个商品库存"""
    try:
        product = StockService.get_product_stock(product_id)
        return success_response(product.to_dict())
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        return error_response(str(e))


@stock_bp.route('/stock/transactions', methods=['GET'])
def get_stock_transactions():
    """获取库存流水"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    product_id = request.args.get('product_id', type=int)
    type_filter = request.args.get('type', '').strip() or None
    start_date = request.args.get('start_date', '').strip() or None
    end_date = request.args.get('end_date', '').strip() or None

    try:
        items, total = StockService.get_transactions(
            page=page, per_page=per_page,
            product_id=product_id, type_filter=type_filter,
            start_date=start_date, end_date=end_date
        )
        return success_response({
            'items': items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page if per_page > 0 else 0
        })
    except Exception as e:
        return error_response(str(e))


@stock_bp.route('/stock/low-stock', methods=['GET'])
def get_low_stock_products():
    """获取低库存商品列表"""
    try:
        products = StockService.get_low_stock_products()
        return success_response(products)
    except Exception as e:
        return error_response(str(e))
