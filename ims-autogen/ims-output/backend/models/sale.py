"""销售订单及其明细模型"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from . import db


class SaleOrder(db.Model):
    """销售订单"""
    __tablename__ = 'sale_order'

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_no = Column(String(50), unique=True, nullable=False, comment='订单编号')
    customer_id = Column(Integer, ForeignKey('customer.id'), nullable=False, comment='客户ID')
    total_amount = Column(Float, default=0.0, comment='总金额')
    status = Column(String(20), default='draft', comment='状态：draft-草稿, shipped-已出库')
    remark = Column(Text, default='', comment='备注')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')

    customer = relationship('Customer', backref='sale_orders', lazy='select')
    items = relationship('SaleOrderItem', backref='order', lazy='select',
                         cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'order_no': self.order_no,
            'customer_id': self.customer_id,
            'customer_name': self.customer.name if self.customer else '',
            'total_amount': self.total_amount,
            'status': self.status,
            'remark': self.remark or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'items': [item.to_dict() for item in self.items] if self.items else []
        }


class SaleOrderItem(db.Model):
    """销售订单明细"""
    __tablename__ = 'sale_order_item'

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey('sale_order.id'), nullable=False, comment='订单ID')
    product_id = Column(Integer, ForeignKey('product.id'), nullable=False, comment='商品ID')
    quantity = Column(Float, nullable=False, default=0.0, comment='数量')
    shipped_quantity = Column(Float, default=0.0, comment='已出库数量')
    price = Column(Float, default=0.0, comment='单价')
    amount = Column(Float, default=0.0, comment='金额')

    product = relationship('Product', backref='sale_items', lazy='select')

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else '',
            'product_code': self.product.code if self.product else '',
            'unit_name': self.product.unit.name if self.product and self.product.unit else '',
            'quantity': self.quantity,
            'shipped_quantity': self.shipped_quantity,
            'price': self.price,
            'amount': self.amount
        }
