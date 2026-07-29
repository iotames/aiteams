"""
数据模型初始化
"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from .category import Category
from .product import Unit, Product
from .supplier import Supplier
from .customer import Customer
from .purchase import PurchaseOrder, PurchaseOrderItem
from .sale import SaleOrder, SaleOrderItem
from .stock import StockTransaction
