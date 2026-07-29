"""报表服务 - 进销存汇总/销售明细"""

from datetime import datetime, timedelta
from sqlalchemy import desc, func
from . import db
from .models.product import Product
from .models.stock import StockTransaction
from .models.sale import SaleOrder, SaleOrderItem
from .models.purchase import PurchaseOrder, PurchaseOrderItem


class ReportService:
    """报表统计业务逻辑"""

    @staticmethod
    def get_summary_report(start_date=None, end_date=None):
        """获取进销存汇总报表"""
        if not end_date:
            end_date = datetime.now()
        elif isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d')

        if not start_date:
            start_date = end_date - timedelta(days=30)
        elif isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d')

        # 统计期间结束时间精确到日末
        end_of_day = end_date.replace(hour=23, minute=59, second=59)

        products = Product.query.all()
        summary_items = []

        for product in products:
            # 期初库存 = start_date 之前的库存汇总
            begin_stock = db.session.query(
                func.coalesce(func.sum(StockTransaction.quantity_change), 0)
            ).filter(
                StockTransaction.product_id == product.id,
                StockTransaction.created_at < start_date
            ).scalar() or 0

            # 期间采购入库
            purchase_qty = db.session.query(
                func.coalesce(func.sum(StockTransaction.quantity_change), 0)
            ).filter(
                StockTransaction.product_id == product.id,
                StockTransaction.type == '采购入库',
                StockTransaction.created_at.between(start_date, end_of_day)
            ).scalar() or 0

            # 期间销售出库（库存记录为负值，取绝对值）
            sale_qty = db.session.query(
                func.coalesce(func.sum(StockTransaction.quantity_change), 0)
            ).filter(
                StockTransaction.product_id == product.id,
                StockTransaction.type == '销售出库',
                StockTransaction.created_at.between(start_date, end_of_day)
            ).scalar() or 0

            end_stock = product.current_stock or 0
            purchase_qty = float(purchase_qty)
            sale_qty = abs(float(sale_qty))

            if float(begin_stock) == 0 and purchase_qty == 0 and sale_qty == 0 and float(end_stock) == 0:
                continue

            summary_items.append({
                'product_id': product.id,
                'product_name': product.name,
                'product_code': product.code,
                'category_name': product.category.name if product.category else '',
                'unit_name': product.unit.name if product.unit else '',
                'begin_stock': float(begin_stock),
                'purchase_qty': purchase_qty,
                'sale_qty': sale_qty,
                'end_stock': float(end_stock)
            })

        return {
            'items': summary_items,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d')
        }

    @staticmethod
    def get_sales_detail(start_date=None, end_date=None, page=1, per_page=20):
        """获取销售明细报表"""
        query = SaleItemModel.query.join(SaleOrder)

        if start_date:
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(SaleOrder.created_at >= start_date)

        if end_date:
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
            query = query.filter(SaleOrder.created_at <= end_date)

        # 改用 SQLAlchemy 原生方式
        pagination = query.order_by(desc(SaleOrder.created_at)).paginate(
            page=page, per_page=per_page, error_out=False
        )

        items = []
        for item in pagination.items:
            items.append({
                'order_id': item.order_id,
                'order_no': item.order.order_no if item.order else '',
                'order_date': item.order.created_at.strftime('%Y-%m-%d %H:%M:%S') if item.order and item.order.created_at else '',
                'customer_name': item.order.customer.name if item.order and item.order.customer else '',
                'product_name': item.product.name if item.product else '',
                'product_code': item.product.code if item.product else '',
                'unit_name': item.product.unit.name if item.product and item.product.unit else '',
                'quantity': item.quantity,
                'shipped_quantity': item.shipped_quantity,
                'unit_price': item.unit_price,
                'subtotal': item.subtotal,
                'status': item.order.status if item.order else ''
            })

        return items, pagination.total
