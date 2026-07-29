"""采购服务 - 采购订单创建/编辑/删除/入库确认"""

from datetime import datetime
from sqlalchemy import desc
from models import db
from models.purchase import PurchaseOrder, PurchaseOrderItem
from models.product import Product
from models.supplier import Supplier
from models.stock import StockTransaction


class PurchaseService:
    """采购订单业务逻辑"""

    @staticmethod
    def generate_order_no():
        """生成采购订单编号：PO-YYYYMMDD-XXXX"""
        today = datetime.now().strftime('%Y%m%d')
        last_order = PurchaseOrder.query.filter(
            PurchaseOrder.order_no.like(f'PO-{today}-%')
        ).order_by(desc(PurchaseOrder.id)).first()

        if last_order:
            seq = int(last_order.order_no.split('-')[-1]) + 1
        else:
            seq = 1
        return f'PO-{today}-{seq:04d}'

    @staticmethod
    def create_order(data):
        """创建采购订单"""
        # 校验供应商
        supplier = Supplier.query.get(data.get('supplier_id'))
        if not supplier:
            raise ValueError('供应商不存在')

        items_data = data.get('items', [])
        if not items_data:
            raise ValueError('请至少添加一个商品明细')

        # 创建订单
        order = PurchaseOrder(
            order_no=PurchaseService.generate_order_no(),
            supplier_id=supplier.id,
            status='待入库',
            remark=data.get('remark', '')
        )
        db.session.add(order)
        db.session.flush()  # 获取 order.id

        total_amount = 0
        for item in items_data:
            product = Product.query.get(item.get('product_id'))
            if not product:
                db.session.rollback()
                raise ValueError(f'商品ID={item.get("product_id")}不存在')

            quantity = float(item.get('quantity', 0))
            unit_price = float(item.get('unit_price', 0))
            subtotal = quantity * unit_price
            total_amount += subtotal

            order_item = PurchaseOrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=quantity,
                received_quantity=0,
                unit_price=unit_price,
                subtotal=subtotal
            )
            db.session.add(order_item)

        order.total_amount = total_amount
        db.session.commit()
        return order

    @staticmethod
    def update_order(order_id, data):
        """编辑采购订单（仅待入库可编辑）"""
        order = PurchaseOrder.query.get(order_id)
        if not order:
            raise ValueError('采购订单不存在')
        if order.status != '待入库':
            raise ValueError('仅待入库状态的订单可编辑')

        # 删除旧明细
        PurchaseOrderItem.query.filter_by(order_id=order.id).delete()

        # 更新基本信息
        if 'supplier_id' in data:
            supplier = Supplier.query.get(data['supplier_id'])
            if not supplier:
                raise ValueError('供应商不存在')
            order.supplier_id = supplier.id
        if 'remark' in data:
            order.remark = data['remark']

        items_data = data.get('items', [])
        if not items_data:
            db.session.rollback()
            raise ValueError('请至少添加一个商品明细')

        total_amount = 0
        for item in items_data:
            product = Product.query.get(item.get('product_id'))
            if not product:
                db.session.rollback()
                raise ValueError(f'商品ID={item.get("product_id")}不存在')

            quantity = float(item.get('quantity', 0))
            unit_price = float(item.get('unit_price', 0))
            subtotal = quantity * unit_price
            total_amount += subtotal

            order_item = PurchaseOrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=quantity,
                received_quantity=0,
                unit_price=unit_price,
                subtotal=subtotal
            )
            db.session.add(order_item)

        order.total_amount = total_amount
        order.updated_at = datetime.now()
        db.session.commit()
        return order

    @staticmethod
    def delete_order(order_id):
        """删除采购订单（仅待入库可删除）"""
        order = PurchaseOrder.query.get(order_id)
        if not order:
            raise ValueError('采购订单不存在')
        if order.status != '待入库':
            raise ValueError('仅待入库状态的订单可删除')

        PurchaseOrderItem.query.filter_by(order_id=order.id).delete()
        db.session.delete(order)
        db.session.commit()

    @staticmethod
    def receive_order(order_id, receive_items=None):
        """入库确认
        receive_items: [{"item_id": 1, "receive_qty": 50}, ...]
        如果为 None 则全部入库
        """
        order = PurchaseOrder.query.get(order_id)
        if not order:
            raise ValueError('采购订单不存在')
        if order.status == '已完成':
            raise ValueError('订单已完成，不可重复入库')
        if order.status == '已取消':
            raise ValueError('订单已取消，不可入库')

        items = PurchaseOrderItem.query.filter_by(order_id=order.id).all()
        if not items:
            raise ValueError('订单无明细，无法入库')

        # 构建接收映射
        receive_map = {}
        if receive_items:
            for ri in receive_items:
                receive_map[ri['item_id']] = float(ri.get('receive_qty', 0))

        all_completed = True
        any_received = False

        for item in items:
            remaining = item.quantity - item.received_quantity
            if remaining <= 0:
                continue

            if receive_items and item.id in receive_map:
                receive_qty = min(receive_map[item.id], remaining)
            elif receive_items:
                continue  # 未在接收列表中，不入库
            else:
                receive_qty = remaining  # 全部入库

            if receive_qty <= 0:
                continue

            any_received = True
            product = Product.query.get(item.product_id)

            # 记录变更前库存
            stock_before = float(product.current_stock) if product.current_stock else 0

            # 更新已入库数量
            item.received_quantity += receive_qty

            # 更新商品库存
            product.current_stock = stock_before + receive_qty

            # 记录库存流水
            transaction = StockTransaction(
                product_id=product.id,
                type='采购入库',
                quantity_change=receive_qty,
                reference_type='purchase_order',
                reference_id=order.id,
                reference_item_id=item.id,
                stock_before=stock_before,
                stock_after=stock_before + receive_qty,
                remark=f'采购订单 {order.order_no} 入库确认'
            )
            db.session.add(transaction)

            # 检查是否全部入库
            if item.received_quantity < item.quantity:
                all_completed = False

        if not any_received:
            raise ValueError('没有需要入库的商品')

        # 更新订单状态
        if all_completed:
            order.status = '已完成'
        else:
            order.status = '部分入库'

        order.updated_at = datetime.now()
        db.session.commit()
        return order

    @staticmethod
    def cancel_order(order_id):
        """取消采购订单"""
        order = PurchaseOrder.query.get(order_id)
        if not order:
            raise ValueError('采购订单不存在')
        if order.status in ('已完成', '已取消'):
            raise ValueError(f'订单已{order.status}，无法取消')

        order.status = '已取消'
        order.updated_at = datetime.now()
        db.session.commit()
        return order

    @staticmethod
    def get_order_detail(order_id):
        """获取采购订单详情（含明细）"""
        order = PurchaseOrder.query.get(order_id)
        return order

    @staticmethod
    def get_order_list(page=1, per_page=20, status=None, keyword=None):
        """获取采购订单列表"""
        query = PurchaseOrder.query

        if status:
            query = query.filter(PurchaseOrder.status == status)
        if keyword:
            query = query.join(Supplier).filter(
                Supplier.name.contains(keyword) |
                PurchaseOrder.order_no.contains(keyword)
            )

        query = query.order_by(desc(PurchaseOrder.created_at))
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return pagination.items, pagination.total
