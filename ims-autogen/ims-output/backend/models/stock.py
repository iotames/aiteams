"""
库存流水模型
记录每一次库存变更的明细日志
"""
from . import db
from datetime import datetime


class StockTransaction(db.Model):
    __tablename__ = 'stock_transaction'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False, comment='商品')
    type = db.Column(db.String(20), nullable=False, comment='类型: 采购入库/销售出库/入库冲正/出库冲正')
    quantity_change = db.Column(db.Numeric(10, 2), nullable=False, comment='变更数量（入库为正+，出库为负-）')
    stock_before = db.Column(db.Numeric(10, 2), nullable=False, comment='变更前库存')
    stock_after = db.Column(db.Numeric(10, 2), nullable=False, comment='变更后库存')
    reference_type = db.Column(db.String(30), nullable=False, comment='来源单据类型: purchase_order/sale_order')
    reference_id = db.Column(db.Integer, nullable=False, comment='来源单据ID')
    reference_item_id = db.Column(db.Integer, nullable=False, comment='来源明细ID')
    remark = db.Column(db.String(200), default='', comment='备注')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')

    # 关系
    product = db.relationship('Product')

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else None,
            'product_code': self.product.code if self.product else None,
            'type': self.type,
            'quantity_change': float(self.quantity_change) if self.quantity_change else 0,
            'stock_before': float(self.stock_before) if self.stock_before else 0,
            'stock_after': float(self.stock_after) if self.stock_after else 0,
            'reference_type': self.reference_type,
            'reference_id': self.reference_id,
            'reference_item_id': self.reference_item_id,
            'remark': self.remark or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }

    def __repr__(self):
        return f'<StockTransaction {self.type} {self.quantity_change}>'
