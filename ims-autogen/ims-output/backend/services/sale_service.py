"""销售服务 - 销售订单创建/编辑/删除/出库确认"""

from datetime import datetime
from models import db
from models.sale import SaleOrder, SaleOrderItem
from models.product import Product
from models.customer import Customer
from models.stock import StockTransaction


class SaleService:

    @staticmethod
    def _generate_order_no():
        """生成销售订单编号：SO-YYYYMMDD-XXXX"""
        today = datetime.now().strftime('%Y%m%d')
        count = SaleOrder.query.filter(
            SaleOrder.order_no.like(f'SO-{today}-%')
        ).count()
        return f'SO-{today}-{count + 1:04d}'

    @staticmethod
    def get_orders(search='', status=None, page=1, per_page=20):
        query = SaleOrder.query

        if search:
            query = query.filter(
                db.or_(
                    SaleOrder.order_no.like(f'%{search}%'),
                    SaleOrder.customer.has(
                        Customer.name.like(f'%{search}%')
                    )
                )
            )
        if status:
            query = query.filter_by(status=status)

        query = query.order_by(SaleOrder.created_at.desc())
        total = query.count()
        orders = query.offset((page - 1) * per_page).limit(per_page).all()

        return {
            'items': [o.to_dict() for o in orders],
            'total': total,
            'page': page,
            'per_page': per_page
        }

    @staticmethod
    def get_order(order_id):
        order = SaleOrder.query.get(order_id)
        if not order:
            raise ValueError('销售订单不存在')
        return order.to_dict()

    @staticmethod
    def create_order(data):
        customer_id = data['customer_id']
        if not Customer.query.get(customer_id):
            raise ValueError('客户不存在')

        items_data = data.get('items', [])
        if not items_data:
            raise ValueError('订单明细不能为空')

        stock_warnings = []
        total_amount = 0
        items = []

        for item_data in items_data:
            product = Product.query.get(item_data['product_id'])
            if not product:
                raise ValueError(f'商品ID {item_data["product_id"]} 不存在')

            quantity = float(item_data['quantity'])
            unit_price = float(item_data.get('unit_price', product.sale_price or 0))
            subtotal = quantity * unit_price
            total_amount += subtotal

            current_stock = float(product.current_stock or 0)
            if quantity > current_stock:
                stock_warnings.append({
                    'product_name': product.name,
                    'current_stock': current_stock,
                    'required': quantity
                })

            items.append(SaleOrderItem(
                product_id=item_data['product_id'],
                quantity=quantity,
                shipped_quantity=0,
                unit_price=unit_price,
                subtotal=subtotal
            ))

        order = SaleOrder(
            order_no=SaleService._generate_order_no(),
            customer_id=customer_id,
            status='待出库',
            total_amount=total_amount,
            remark=data.get('remark', ''),
            items=items
        )
        db.session.add(order)
        db.session.commit()

        result = order.to_dict()
        if stock_warnings:
            result['stock_warnings'] = stock_warnings

        return result

    @staticmethod
    def update_order(order_id, data):
        order = SaleOrder.query.get(order_id)
        if not order:
            raise ValueError('销售订单不存在')
        if order.status != '待出库':
            raise ValueError(f'订单状态为 {order.status}，不能修改')

        if 'customer_id' in data:
            if not Customer.query.get(data['customer_id']):
                raise ValueError('客户不存在')
            order.customer_id = data['customer_id']

        if 'remark' in data:
            order.remark = data['remark']

        if 'items' in data:
            items_data = data['items']
            if not items_data:
                raise ValueError('订单明细不能为空')

            SaleOrderItem.query.filter_by(order_id=order_id).delete()

            total_amount = 0
            for item_data in items_data:
                product = Product.query.get(item_data['product_id'])
                if not product:
                    raise ValueError(f'商品ID {item_data["product_id"]} 不存在')

                quantity = float(item_data['quantity'])
                unit_price = float(item_data.get('unit_price', product.sale_price or 0))
                subtotal = quantity * unit_price
                total_amount += subtotal

                item = SaleOrderItem(
                    order_id=order_id,
                    product_id=item_data['product_id'],
                    quantity=quantity,
                    shipped_quantity=0,
                    unit_price=unit_price,
                    subtotal=subtotal
                )
                db.session.add(item)

            order.total_amount = total_amount

        db.session.commit()
        return order.to_dict()

    @staticmethod
    def delete_order(order_id):
        order = SaleOrder.query.get(order_id)
        if not order:
            raise ValueError('销售订单不存在')
        if order.status != '待出库':
            raise ValueError(f'订单状态为 {order.status}，不能删除')

        db.session.delete(order)
        db.session.commit()
        return True

    @staticmethod
    def ship_order(order_id, ship_data=None):
        """
        出库确认
        ship_data: [{"item_id": 1, "quantity": 10}, ...]
        如果为 None 则全部出库
        """
        order = SaleOrder.query.get(order_id)
        if not order:
            raise ValueError('销售订单不存在')
        if order.status in ('已完成', '已取消'):
            raise ValueError(f'订单已{order.status}，不能出库')

        items = SaleOrderItem.query.filter_by(order_id=order.id).all()
        if not items:
            raise ValueError('订单无明细，无法出库')

        ship_map = {}
        if ship_data:
            for si in ship_data:
                ship_map[si['item_id']] = float(si.get('quantity', 0))

        all_completed = True
        any_shipped = False
        stock_changes = []

        for item in items:
            remaining = item.quantity - item.shipped_quantity
            if remaining <= 0:
                continue

            if ship_data and item.id in ship_map:
                ship_qty = min(ship_map[item.id], remaining)
            elif ship_data:
                continue
            else:
                ship_qty = remaining

            if ship_qty <= 0:
                continue

            any_shipped = True
            product = Product.query.get(item.product_id)
            stock_before = float(product.current_stock or 0)
            actual_deduction = min(stock_before, ship_qty)

            item.shipped_quantity += actual_deduction
            product.current_stock = max(0, stock_before - actual_deduction)

            txn = StockTransaction(
                product_id=product.id,
                type='销售出库',
                quantity_change=-actual_deduction,
                reference_type='sale_order',
                reference_id=order.id,
                reference_item_id=item.id,
                stock_before=stock_before,
                stock_after=max(0, stock_before - actual_deduction),
                remark=f'销售订单 {order.order_no} 出库确认'
            )
            db.session.add(txn)

            stock_changes.append({
                'product_id': product.id,
                'product_name': product.name,
                'ship_qty': actual_deduction,
                'stock_before': stock_before,
                'stock_after': float(product.current_stock)
            })

            if item.shipped_quantity < item.quantity:
                all_completed = False

        if not any_shipped:
            raise ValueError('没有需要出库的商品')

        if all_completed:
            order.status = '已完成'
        else:
            order.status = '部分出库'

        order.updated_at = datetime.now()
        db.session.commit()

        return {
            'order': order.to_dict(),
            'stock_changes': stock_changes
        }

    @staticmethod
    def cancel_order(order_id):
        order = SaleOrder.query.get(order_id)
        if not order:
            raise ValueError('销售订单不存在')
        if order.status in ('已完成', '已取消'):
            raise ValueError(f'订单已{order.status}，不能取消')

        has_shipped = any(
            float(item.shipped_quantity or 0) > 0 for item in order.items
        )
        if has_shipped:
            raise ValueError('订单已有出库记录，不能取消（请先联系管理员处理）')

        order.status = '已取消'
        db.session.commit()
        return order.to_dict()
