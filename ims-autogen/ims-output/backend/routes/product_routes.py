"""商品/分类/单位 CRUD 路由"""

from flask import Blueprint, request
from models import db
from models.category import Category
from models.product import Product, Unit
from services.product_service import ProductService
from utils.response import success_response, error_response
from utils.validators import validate_required

product_bp = Blueprint('product', __name__, url_prefix='/api/v1')


# ===== 分类 =====

@product_bp.route('/categories', methods=['GET'])
def list_categories():
    """获取分类列表"""
    categories = Category.query.order_by(Category.name).all()
    return success_response([c.to_dict() for c in categories])


@product_bp.route('/categories', methods=['POST'])
def create_category():
    """创建分类"""
    data = request.get_json(silent=True) or {}
    ok, msg = validate_required(data, ['name'])
    if not ok:
        return error_response(msg)

    category = Category(name=data['name'], remark=data.get('remark', ''))
    db.session.add(category)
    db.session.commit()
    return success_response(category.to_dict(), '分类创建成功')


@product_bp.route('/categories/<int:category_id>', methods=['PUT'])
def update_category(category_id):
    """更新分类"""
    category = Category.query.get(category_id)
    if not category:
        return error_response('分类不存在', 404)

    data = request.get_json(silent=True) or {}
    if 'name' in data:
        category.name = data['name']
    if 'remark' in data:
        category.remark = data['remark']
    db.session.commit()
    return success_response(category.to_dict(), '分类更新成功')


@product_bp.route('/categories/<int:category_id>', methods=['DELETE'])
def delete_category(category_id):
    """删除分类"""
    category = Category.query.get(category_id)
    if not category:
        return error_response('分类不存在', 404)

    # 检查是否有商品关联
    if Product.query.filter_by(category_id=category_id).first():
        return error_response('该分类下存在商品，无法删除')

    db.session.delete(category)
    db.session.commit()
    return success_response(message='分类删除成功')


# ===== 单位 =====

@product_bp.route('/units', methods=['GET'])
def list_units():
    """获取单位列表"""
    units = Unit.query.order_by(Unit.name).all()
    return success_response([u.to_dict() for u in units])


@product_bp.route('/units', methods=['POST'])
def create_unit():
    """创建单位"""
    data = request.get_json(silent=True) or {}
    ok, msg = validate_required(data, ['name'])
    if not ok:
        return error_response(msg)

    unit = Unit(name=data['name'])
    db.session.add(unit)
    db.session.commit()
    return success_response(unit.to_dict(), '单位创建成功')


@product_bp.route('/units/<int:unit_id>', methods=['PUT'])
def update_unit(unit_id):
    """更新单位"""
    unit = Unit.query.get(unit_id)
    if not unit:
        return error_response('单位不存在', 404)

    data = request.get_json(silent=True) or {}
    if 'name' in data:
        unit.name = data['name']
    db.session.commit()
    return success_response(unit.to_dict(), '单位更新成功')


@product_bp.route('/units/<int:unit_id>', methods=['DELETE'])
def delete_unit(unit_id):
    """删除单位"""
    unit = Unit.query.get(unit_id)
    if not unit:
        return error_response('单位不存在', 404)

    if Product.query.filter_by(unit_id=unit_id).first():
        return error_response('该单位下存在商品，无法删除')

    db.session.delete(unit)
    db.session.commit()
    return success_response(message='单位删除成功')


# ===== 商品 =====

@product_bp.route('/products', methods=['GET'])
def list_products():
    """获取商品列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    keyword = request.args.get('keyword', '').strip()
    category_id = request.args.get('category_id', type=int)

    products, total = ProductService.get_product_list(
        page=page, per_page=per_page,
        keyword=keyword, category_id=category_id
    )
    return success_response({
        'items': [p.to_dict() for p in products],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page if per_page > 0 else 0
    })


@product_bp.route('/products', methods=['POST'])
def create_product():
    """创建商品"""
    data = request.get_json(silent=True) or {}
    try:
        product = ProductService.create_product(data)
        return success_response(product.to_dict(), '商品创建成功')
    except ValueError as e:
        return error_response(str(e))


@product_bp.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    """获取商品详情"""
    product = Product.query.get(product_id)
    if not product:
        return error_response('商品不存在', 404)
    return success_response(product.to_dict())


@product_bp.route('/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    """更新商品"""
    data = request.get_json(silent=True) or {}
    try:
        product = ProductService.update_product(product_id, data)
        return success_response(product.to_dict(), '商品更新成功')
    except ValueError as e:
        return error_response(str(e))


@product_bp.route('/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    """删除商品"""
    try:
        ProductService.delete_product(product_id)
        return success_response(message='商品删除成功')
    except ValueError as e:
        return error_response(str(e))
