"""库存服务 - 库存查询/流水/预警"""

from datetime import datetime
from sqlalchemy import desc
from models import db
from models.product import Product
from models.stock import StockTransaction


class StockService:
    """库存业务逻辑"""

    @staticmethod
    def get_stock_list(page=1, per_page=20, keyword=None, category_id=None, low_stock_only=False):
        """获取库存列表"""
        query = Product.query
        if keyword:
            query = query.filter(
                Product.name.contains(keyword) |
                Product.code.contains(keyword)
            )
        if category_id:
            query = query.filter(Product.category_id == category_id)
        if low_stock_only:
            query = query.filter(Product.current_stock < Product.min_stock)
        query = query.order_by(Product.name)
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        items = [p.to_dict() for p in pagination.items]
        return items, pagination.total

    @staticmethod
    def get_product_stock(product_id):
        """获取单个商品库存详情"""
        product = Product.query.get(product_id)
        if not product:
            raise ValueError('商品不存在')
        return product

    @staticmethod
    def get_transactions(page=1, per_page=20, product_id=None, type_filter=None, start_date=None, end_date=None):
        """获取库存流水列表"""
        query = StockTransaction.query
        if product_id:
            query = query.filter(StockTransaction.product_id == product_id)
        if type_filter:
            query = query.filter(StockTransaction.type == type_filter)
        if start_date:
            query = query.filter(StockTransaction.created_at >= start_date)
        if end_date:
            query = query.filter(StockTransaction.created_at <= end_date + ' 23:59:59')
        query = query.order_by(desc(StockTransaction.created_at))
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        items = [t.to_dict() for t in pagination.items]
        return items, pagination.total

    @staticmethod
    def get_low_stock_products():
        """获取所有低库存商品"""
        products = Product.query.filter(Product.current_stock < Product.min_stock).all()
        return [p.to_dict() for p in products]
