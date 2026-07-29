"""客户数据模型"""

from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from . import db


class Customer(db.Model):
    """客户"""
    __tablename__ = 'customer'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment='客户名称')
    contact = Column(String(50), default='', comment='联系人')
    phone = Column(String(30), default='', comment='联系电话')
    address = Column(Text, default='', comment='地址')
    remark = Column(Text, default='', comment='备注')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

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
