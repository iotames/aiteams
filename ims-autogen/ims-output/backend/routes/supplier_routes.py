"""供应商 CRUD 路由"""

from flask import Blueprint, request
from models import db
from models.supplier import Supplier
from utils.response import success_response, error_response
from utils.validators import validate_required

supplier_bp = Blueprint('supplier', __name__, url_prefix='/api/v1')


@supplier_bp.route('/suppliers', methods=['GET'])
def list_suppliers():
    """获取供应商列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    keyword = request.args.get('keyword', '').strip()

    query = Supplier.query
    if keyword:
        query = query.filter(
            Supplier.name.contains(keyword) |
            Supplier.contact.contains(keyword) |
            Supplier.phone.contains(keyword)
        )

    query = query.order_by(Supplier.name)
    total = query.count()
    suppliers = query.offset((page - 1) * per_page).limit(per_page).all()

    return success_response({
        'items': [s.to_dict() for s in suppliers],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page if per_page > 0 else 0
    })


@supplier_bp.route('/suppliers', methods=['POST'])
def create_supplier():
    """创建供应商"""
    data = request.get_json(silent=True) or {}
    ok, msg = validate_required(data, ['name'])
    if not ok:
        return error_response(msg)

    supplier = Supplier(
        name=data['name'],
        contact=data.get('contact', ''),
        phone=data.get('phone', ''),
        address=data.get('address', ''),
        remark=data.get('remark', '')
    )
    db.session.add(supplier)
    db.session.commit()
    return success_response(supplier.to_dict(), '供应商创建成功')


@supplier_bp.route('/suppliers/<int:supplier_id>', methods=['PUT'])
def update_supplier(supplier_id):
    """更新供应商"""
    supplier = Supplier.query.get(supplier_id)
    if not supplier:
        return error_response('供应商不存在', 404)

    data = request.get_json(silent=True) or {}
    if 'name' in data:
        supplier.name = data['name']
    if 'contact' in data:
        supplier.contact = data['contact']
    if 'phone' in data:
        supplier.phone = data['phone']
    if 'address' in data:
        supplier.address = data['address']
    if 'remark' in data:
        supplier.remark = data['remark']
    db.session.commit()
    return success_response(supplier.to_dict(), '供应商更新成功')


@supplier_bp.route('/suppliers/<int:supplier_id>', methods=['DELETE'])
def delete_supplier(supplier_id):
    """删除供应商"""
    supplier = Supplier.query.get(supplier_id)
    if not supplier:
        return error_response('供应商不存在', 404)

    from models.purchase import PurchaseOrder
    if PurchaseOrder.query.filter_by(supplier_id=supplier_id).first():
        return error_response('该供应商存在关联的采购订单，无法删除')

    db.session.delete(supplier)
    db.session.commit()
    return success_response(message='供应商删除成功')
