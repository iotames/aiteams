"""客户 CRUD 路由"""

from flask import Blueprint, request
from models import db
from models.customer import Customer
from utils.response import success_response, error_response
from utils.validators import validate_required

customer_bp = Blueprint('customer', __name__, url_prefix='/api/v1')


@customer_bp.route('/customers', methods=['GET'])
def list_customers():
    """获取客户列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    keyword = request.args.get('keyword', '').strip()

    query = Customer.query
    if keyword:
        query = query.filter(
            Customer.name.contains(keyword) |
            Customer.contact.contains(keyword) |
            Customer.phone.contains(keyword)
        )

    query = query.order_by(Customer.name)
    total = query.count()
    customers = query.offset((page - 1) * per_page).limit(per_page).all()

    return success_response({
        'items': [c.to_dict() for c in customers],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page if per_page > 0 else 0
    })


@customer_bp.route('/customers', methods=['POST'])
def create_customer():
    """创建客户"""
    data = request.get_json(silent=True) or {}
    ok, msg = validate_required(data, ['name'])
    if not ok:
        return error_response(msg)

    customer = Customer(
        name=data['name'],
        contact=data.get('contact', ''),
        phone=data.get('phone', ''),
        address=data.get('address', ''),
        remark=data.get('remark', '')
    )
    db.session.add(customer)
    db.session.commit()
    return success_response(customer.to_dict(), '客户创建成功')


@customer_bp.route('/customers/<int:customer_id>', methods=['PUT'])
def update_customer(customer_id):
    """更新客户"""
    customer = Customer.query.get(customer_id)
    if not customer:
        return error_response('客户不存在', 404)

    data = request.get_json(silent=True) or {}
    if 'name' in data:
        customer.name = data['name']
    if 'contact' in data:
        customer.contact = data['contact']
    if 'phone' in data:
        customer.phone = data['phone']
    if 'address' in data:
        customer.address = data['address']
    if 'remark' in data:
        customer.remark = data['remark']
    db.session.commit()
    return success_response(customer.to_dict(), '客户更新成功')


@customer_bp.route('/customers/<int:customer_id>', methods=['DELETE'])
def delete_customer(customer_id):
    """删除客户"""
    customer = Customer.query.get(customer_id)
    if not customer:
        return error_response('客户不存在', 404)

    from models.sale import SaleOrder
    if SaleOrder.query.filter_by(customer_id=customer_id).first():
        return error_response('该客户存在关联的销售订单，无法删除')

    db.session.delete(customer)
    db.session.commit()
    return success_response(message='客户删除成功')
