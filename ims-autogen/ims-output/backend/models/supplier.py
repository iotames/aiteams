"""
供应商模型
"""
from . import db
from datetime import datetime


class Supplier(db.Model):
    __tablename__ = 'supplier'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False, comment='供应商名称')
    contact = db.Column(db.String(50), default='', comment='联系人')
    phone = db.Column(db.String(30), default='', comment='联系电话')
    address = db.Column(db.Text, default='', comment='地址')
    remark = db.Column(db.Text, default='', comment='备注')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'contact': self.contact or '',
            'phone': self.phone or '',
            'address': self.address or '',
            'remark': self.remark or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }

    def __repr__(self):
        return f'<Supplier {self.name}>'
