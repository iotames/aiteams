"""
采购订单及其明细模型
"""
from . import db
from datetime import datetime


class PurchaseOrder(db.Model):
    __tablename__ = 'purchase_order'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    order_no = db.Column(db.String(50), nullable=False, unique=True, comment='订单编号')
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=False, comment='供应商')
    status = db.Column(db.String(20), nullable=False, default='待入库',
                       comment='状态: 待入库/部分入库/已完成/已取消')
    total_amount = db.Column(db.Numeric(12, 2), default=0, comment='订单总金额')
    remark = db.Column(db.Text, default='', comment='备注')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    created_by = db.Column(db.String(50), default=None, comment='预留扩展')

    # 关系
    supplier = db.relationship('Supplier', backref='purchase_orders')
    items = db.relationship('PurchaseOrderItem', backref='order', lazy='joined',
                            cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'order_no': self.order_no,
            'supplier_id': self.supplier_id,
            'supplier_name': self.supplier.name if self.supplier else None,
            'status': self.status,
            'total_amount': float(self.total_amount) if self.total_amount else 0,
            'remark': self.remark or '',
            'items': [item.to_dict() for item in self.items],
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }

    def __repr__(self):
        return f'<PurchaseOrder {self.order_no}>'


class PurchaseOrderItem(db.Model):
    __tablename__ = 'purchase_order_item'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    order_id = db.Column(db.Integer, db.ForeignKey('purchase_order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), nullable=False, comment='订购数量')
    received_quantity = db.Column(db.Numeric(10, 2), default=0, comment='已入库数量')
    unit_price = db.Column(db.Numeric(10, 2), nullable=False, comment='单价')
    subtotal = db.Column(db.Numeric(12, 2), default=0, comment='小计')

    # 关系
    product = db.relationship('Product')

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else None,
            'product_code': self.product.code if self.product else None,
            'quantity': float(self.quantity) if self.quantity else 0,
            'received_quantity': float(self.received_quantity) if self.received_quantity else 0,
            'pending_quantity': float(self.quantity or 0) - float(self.received_quantity or 0),
            'unit_price': float(self.unit_price) if self.unit_price else 0,
            'subtotal': float(self.subtotal) if self.subtotal else 0
        }

    def __repr__(self):
        return f'<PurchaseOrderItem {self.product_id} x {self.quantity}>'
