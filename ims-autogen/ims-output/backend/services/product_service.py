"""
商品服务 - 商品/分类/单位 CRUD 业务逻辑
"""
from models import db
from models.product import Product
from models.category import Category
from models.unit import Unit
from models.purchase import PurchaseOrderItem
from models.sale import SaleOrderItem


class ProductService:

    # ─── 商品 CRUD ────────────────────────────────────────

    @staticmethod
    def get_products(search='', category_id=None, page=1, per_page=20):
        query = Product.query

        if search:
            query = query.filter(
                db.or_(
                    Product.name.like(f'%{search}%'),
                    Product.code.like(f'%{search}%')
                )
            )
        if category_id:
            query = query.filter_by(category_id=category_id)

        query = query.order_by(Product.updated_at.desc())
        total = query.count()
        products = query.offset((page - 1) * per_page).limit(per_page).all()

        return {
            'items': [p.to_dict() for p in products],
            'total': total,
            'page': page,
            'per_page': per_page
        }

    @staticmethod
    def get_product(product_id):
        product = Product.query.get(product_id)
        if not product:
            raise ValueError('商品不存在')
        return product.to_dict()

    @staticmethod
    def create_product(data):
        # 检查编码唯一性
        if Product.query.filter_by(code=data['code']).first():
            raise ValueError(f'商品编码 "{data["code"]}" 已存在')

        # 检查分类和单位存在
        if not Category.query.get(data['category_id']):
            raise ValueError('分类不存在')
        if not Unit.query.get(data['unit_id']):
            raise ValueError('单位不存在')

        product = Product(
            name=data['name'],
            code=data['code'],
            category_id=data['category_id'],
            unit_id=data['unit_id'],
            purchase_price=data.get('purchase_price', 0),
            sale_price=data.get('sale_price', 0),
            stock_low=data.get('stock_low', 0)
        )
        db.session.add(product)
        db.session.commit()
        return product.to_dict()

    @staticmethod
    def update_product(product_id, data):
        product = Product.query.get(product_id)
        if not product:
            raise ValueError('商品不存在')

        # 检查编码唯一性（排除自身）
        code = data.get('code')
        if code and code != product.code:
            existing = Product.query.filter_by(code=code).first()
            if existing:
                raise ValueError(f'商品编码 "{code}" 已存在')

        # 检查分类和单位存在
        if 'category_id' in data and data['category_id']:
            if not Category.query.get(data['category_id']):
                raise ValueError('分类不存在')
        if 'unit_id' in data and data['unit_id']:
            if not Unit.query.get(data['unit_id']):
                raise ValueError('单位不存在')

        for key in ('name', 'code', 'category_id', 'unit_id',
                     'purchase_price', 'sale_price', 'stock_low'):
            if key in data:
                setattr(product, key, data[key])

        db.session.commit()
        return product.to_dict()

    @staticmethod
    def delete_product(product_id):
        product = Product.query.get(product_id)
        if not product:
            raise ValueError('商品不存在')

        # 检查是否有业务引用
        po_count = PurchaseOrderItem.query.filter_by(product_id=product_id).count()
        so_count = SaleOrderItem.query.filter_by(product_id=product_id).count()
        if po_count > 0 or so_count > 0:
            raise ValueError(f'该商品已被 {po_count + so_count} 个订单引用，无法删除')

        db.session.delete(product)
        db.session.commit()
        return True

    # ─── 分类 CRUD ────────────────────────────────────────

    @staticmethod
    def get_categories():
        categories = Category.query.order_by(Category.name).all()
        return [c.to_dict() for c in categories]

    @staticmethod
    def create_category(data):
        if Category.query.filter_by(name=data['name']).first():
            raise ValueError(f'分类 "{data["name"]}" 已存在')
        category = Category(
            name=data['name'],
            parent_id=data.get('parent_id')
        )
        db.session.add(category)
        db.session.commit()
        return category.to_dict()

    @staticmethod
    def update_category(category_id, data):
        category = Category.query.get(category_id)
        if not category:
            raise ValueError('分类不存在')

        name = data.get('name')
        if name and name != category.name:
            if Category.query.filter_by(name=name).first():
                raise ValueError(f'分类 "{name}" 已存在')
            category.name = name

        if 'parent_id' in data:
            category.parent_id = data['parent_id']

        db.session.commit()
        return category.to_dict()

    @staticmethod
    def delete_category(category_id):
        category = Category.query.get(category_id)
        if not category:
            raise ValueError('分类不存在')

        # 检查是否有商品引用
        product_count = Product.query.filter_by(category_id=category_id).count()
        if product_count > 0:
            raise ValueError(f'该分类下还有 {product_count} 个商品，请先移除')

        db.session.delete(category)
        db.session.commit()
        return True

    # ─── 单位 CRUD ────────────────────────────────────────

    @staticmethod
    def get_units():
        units = Unit.query.order_by(Unit.name).all()
        return [u.to_dict() for u in units]

    @staticmethod
    def create_unit(data):
        if Unit.query.filter_by(name=data['name']).first():
            raise ValueError(f'单位 "{data["name"]}" 已存在')
        unit = Unit(name=data['name'])
        db.session.add(unit)
        db.session.commit()
        return unit.to_dict()

    @staticmethod
    def update_unit(unit_id, data):
        unit = Unit.query.get(unit_id)
        if not unit:
            raise ValueError('单位不存在')

        name = data.get('name')
        if name and name != unit.name:
            if Unit.query.filter_by(name=name).first():
                raise ValueError(f'单位 "{name}" 已存在')
            unit.name = name

        db.session.commit()
        return unit.to_dict()

    @staticmethod
    def delete_unit(unit_id):
        unit = Unit.query.get(unit_id)
        if not unit:
            raise ValueError('单位不存在')

        # 检查是否有商品引用
        product_count = Product.query.filter_by(unit_id=unit_id).count()
        if product_count > 0:
            raise ValueError(f'该单位还有 {product_count} 个商品使用，请先修改')

        db.session.delete(unit)
        db.session.commit()
        return True
