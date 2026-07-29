"""商品数据模型"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from . import db


class Unit(db.Model):
    """计量单位"""
    __tablename__ = 'unit'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(20), nullable=False, unique=True, comment='单位名称')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class Product(db.Model):
    """商品"""
    __tablename__ = 'product'

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False, comment='商品编码')
    name = Column(String(200), nullable=False, comment='商品名称')
    category_id = Column(Integer, ForeignKey('category.id'), nullable=True, comment='分类ID')
    unit_id = Column(Integer, ForeignKey('unit.id'), nullable=True, comment='单位ID')
    purchase_price = Column(Float, default=0.0, comment='采购价')
    sale_price = Column(Float, default=0.0, comment='销售价')
    current_stock = Column(Float, default=0.0, comment='当前库存')
    min_stock = Column(Float, default=0.0, comment='库存下限')
    max_stock = Column(Float, default=0.0, comment='库存上限')
    remark = Column(Text, default='', comment='备注')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    category = relationship('Category', backref='products', lazy='select')
    unit = relationship('Unit', backref='products', lazy='select')

    def to_dict(self):
        cs = float(self.current_stock or 0)
        ms = float(self.min_stock or 0)
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else None,
            'unit_id': self.unit_id,
            'unit_name': self.unit.name if self.unit else None,
            'purchase_price': self.purchase_price,
            'sale_price': self.sale_price,
            'current_stock': cs,
            'min_stock': ms,
            'stock_low': ms,  # 前端向后兼容
            'max_stock': float(self.max_stock or 0),
            'is_low_stock': cs < ms if ms else False,
            'remark': self.remark or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }
