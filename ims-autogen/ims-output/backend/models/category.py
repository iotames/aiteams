"""
商品分类模型
"""
from . import db
from datetime import datetime


class Category(db.Model):
    __tablename__ = 'category'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False, unique=True, comment='分类名称')
    parent_id = db.Column(db.Integer, db.ForeignKey('category.id'), default=None, comment='父分类ID')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')

    # 自关联关系
    parent = db.relationship('Category', remote_side=[id], backref='children')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'parent_id': self.parent_id,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }

    def __repr__(self):
        return f'<Category {self.name}>'
