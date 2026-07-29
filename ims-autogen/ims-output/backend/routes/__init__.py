"""API 路由初始化"""

from .product_routes import product_bp
from .supplier_routes import supplier_bp
from .customer_routes import customer_bp
from .purchase_routes import purchase_bp
from .sale_routes import sale_bp
from .stock_routes import stock_bp
from .report_routes import report_bp

all_blueprints = [
    product_bp,
    supplier_bp,
    customer_bp,
    purchase_bp,
    sale_bp,
    stock_bp,
    report_bp
]

__all__ = ['all_blueprints']
